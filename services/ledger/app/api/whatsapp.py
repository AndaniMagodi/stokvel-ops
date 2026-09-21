"""Meta WhatsApp Cloud API webhook and POP review queue."""

from datetime import date, datetime, timezone
import hashlib
import hmac
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contributions.ai_proof import AIProofUnavailable, extract_with_ai
from app.contributions.members import match_member
from app.contributions.proof import MAX_FILE_BYTES, ProofError, extract_proof_text, suggest_proof_fields
from app.core.config import settings
from app.db.session import get_db
from app.models.whatsapp import WhatsAppInbound


router = APIRouter(tags=["whatsapp"])


def _group_id() -> UUID:
    try:
        return UUID(settings.whatsapp_group_id or "")
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="WHATSAPP_GROUP_ID is not configured") from exc


def _valid_signature(body: bytes, signature: str | None) -> bool:
    if not settings.whatsapp_app_secret:
        return False
    expected = "sha256=" + hmac.new(
        settings.whatsapp_app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return bool(signature and hmac.compare_digest(expected, signature))


def _messages(payload: dict):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for message in change.get("value", {}).get("messages", []):
                yield message


def _media_details(message: dict) -> tuple[str | None, str | None, str | None]:
    kind = message.get("type", "unknown")
    content = message.get(kind, {}) if kind in {"image", "document"} else {}
    return content.get("id"), content.get("filename"), content.get("mime_type")


def _download_media(media_id: str) -> bytes:
    if not settings.whatsapp_access_token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN is not configured")
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    base = f"https://graph.facebook.com/{settings.whatsapp_graph_version}"
    with httpx.Client(timeout=20) as client:
        metadata = client.get(f"{base}/{media_id}", headers=headers)
        metadata.raise_for_status()
        url = metadata.json()["url"]
        response = client.get(url, headers=headers)
        response.raise_for_status()
        data = response.content
    if not data or len(data) > MAX_FILE_BYTES:
        raise ProofError("WhatsApp proof must be between 1 byte and 5 MB")
    return data


def _process(item: WhatsAppInbound, db: Session) -> None:
    if not item.media_id:
        item.status = "ignored"
        item.warnings = ["Send the proof as a PDF, image, or screenshot."]
        return
    try:
        text = extract_proof_text(_download_media(item.media_id))
        try:
            suggestion = extract_with_ai(text) if settings.groq_api_key else suggest_proof_fields(text)
            method = "ai" if settings.groq_api_key else "local"
        except AIProofUnavailable:
            suggestion = suggest_proof_fields(text)
            method = "local"
        member, match_method, needs_review = match_member(
            db, item.group_id, reference=suggestion.reference, sender_phone=item.sender_phone
        )
        item.payment_date = suggestion.payment_date
        item.amount_cents = suggestion.amount_cents
        item.reference = suggestion.reference
        item.suggested_member_id = member.id if member else None
        item.extraction_method = method
        item.warnings = list(suggestion.warnings)
        if match_method:
            item.warnings.append(f"Member matched by {match_method}.")
        if needs_review:
            item.warnings.append("Member match needs manual review.")
        complete = member and suggestion.payment_date and suggestion.amount_cents and suggestion.reference
        item.status = "ready" if complete and not needs_review else "review"
    except (ProofError, ValueError, RuntimeError, httpx.HTTPError, KeyError) as exc:
        item.status = "error"
        item.error = str(exc)[:500]
    finally:
        item.processed_at = datetime.now(timezone.utc)


@router.get("/webhooks/whatsapp", response_class=Response)
def verify_whatsapp(
    mode: str | None = Query(None, alias="hub.mode"),
    token: str | None = Query(None, alias="hub.verify_token"),
    challenge: str | None = Query(None, alias="hub.challenge"),
) -> Response:
    if mode == "subscribe" and settings.whatsapp_verify_token and hmac.compare_digest(
        token or "", settings.whatsapp_verify_token
    ):
        return Response(content=challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="WhatsApp webhook verification failed")


@router.post("/webhooks/whatsapp")
async def receive_whatsapp(request: Request, db: Session = Depends(get_db)) -> dict:
    body = await request.body()
    if not _valid_signature(body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=401, detail="Invalid WhatsApp signature")
    payload = await request.json()
    group_id = _group_id()
    for message in _messages(payload):
        message_id = message.get("id")
        sender = message.get("from")
        if not message_id or not sender:
            continue
        if db.scalar(select(WhatsAppInbound).where(WhatsAppInbound.wa_message_id == message_id)):
            continue
        media_id, filename, mime_type = _media_details(message)
        item = WhatsAppInbound(
            wa_message_id=message_id, group_id=group_id, sender_phone=sender,
            message_type=message.get("type", "unknown"), media_id=media_id,
            filename=filename, mime_type=mime_type, status="received", warnings=[],
        )
        db.add(item)
        db.flush()
        _process(item, db)
    db.commit()
    return {"received": True}


class WhatsAppReviewResponse(BaseModel):
    id: UUID
    wa_message_id: str
    sender_phone: str
    message_type: str
    filename: str | None
    status: str
    suggested_member_id: UUID | None
    payment_date: date | None
    amount_cents: int | None
    reference: str | None
    extraction_method: str | None
    warnings: list[str]
    error: str | None


@router.get("/groups/{group_id}/whatsapp/review", response_model=list[WhatsAppReviewResponse])
def whatsapp_review(group_id: UUID, db: Session = Depends(get_db)):
    return db.scalars(
        select(WhatsAppInbound)
        .where(WhatsAppInbound.group_id == group_id)
        .order_by(WhatsAppInbound.created_at.desc())
    ).all()
