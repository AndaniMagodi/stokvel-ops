import pytest

from app.contributions.allocation import (
    Allocation,
    MissedMonth,
    allocate_payment,
    settle_missed_months,
)


def test_payment_with_four_missed_months_and_below_minimum_remainder():
    result = allocate_payment(payment_cents=60_000, outstanding_fines_cents=40_000)

    assert result == Allocation(
        old_fines_paid_cents=40_000,
        minimum_rule_fine_cents=10_000,
        contribution_cents=10_000,
        outstanding_fines_cents=0,
    )
    assert result.fines_received_cents == 50_000


def test_payment_smaller_than_old_fines_carries_the_unpaid_amount():
    result = allocate_payment(payment_cents=20_000, outstanding_fines_cents=40_000)

    assert result.old_fines_paid_cents == 20_000
    assert result.minimum_rule_fine_cents == 0
    assert result.contribution_cents == 0
    assert result.outstanding_fines_cents == 20_000


def test_payment_at_minimum_has_no_new_fine():
    result = allocate_payment(payment_cents=30_000, outstanding_fines_cents=0)

    assert result.contribution_cents == 30_000
    assert result.fines_received_cents == 0


def test_remainder_below_fine_requires_a_rule_before_allocation():
    with pytest.raises(ValueError, match="below R100"):
        allocate_payment(payment_cents=5_000, outstanding_fines_cents=0)


def test_old_fine_payment_clears_earliest_missed_months_first():
    months = (
        MissedMonth(2026, 5, 10_000),
        MissedMonth(2026, 6, 10_000),
        MissedMonth(2026, 7, 10_000),
    )

    result = settle_missed_months(months, old_fines_paid_cents=25_000)

    assert [(item.month, item.fine_paid_cents, item.cleared) for item in result] == [
        (5, 10_000, True),
        (6, 10_000, True),
        (7, 5_000, False),
    ]
    assert result[-1].fine_still_owed_cents == 5_000
    assert months[-1].outstanding_fine_cents == 10_000


def test_missed_months_are_settled_in_date_order_even_if_input_is_not():
    months = (
        MissedMonth(2027, 1, 10_000),
        MissedMonth(2026, 12, 10_000),
    )

    result = settle_missed_months(months, old_fines_paid_cents=10_000)

    assert [(item.year, item.month, item.cleared) for item in result] == [
        (2026, 12, True),
        (2027, 1, False),
    ]
