import hashlib
import hmac
import json
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.whatsapp import WhatsAppInbound


def _signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_verification(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", "verify-me")
    client = TestClient(app)
    response = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"},
    )
    assert response.status_code == 200
    assert response.text == "12345"
    assert client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"},
    ).status_code == 403


def test_signed_message_is_stored_once_for_review(db, group_id, monkeypatch):
    secret = "app-secret"
    monkeypatch.setattr(settings, "whatsapp_app_secret", secret)
    monkeypatch.setattr(settings, "whatsapp_group_id", str(group_id))
    payload = {
        "entry": [{"changes": [{"value": {"messages": [{
            "id": "wamid.abc", "from": "27791234567", "type": "text",
            "text": {"body": "payment sent"},
        }]}}]}]
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        headers = {"content-type": "application/json", "x-hub-signature-256": _signature(body, secret)}
        first = client.post("/webhooks/whatsapp", content=body, headers=headers)
        second = client.post("/webhooks/whatsapp", content=body, headers=headers)
        assert first.status_code == second.status_code == 200
        assert db.scalar(select(func.count()).select_from(WhatsAppInbound)) == 1
        item = db.scalar(select(WhatsAppInbound))
        assert item.status == "ignored"
        assert item.sender_phone == "27791234567"

        review = client.get(f"/groups/{group_id}/whatsapp/review")
        assert review.status_code == 200
        assert review.json()[0]["wa_message_id"] == "wamid.abc"
    finally:
        app.dependency_overrides.clear()


def test_invalid_signature_is_rejected(db, group_id, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", "secret")
    monkeypatch.setattr(settings, "whatsapp_group_id", str(group_id))
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).post(
            "/webhooks/whatsapp", json={"entry": []},
            headers={"x-hub-signature-256": "sha256=bad"},
        )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
