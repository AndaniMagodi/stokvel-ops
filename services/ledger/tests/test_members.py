import uuid

from fastapi.testclient import TestClient

from app.contributions.members import (
    find_member_by_reference,
    match_member,
    normalize_sa_phone,
    register_member,
)
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
        updated = client.patch(
            f"/groups/{group_id}/members/{member_id}/first-expected-month",
            json={"year": 2026, "month": 8},
        )
        assert updated.status_code == 200
        assert updated.json()["first_expected_month"] == 8
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


def test_phone_and_reference_matching_handles_shared_numbers(db, group_id):
    first = register_member(
        db, group_id, "First", ["A FIRST"], contact_number="072 246 7235"
    )
    second = register_member(
        db, group_id, "Second", ["A SECOND"], contact_number="+27 72 246 7235"
    )
    unique = register_member(
        db, group_id, "Unique", ["A UNIQUE"], contact_number="0791678828"
    )
    db.commit()

    assert normalize_sa_phone("+27 79 167 8828") == "791678828"
    matched, method, review = match_member(
        db, group_id, reference="A SECOND", sender_phone="0722467235"
    )
    assert (matched.id, method, review) == (second.id, "phone_and_reference", False)
    matched, method, review = match_member(
        db, group_id, reference=None, sender_phone="0791678828"
    )
    assert (matched.id, method, review) == (unique.id, "phone", False)
    matched, method, review = match_member(
        db, group_id, reference=None, sender_phone="0722467235"
    )
    assert (matched, method, review) == (None, None, True)


def test_initial_and_surname_reference_resolves_shared_spreadsheet_phone(db, group_id):
    register_member(db, group_id, "Magodi Andani", [], contact_number="0791678828")
    expected = register_member(db, group_id, "Radzilani Elekanyani", [], contact_number="0791678828")
    db.commit()
    matched, method, review = match_member(
        db, group_id, reference="E RADZILANI", sender_phone="0791678828"
    )
    assert (matched.id, method, review) == (expected.id, "phone_and_reference", False)
    matched, method, review = match_member(
        db, group_id, reference="A FIRST", sender_phone="0791678828"
    )
    assert (matched, method, review) == (None, None, True)


def test_proof_inspection_matches_sender_phone_and_reference(db, group_id, monkeypatch):
    member = register_member(
        db, group_id, "Member", ["A MEMBER"], contact_number="0791678828"
    )
    db.commit()
    monkeypatch.setattr(
        "app.api.contributions.extract_proof_text",
        lambda _: "Payment Date 31/08/2026\nAmount R300.00\nReference A MEMBER",
    )
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).post(
            "/payments/proof/inspect",
            data={"group_id": str(group_id), "sender_phone": "+27 79 167 8828"},
            files={"file": ("proof.png", b"sample")},
        )
        assert response.status_code == 200
        assert response.json()["suggested_member_id"] == str(member.id)
        assert response.json()["match_method"] == "phone_and_reference"
        assert response.json()["match_needs_review"] is False
    finally:
        app.dependency_overrides.clear()
