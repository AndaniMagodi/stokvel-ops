"""Read-only monthly contribution view for the treasurer."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contributions.periods import contribution_month
from app.models.contributions import ConfirmedPayment, FineSettlement, MemberMonth
from app.models.members import Member


@dataclass(frozen=True)
class MonthlyMemberStatus:
    member_id: UUID
    member_name: str
    status: str
    payment_received_cents: int
    contribution_cents: int
    fines_received_cents: int
    fine_due_cents: int
    fine_paid_cents: int


@dataclass(frozen=True)
class MonthlyReport:
    year: int
    month: int
    window_closed: bool
    members: tuple[MonthlyMemberStatus, ...]

    @property
    def payment_received_cents(self) -> int:
        return sum(item.payment_received_cents for item in self.members)

    @property
    def contribution_cents(self) -> int:
        return sum(item.contribution_cents for item in self.members)

    @property
    def fines_received_cents(self) -> int:
        return sum(item.fines_received_cents for item in self.members)


def _month_number(year: int, month: int) -> int:
    return year * 12 + month - 1


def monthly_report(
    db: Session, group_id: UUID, year: int, month: int, *, as_of: date,
) -> MonthlyReport:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    members = db.scalars(
        select(Member).where(Member.group_id == group_id).order_by(Member.name)
    ).all()
    records = db.scalars(
        select(MemberMonth).where(
            MemberMonth.group_id == group_id,
            MemberMonth.year == year,
            MemberMonth.month == month,
        )
    ).all()
    payments = db.scalars(
        select(ConfirmedPayment).where(
            ConfirmedPayment.group_id == group_id,
            ConfirmedPayment.contribution_year == year,
            ConfirmedPayment.contribution_month == month,
        )
    ).all()
    fine_settlements = db.execute(
        select(FineSettlement, MemberMonth)
        .join(MemberMonth, FineSettlement.member_month_id == MemberMonth.id)
        .where(
            MemberMonth.group_id == group_id,
            MemberMonth.year == year,
            MemberMonth.month == month,
        )
    ).all()
    by_member_record = {record.member_id: record for record in records}
    by_member_payment = {payment.member_id: payment for payment in payments}
    settled_fines_by_member: dict[UUID, int] = {}
    for settlement, missed_month in fine_settlements:
        settled_fines_by_member[missed_month.member_id] = (
            settled_fines_by_member.get(missed_month.member_id, 0)
            + settlement.fine_paid_cents
        )
    current_year, current_month = contribution_month(as_of)
    closed = _month_number(year, month) < _month_number(current_year, current_month)
    target = _month_number(year, month)

    statuses = []
    for member in members:
        record = by_member_record.get(member.id)
        payment = by_member_payment.get(member.id)
        first = (
            _month_number(member.first_expected_year, member.first_expected_month)
            if member.first_expected_year is not None and member.first_expected_month is not None
            else None
        )
        if first is None:
            status = "unconfigured"
        elif target < first:
            status = "not_expected"
        elif record is not None and record.was_missed:
            status = "green" if record.fine_paid_cents == record.fine_due_cents else "red"
        elif payment is not None or (record is not None and record.contribution_cents > 0):
            status = "normal"
        elif closed:
            status = "pending_review"
        else:
            status = "pending"
        statuses.append(
            MonthlyMemberStatus(
                member_id=member.id,
                member_name=member.name,
                status=status,
                payment_received_cents=payment.amount_cents if payment else 0,
                contribution_cents=record.contribution_cents if record else 0,
                # Old fines belong to the missed month they settle. This lets a
                # September payment backfill August's "Fine Received" cell.
                # The minimum-rule fine belongs to the current contribution month.
                fines_received_cents=(
                    settled_fines_by_member.get(member.id, 0)
                    + (payment.minimum_rule_fine_cents if payment else 0)
                ),
                fine_due_cents=record.fine_due_cents if record else 0,
                fine_paid_cents=record.fine_paid_cents if record else 0,
            )
        )
    return MonthlyReport(year, month, closed, tuple(statuses))
