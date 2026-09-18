import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.contributions.workflow import (
    PaymentConflict,
    PaymentInput,
    confirm_payment,
    mark_missed_month,
    preview_payment,
)
from app.ledger.service import group_balances
from app.db.session import get_db
from app.main import app
from app.models.contributions import ConfirmedPayment, FineSettlement, MemberMonth


def _missed_april_to_july(db, group_id, member_id):
    for month in range(4, 8):
        mark_missed_month(
            db, group_id, member_id, 2026, month, as_of=date(2026, 9, 18)
        )
    db.commit()


def test_review_and_confirm_real_payment_example(db, group_id):
    member_id = uuid.uuid4()
    _missed_april_to_july(db, group_id, member_id)
    request = PaymentInput(
        group_id=group_id,
        member_id=member_id,
        proof_key="sample-proof-1",
        payment_date=date(2026, 8, 31),
        reference="TEST MEMBER",
        amount_cents=60_000,
    )

    preview = preview_payment(db, request)
    assert (preview.contribution_year, preview.contribution_month) == (2026, 8)
    assert preview.allocation.fines_received_cents == 50_000
    assert preview.allocation.contribution_cents == 10_000
    assert [month.cleared for month in preview.missed_months] == [True] * 4
    assert db.scalar(select(func.count()).select_from(ConfirmedPayment)) == 0

    first = confirm_payment(db, request)
    db.commit()

    assert first.created is True
    assert db.scalar(select(func.count()).select_from(ConfirmedPayment)) == 1
    assert db.scalar(select(func.count()).select_from(FineSettlement)) == 4
    months = db.scalars(
        select(MemberMonth)
        .where(MemberMonth.group_id == group_id, MemberMonth.member_id == member_id)
        .order_by(MemberMonth.month)
    ).all()
    assert all(month.fine_paid_cents == 10_000 for month in months[:4])
    assert months[4].month == 8
    assert months[4].contribution_cents == 10_000
    assert sum(group_balances(db, group_id).values()) == 0

    replay = confirm_payment(db, request)
    db.commit()
    assert replay.created is False
    assert replay.payment_id == first.payment_id
    assert replay.preview == first.preview
    assert db.scalar(select(func.count()).select_from(ConfirmedPayment)) == 1


def test_partial_fine_payment_keeps_unpaid_months_red(db, group_id):
    member_id = uuid.uuid4()
    _missed_april_to_july(db, group_id, member_id)
    request = PaymentInput(
        group_id, member_id, "sample-proof-2", date(2026, 8, 31), "TEST", 25_000
    )

    confirmation = confirm_payment(db, request)
    db.commit()

    assert confirmation.preview.allocation.contribution_cents == 0
    assert [month.cleared for month in confirmation.preview.missed_months] == [
        True, True, False, False
    ]
    assert confirmation.preview.missed_months[2].fine_still_owed_cents == 5_000
    assert confirmation.preview.allocation.outstanding_fines_cents == 15_000


def test_cannot_mark_month_missed_before_cutoff(db, group_id):
    with pytest.raises(ValueError, match="not closed"):
        mark_missed_month(
            db, group_id, uuid.uuid4(), 2026, 8, as_of=date(2026, 9, 7)
        )


def test_unpaid_current_month_can_be_marked_missed_after_cutoff(db, group_id):
    member_id = uuid.uuid4()
    _missed_april_to_july(db, group_id, member_id)
    confirm_payment(
        db,
        PaymentInput(
            group_id, member_id, "sample-proof-3", date(2026, 8, 31), "TEST", 20_000
        ),
    )
    db.commit()

    august = mark_missed_month(
        db, group_id, member_id, 2026, 8, as_of=date(2026, 9, 8)
    )
    db.commit()

    assert august.was_missed is True
    assert august.fine_due_cents == 10_000
    assert august.contribution_cents == 0


def test_payment_api_previews_confirms_and_replays(db, group_id):
    member_id = uuid.uuid4()
    _missed_april_to_july(db, group_id, member_id)
    payload = {
        "group_id": str(group_id),
        "member_id": str(member_id),
        "proof_key": "sample-api-proof",
        "payment_date": "2026-08-31",
        "reference": "TEST MEMBER",
        "amount_cents": 60_000,
    }
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        preview = client.post("/payments/preview", json=payload)
        assert preview.status_code == 200
        assert preview.json()["allocation"]["fines_received_cents"] == 50_000

        confirmed = client.post("/payments/confirm", json=payload)
        assert confirmed.status_code == 200
        assert confirmed.json()["created"] is True

        replay = client.post("/payments/confirm", json=payload)
        assert replay.status_code == 200
        assert replay.json()["created"] is False
        assert replay.json()["payment_id"] == confirmed.json()["payment_id"]

        conflicting = client.post(
            "/payments/confirm", json={**payload, "amount_cents": 70_000}
        )
        assert conflicting.status_code == 409
        assert db.scalar(select(func.count()).select_from(ConfirmedPayment)) == 1
    finally:
        app.dependency_overrides.clear()


def test_second_payment_in_same_month_needs_rule_review(db, group_id):
    member_id = uuid.uuid4()
    first = PaymentInput(
        group_id, member_id, "first-proof", date(2026, 8, 31), "TEST", 30_000
    )
    confirm_payment(db, first)
    db.commit()

    second = PaymentInput(
        group_id, member_id, "second-proof", date(2026, 9, 1), "TEST", 30_000
    )
    with pytest.raises(PaymentConflict, match="split payments"):
        confirm_payment(db, second)
    assert db.scalar(select(func.count()).select_from(ConfirmedPayment)) == 1
