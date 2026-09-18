import uuid

from fastapi.testclient import TestClient

from app.contributions.members import find_member_by_reference
from app.db.session import get_db
from app.main import app


def test_member_registration_and_exact_reference_suggestion(db, group_id, monkeypatch):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        created = client.post(
            "/members",
            json={"group_id": str(group_id), "name": "Test Member", "references": ["A MEMBER"]},
        )
        assert created.status_code == 201
        member_id = created.json()["id"]
        assert find_member_by_reference(db, group_id, "AMEMBER").id == uuid.UUID(member_id)
        assert find_member_by_reference(db, uuid.uuid4(), "A MEMBER") is None

        monkeypatch.setattr(
            "app.api.contributions.extract_proof_text",
            lambda _: "Payment Date 31/08/2026\nAmount R300.00\nReference AMEMBER",
        )
        inspected = client.post(
            "/payments/proof/inspect",
            data={"group_id": str(group_id)},
            files={"file": ("proof.png", b"sample")},
        )
        assert inspected.status_code == 200
        assert inspected.json()["suggested_member_id"] == member_id
        assert inspected.json()["suggested_member_name"] == "Test Member"

        listed = client.get(f"/groups/{group_id}/members")
        assert listed.status_code == 200
        assert listed.json()[0]["references"] == ["A MEMBER"]
    finally:
        app.dependency_overrides.clear()


def test_duplicate_alias_cannot_be_assigned_to_another_member(db, group_id):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        first = client.post(
            "/members", json={"group_id": str(group_id), "name": "One", "references": ["A MEMBER"]}
        )
        second = client.post(
            "/members", json={"group_id": str(group_id), "name": "Two", "references": ["AMEMBER"]}
        )
        assert first.status_code == 201
        assert second.status_code == 409
        assert len(client.get(f"/groups/{group_id}/members").json()) == 1
    finally:
        app.dependency_overrides.clear()
