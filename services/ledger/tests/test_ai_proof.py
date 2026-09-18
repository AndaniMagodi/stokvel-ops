import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.contributions.ai_proof import extract_with_ai
from app.core.config import settings
from app.main import app


def test_ai_extracts_different_wording_without_posting(monkeypatch):
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps({"payment_date": "2026-08-31", "amount_cents": 170_000, "reference": "A MEMBER"})
            ))])

    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(
        "app.contributions.ai_proof.Groq",
        lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
    )
    result = extract_with_ai("Sent on 31 Aug 2026\nPaid out R1 700.00\nMy ref A MEMBER")
    assert result.payment_date == "2026-08-31"
    assert result.amount_cents == 170_000
    assert result.reference == "A MEMBER"
    assert calls[0]["model"] == "qwen/qwen3.8-27b"
    assert calls[0]["response_format"]["json_schema"]["strict"] is True


def test_ai_inspection_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(
        "app.api.contributions.extract_proof_text",
        lambda _: "Sent on 31 Aug 2026\nPaid out R1 700.00",
    )
    response = TestClient(app).post(
        "/payments/proof/inspect",
        data={"use_ai": "true"},
        files={"file": ("proof.png", b"sample")},
    )
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]
