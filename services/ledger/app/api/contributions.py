"""Local treasurer endpoints for manual payment review."""

from dataclasses import asdict, replace
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contributions.workflow import (
    PaymentConflict,
    PaymentInput,
    confirm_payment,
    mark_missed_month,
    preview_payment,
)
from app.contributions.proof import MAX_FILE_BYTES, ProofError, extract_proof_text, suggest_proof_fields
from app.contributions.ai_proof import AIProofUnavailable, extract_with_ai
from app.contributions.members import find_member_by_reference
from app.contributions.reconciliation import confirm_missed_months, review_missed_months
from app.db.session import get_db


router = APIRouter(tags=["contributions"])


class ProofSuggestionResponse(BaseModel):
    payment_date: date | None
    amount_cents: int | None
    reference: str | None
    suggested_member_id: UUID | None = None
    suggested_member_name: str | None = None
    extraction_method: str
    warnings: list[str]


@router.post("/payments/proof/inspect", response_model=ProofSuggestionResponse)
async def payment_proof_inspect(
    file: UploadFile = File(...),
    group_id: UUID | None = Form(None),
    use_ai: bool = Form(False),
    db: Session = Depends(get_db),
) -> ProofSuggestionResponse:
    data = await file.read(MAX_FILE_BYTES + 1)
    try:
        text = extract_proof_text(data)
        local = suggest_proof_fields(text)
        suggestion = local
        if use_ai:
            suggestion = extract_with_ai(text)
            if any(
                getattr(local, field) is not None
                and getattr(local, field) != getattr(suggestion, field)
                for field in ("payment_date", "amount_cents", "reference")
            ):
                suggestion = replace(
                    suggestion,
                    warnings=[*suggestion.warnings, "AI and local extraction differ; compare both with the proof."],
                )
    except ProofError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIProofUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    match = (
        find_member_by_reference(db, group_id, suggestion.reference)
        if group_id is not None and suggestion.reference else None
    )
    return ProofSuggestionResponse(
        **vars(suggestion),
        suggested_member_id=match.id if match else None,
        suggested_member_name=match.name if match else None,
        extraction_method="ai" if use_ai else "local",
    )


class PaymentRequest(BaseModel):
    group_id: UUID
    member_id: UUID
    proof_key: str = Field(min_length=1, max_length=200)
    payment_date: date
    reference: str = Field(min_length=1, max_length=200)
    amount_cents: int = Field(gt=0)

    def to_domain(self) -> PaymentInput:
        return PaymentInput(**self.model_dump())


class AllocationResponse(BaseModel):
    old_fines_paid_cents: int
    minimum_rule_fine_cents: int
    contribution_cents: int
    outstanding_fines_cents: int
    fines_received_cents: int


class MonthSettlementResponse(BaseModel):
    year: int
    month: int
    fine_paid_cents: int
    fine_still_owed_cents: int
    cleared: bool


class PreviewResponse(BaseModel):
    contribution_year: int
    contribution_month: int
    allocation: AllocationResponse
    missed_months: list[MonthSettlementResponse]


class ConfirmationResponse(BaseModel):
    payment_id: UUID
    created: bool
    preview: PreviewResponse


class MissedMonthRequest(BaseModel):
    group_id: UUID
    member_id: UUID
    year: int
    month: int = Field(ge=1, le=12)


class MissedMonthResponse(BaseModel):
    year: int
    month: int
    fine_due_cents: int
    fine_paid_cents: int
    cleared: bool


class MissingCandidateResponse(BaseModel):
    member_id: UUID
    member_name: str
    year: int
    month: int
    fine_due_cents: int


class MissingReviewResponse(BaseModel):
    candidates: list[MissingCandidateResponse]
    unconfigured_members: list[UUID]
    candidate_fines_cents: int


def _missing_response(review) -> MissingReviewResponse:
    return MissingReviewResponse(
        candidates=[asdict(item) for item in review.candidates],
        unconfigured_members=list(review.unconfigured_members),
        candidate_fines_cents=sum(item.fine_due_cents for item in review.candidates),
    )


def _today() -> date:
    return datetime.now(ZoneInfo("Africa/Johannesburg")).date()


@router.get("/groups/{group_id}/missed-months/review", response_model=MissingReviewResponse)
def missed_months_review(
    group_id: UUID, db: Session = Depends(get_db),
) -> MissingReviewResponse:
    try:
        return _missing_response(review_missed_months(db, group_id, as_of=_today()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/groups/{group_id}/missed-months/confirm", response_model=MissingReviewResponse)
def missed_months_confirm(
    group_id: UUID, db: Session = Depends(get_db),
) -> MissingReviewResponse:
    try:
        result = confirm_missed_months(db, group_id, as_of=_today())
        db.commit()
        return _missing_response(result)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Month changed during confirmation; review again") from exc


def _preview_response(preview) -> PreviewResponse:
    allocation = asdict(preview.allocation)
    allocation["fines_received_cents"] = preview.allocation.fines_received_cents
    return PreviewResponse(
        contribution_year=preview.contribution_year,
        contribution_month=preview.contribution_month,
        allocation=allocation,
        missed_months=[asdict(month) for month in preview.missed_months],
    )


@router.post("/missed-months", response_model=MissedMonthResponse)
def record_missed_month(
    request: MissedMonthRequest, db: Session = Depends(get_db)
) -> MissedMonthResponse:
    try:
        month = mark_missed_month(
            db,
            request.group_id,
            request.member_id,
            request.year,
            request.month,
            as_of=_today(),
        )
        db.commit()
    except PaymentConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Month already recorded") from exc
    return MissedMonthResponse(
        year=month.year,
        month=month.month,
        fine_due_cents=month.fine_due_cents,
        fine_paid_cents=month.fine_paid_cents,
        cleared=month.fine_due_cents == month.fine_paid_cents,
    )


@router.post("/payments/preview", response_model=PreviewResponse)
def payment_preview(
    request: PaymentRequest, db: Session = Depends(get_db)
) -> PreviewResponse:
    try:
        return _preview_response(preview_payment(db, request.to_domain()))
    except PaymentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/payments/confirm", response_model=ConfirmationResponse)
def payment_confirm(
    request: PaymentRequest, db: Session = Depends(get_db)
) -> ConfirmationResponse:
    try:
        result = confirm_payment(db, request.to_domain())
        db.commit()
    except PaymentConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Payment conflicts with existing data") from exc
    return ConfirmationResponse(
        payment_id=result.payment_id,
        created=result.created,
        preview=_preview_response(result.preview),
    )
