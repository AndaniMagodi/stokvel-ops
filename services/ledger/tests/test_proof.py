from fastapi.testclient import TestClient

from app.contributions.proof import suggest_proof_fields
from app.main import app


def test_suggest_labeled_fields_without_guessing_other_numbers():
    result = suggest_proof_fields(
        "Account Number 62930000000\nPayment Date 31/08/2026 19:43\n"
        "Amount R1 700.00\nReference A MEMBER\nSkyQR reference: abc"
    )
    assert result.payment_date == "2026-08-31"
    assert result.amount_cents == 170_000
    assert result.reference == "A MEMBER"
    assert len(result.warnings) == 1


def test_missing_fields_are_left_for_manual_entry():
    result = suggest_proof_fields("Account Number 12345\nBalance R900.00")
    assert result.payment_date is None
    assert result.amount_cents is None
    assert result.reference is None
    assert len(result.warnings) == 2


def test_inspect_route_rejects_non_proof_and_oversized_file():
    client = TestClient(app)
    for content in (b"not a proof", b"x" * (5 * 1024 * 1024 + 1)):
        response = client.post(
            "/payments/proof/inspect", files={"file": ("proof.pdf", content)}
        )
        assert response.status_code == 422
