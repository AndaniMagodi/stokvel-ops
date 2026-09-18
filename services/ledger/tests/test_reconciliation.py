from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.contributions.members import register_member
from app.contributions.reconciliation import confirm_missed_months, review_missed_months
from app.contributions.workflow import PaymentInput, confirm_payment, mark_missed_month
from app.db.session import get_db
from app.main import app
from app.models.contributions import MemberMonth


def test_cutoff_and_unrecorded_members_are_reviewed_before_writing(db, group_id):
    first = register_member(
        db, group_id, "First", ["FIRST"],
        first_expected_year=2026, first_expected_month=7,
    )
    second = register_member(
        db, group_id, "Second", ["SECOND"],
        first_expected_year=2026, first_expected_month=8,
    )
    unconfigured = register_member(db, group_id, "Unconfigured", ["OTHER"])
    db.commit()
    confirm_payment(
        db, PaymentInput(group_id, second.id, "proof-second", date(2026, 8, 31), "SECOND", 30_000)
    )
    db.commit()

    before_cutoff = review_missed_months(db, group_id, as_of=date(2026, 9, 7))
    assert [(item.member_id, item.year, item.month) for item in before_cutoff.candidates] == [
        (first.id, 2026, 7)
    ]
    assert before_cutoff.unconfigured_members == (unconfigured.id,)
    assert db.scalar(select(func.count()).select_from(MemberMonth)) == 1

    after_cutoff = review_missed_months(db, group_id, as_of=date(2026, 9, 8))
    assert [(item.member_id, item.year, item.month) for item in after_cutoff.candidates] == [
        (first.id, 2026, 7), (first.id, 2026, 8)
    ]
    recorded = confirm_missed_months(db, group_id, as_of=date(2026, 9, 8))
    db.commit()
    assert len(recorded.candidates) == 2
    assert confirm_missed_months(db, group_id, as_of=date(2026, 9, 8)).candidates == ()
    db.commit()
    assert db.scalar(select(func.count()).select_from(MemberMonth)) == 3


def test_payment_applied_to_old_fine_still_counts_as_payment_for_window(db, group_id):
    member = register_member(
        db, group_id, "Member", ["MEMBER"],
        first_expected_year=2026, first_expected_month=8,
    )
    db.commit()
    mark_missed_month(db, group_id, member.id, 2026, 7, as_of=date(2026, 9, 18))
    db.commit()
    confirm_payment(
        db, PaymentInput(group_id, member.id, "fine-only", date(2026, 8, 31), "MEMBER", 10_000)
    )
    db.commit()

    review = review_missed_months(db, group_id, as_of=date(2026, 9, 18))
    assert review.candidates == ()


def test_group_review_api_requires_explicit_confirmation(db, group_id, monkeypatch):
    member = register_member(
        db, group_id, "Member", ["MEMBER"],
        first_expected_year=2026, first_expected_month=8,
    )
    db.commit()
    monkeypatch.setattr("app.api.contributions._today", lambda: date(2026, 9, 18))
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        review = client.get(f"/groups/{group_id}/missed-months/review")
        assert review.status_code == 200
        assert review.json()["candidate_fines_cents"] == 10_000
        assert review.json()["candidates"][0]["member_id"] == str(member.id)
        assert db.scalar(select(func.count()).select_from(MemberMonth)) == 0

        confirmed = client.post(f"/groups/{group_id}/missed-months/confirm")
        assert confirmed.status_code == 200
        assert confirmed.json()["candidate_fines_cents"] == 10_000
        replay = client.post(f"/groups/{group_id}/missed-months/confirm")
        assert replay.status_code == 200
        assert replay.json()["candidates"] == []
        assert db.scalar(select(func.count()).select_from(MemberMonth)) == 1
    finally:
        app.dependency_overrides.clear()
