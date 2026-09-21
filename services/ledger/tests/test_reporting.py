from datetime import date

from fastapi.testclient import TestClient

from app.contributions.members import register_member
from app.contributions.reporting import monthly_report
from app.contributions.workflow import PaymentInput, confirm_payment, mark_missed_month
from app.db.session import get_db
from app.main import app


def test_monthly_report_uses_spreadsheet_colour_rules(db, group_id):
    cleared = register_member(
        db, group_id, "Cleared", ["CLEARED"],
        first_expected_year=2026, first_expected_month=7,
    )
    red = register_member(
        db, group_id, "Red", ["RED"],
        first_expected_year=2026, first_expected_month=7,
    )
    pending = register_member(
        db, group_id, "Pending review", ["PENDING"],
        first_expected_year=2026, first_expected_month=7,
    )
    future = register_member(
        db, group_id, "Future", ["FUTURE"],
        first_expected_year=2026, first_expected_month=9,
    )
    register_member(db, group_id, "Unconfigured", ["UNKNOWN"])
    db.commit()
    mark_missed_month(db, group_id, cleared.id, 2026, 7, as_of=date(2026, 9, 18))
    mark_missed_month(db, group_id, red.id, 2026, 7, as_of=date(2026, 9, 18))
    db.commit()
    confirm_payment(
        db, PaymentInput(group_id, cleared.id, "clear-july", date(2026, 8, 31), "CLEARED", 40_000)
    )
    db.commit()

    july = monthly_report(db, group_id, 2026, 7, as_of=date(2026, 9, 18))
    by_name = {item.member_name: item for item in july.members}
    assert by_name["Cleared"].status == "green"
    assert by_name["Red"].status == "red"
    assert by_name["Pending review"].status == "pending_review"
    assert by_name["Future"].status == "not_expected"
    assert by_name["Unconfigured"].status == "unconfigured"
    assert july.window_closed is True

    august = monthly_report(db, group_id, 2026, 8, as_of=date(2026, 9, 18))
    august_cleared = next(item for item in august.members if item.member_id == cleared.id)
    assert august_cleared.status == "normal"
    assert august_cleared.payment_received_cents == 40_000
    assert august_cleared.contribution_cents == 30_000
    assert august_cleared.fines_received_cents == 10_000
    assert august.payment_received_cents == 40_000
    assert august.contribution_cents == 30_000
    assert august.fines_received_cents == 10_000


def test_current_open_month_without_payment_is_pending(db, group_id):
    member = register_member(
        db, group_id, "Member", ["MEMBER"],
        first_expected_year=2026, first_expected_month=9,
    )
    db.commit()
    report = monthly_report(db, group_id, 2026, 9, as_of=date(2026, 9, 21))
    assert report.window_closed is False
    assert report.members[0].member_id == member.id
    assert report.members[0].status == "pending"


def test_monthly_report_api(db, group_id, monkeypatch):
    register_member(
        db, group_id, "Member", ["MEMBER"],
        first_expected_year=2026, first_expected_month=8,
    )
    db.commit()
    monkeypatch.setattr("app.api.reports._today", lambda: date(2026, 9, 21))
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get(f"/groups/{group_id}/months/2026/8")
        assert response.status_code == 200
        assert response.json()["members"][0]["status"] == "pending_review"
        invalid = TestClient(app).get(f"/groups/{group_id}/months/2026/13")
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()
