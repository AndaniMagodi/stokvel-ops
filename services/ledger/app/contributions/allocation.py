"""Preview a payment split before the treasurer records it."""

from dataclasses import dataclass
from collections.abc import Sequence


MINIMUM_CONTRIBUTION_CENTS = 30_000
BELOW_MINIMUM_FINE_CENTS = 10_000


@dataclass(frozen=True)
class Allocation:
    old_fines_paid_cents: int
    minimum_rule_fine_cents: int
    contribution_cents: int
    outstanding_fines_cents: int

    @property
    def fines_received_cents(self) -> int:
        return self.old_fines_paid_cents + self.minimum_rule_fine_cents


@dataclass(frozen=True)
class MissedMonth:
    year: int
    month: int
    outstanding_fine_cents: int


@dataclass(frozen=True)
class MonthSettlement:
    year: int
    month: int
    fine_paid_cents: int
    fine_still_owed_cents: int
    cleared: bool


def allocate_payment(payment_cents: int, outstanding_fines_cents: int) -> Allocation:
    """Split a confirmed payment into fines and this month's contribution.

    Amounts are integer cents. This only calculates a preview; it does not
    update monthly cells, store a POP, or post to the ledger.
    """
    if payment_cents <= 0:
        raise ValueError("payment_cents must be positive")
    if outstanding_fines_cents < 0:
        raise ValueError("outstanding_fines_cents cannot be negative")

    old_fines_paid = min(payment_cents, outstanding_fines_cents)
    fines_still_owed = outstanding_fines_cents - old_fines_paid
    remaining = payment_cents - old_fines_paid

    # If old fines use the whole payment, there is no current contribution to
    # test against the R300 minimum. Any unpaid old fine carries forward.
    minimum_rule_fine = 0
    if 0 < remaining < MINIMUM_CONTRIBUTION_CENTS:
        if remaining < BELOW_MINIMUM_FINE_CENTS:
            raise ValueError(
                "Remainder is below R100; confirm how this payment should be allocated"
            )
        minimum_rule_fine = BELOW_MINIMUM_FINE_CENTS

    return Allocation(
        old_fines_paid_cents=old_fines_paid,
        minimum_rule_fine_cents=minimum_rule_fine,
        contribution_cents=remaining - minimum_rule_fine,
        outstanding_fines_cents=fines_still_owed,
    )


def settle_missed_months(
    months: Sequence[MissedMonth], old_fines_paid_cents: int
) -> tuple[MonthSettlement, ...]:
    """Show which red months an old-fine payment clears, oldest first.

    The returned settlements are a preview. No month record is changed here.
    """
    if old_fines_paid_cents < 0:
        raise ValueError("old_fines_paid_cents cannot be negative")
    if any(month.outstanding_fine_cents <= 0 for month in months):
        raise ValueError("Each missed month must have an outstanding fine")
    if old_fines_paid_cents > sum(month.outstanding_fine_cents for month in months):
        raise ValueError("Fine payment exceeds the missed months' outstanding fines")

    remaining_payment = old_fines_paid_cents
    settlements = []
    for month in sorted(months, key=lambda item: (item.year, item.month)):
        paid = min(remaining_payment, month.outstanding_fine_cents)
        still_owed = month.outstanding_fine_cents - paid
        settlements.append(
            MonthSettlement(
                year=month.year,
                month=month.month,
                fine_paid_cents=paid,
                fine_still_owed_cents=still_owed,
                cleared=still_owed == 0,
            )
        )
        remaining_payment -= paid

    return tuple(settlements)
