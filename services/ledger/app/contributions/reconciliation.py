"""Find whole months with no recorded payment after their cutoff."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contributions.periods import contribution_month
from app.contributions.workflow import mark_missed_month
from app.models.contributions import ConfirmedPayment, MemberMonth
from app.models.members import Member


@dataclass(frozen=True)
class MissingCandidate:
    member_id: UUID
    member_name: str
    year: int
    month: int
    fine_due_cents: int = 10_000


@dataclass(frozen=True)
class MissingReview:
    candidates: tuple[MissingCandidate, ...]
    unconfigured_members: tuple[UUID, ...]


def _month_number(year: int, month: int) -> int:
    return year * 12 + month - 1


def _year_month(number: int) -> tuple[int, int]:
    return divmod(number, 12)[0], divmod(number, 12)[1] + 1


def review_missed_months(db: Session, group_id: UUID, *, as_of: date) -> MissingReview:
    members = db.scalars(select(Member).where(Member.group_id == group_id).order_by(Member.name)).all()
    payments = db.scalars(select(ConfirmedPayment).where(ConfirmedPayment.group_id == group_id)).all()
    months = db.scalars(select(MemberMonth).where(MemberMonth.group_id == group_id)).all()
    paid = {(payment.member_id, payment.contribution_year, payment.contribution_month) for payment in payments}
    recorded = {(month.member_id, month.year, month.month): month for month in months}

    current_year, current_month = contribution_month(as_of)
    last_closed = _month_number(current_year, current_month) - 1
    candidates = []
    unconfigured = []
    for member in members:
        if member.first_expected_year is None or member.first_expected_month is None:
            unconfigured.append(member.id)
            continue
        first = _month_number(member.first_expected_year, member.first_expected_month)
        if last_closed - first > 120:
            raise ValueError("First expected month is more than 10 years before the latest closed month")
        for number in range(first, last_closed + 1):
            year, month = _year_month(number)
            record = recorded.get((member.id, year, month))
            if (member.id, year, month) in paid or (record and (record.was_missed or record.contribution_cents > 0)):
                continue
            candidates.append(MissingCandidate(member.id, member.name, year, month))
    return MissingReview(tuple(candidates), tuple(unconfigured))


def confirm_missed_months(db: Session, group_id: UUID, *, as_of: date) -> MissingReview:
    """Record the currently eligible candidates; caller commits atomically."""
    review = review_missed_months(db, group_id, as_of=as_of)
    for candidate in review.candidates:
        mark_missed_month(
            db, group_id, candidate.member_id,
            candidate.year, candidate.month, as_of=as_of,
        )
    return review
