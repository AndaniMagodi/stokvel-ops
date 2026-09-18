"""Manual POP review followed by an auditable payment confirmation."""

from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contributions.allocation import (
    Allocation,
    MissedMonth,
    MonthSettlement,
    allocate_payment,
    settle_missed_months,
)
from app.contributions.periods import contribution_month
from app.ledger.accounts import ensure_account
from app.ledger.posting import Leg, PostingRequest
from app.ledger.service import post_transaction
from app.models.contributions import ConfirmedPayment, FineSettlement, MemberMonth


FINE_PER_MISSED_MONTH_CENTS = 10_000


class PaymentConflict(ValueError):
    """A proof or monthly record conflicts with an existing payment."""


@dataclass(frozen=True)
class PaymentInput:
    group_id: UUID
    member_id: UUID
    proof_key: str
    payment_date: date
    reference: str
    amount_cents: int


@dataclass(frozen=True)
class PaymentPreview:
    contribution_year: int
    contribution_month: int
    allocation: Allocation
    missed_months: tuple[MonthSettlement, ...]


@dataclass(frozen=True)
class Confirmation:
    payment_id: UUID
    created: bool
    preview: PaymentPreview


def _missed_months(db: Session, request: PaymentInput, *, lock: bool) -> list[MemberMonth]:
    year, month = contribution_month(request.payment_date)
    stmt = (
        select(MemberMonth)
        .where(
            MemberMonth.group_id == request.group_id,
            MemberMonth.member_id == request.member_id,
            MemberMonth.was_missed.is_(True),
            MemberMonth.fine_due_cents > MemberMonth.fine_paid_cents,
            (MemberMonth.year < year)
            | ((MemberMonth.year == year) & (MemberMonth.month < month)),
        )
        .order_by(MemberMonth.year, MemberMonth.month)
    )
    if lock:
        stmt = stmt.with_for_update()
    return list(db.scalars(stmt))


def _preview_from_months(
    request: PaymentInput, missed: list[MemberMonth]
) -> PaymentPreview:
    year, month = contribution_month(request.payment_date)
    fine_due = sum(item.fine_due_cents - item.fine_paid_cents for item in missed)
    allocation = allocate_payment(request.amount_cents, fine_due)
    settlements = settle_missed_months(
        tuple(
            MissedMonth(item.year, item.month, item.fine_due_cents - item.fine_paid_cents)
            for item in missed
        ),
        allocation.old_fines_paid_cents,
    )
    return PaymentPreview(year, month, allocation, settlements)


def preview_payment(db: Session, request: PaymentInput) -> PaymentPreview:
    """Read current dues and calculate a preview without writing anything."""
    year, month = contribution_month(request.payment_date)
    current = db.scalar(
        select(MemberMonth).where(
            MemberMonth.group_id == request.group_id,
            MemberMonth.member_id == request.member_id,
            MemberMonth.year == year,
            MemberMonth.month == month,
        )
    )
    if current is not None and current.contribution_cents:
        raise PaymentConflict(
            "A contribution already exists for this month; split payments need review"
        )
    missed = _missed_months(db, request, lock=False)
    return _preview_from_months(request, missed)


def mark_missed_month(
    db: Session,
    group_id: UUID,
    member_id: UUID,
    year: int,
    month: int,
    *,
    as_of: date,
) -> MemberMonth:
    """Record an unpaid month after its 7th-of-next-month cutoff."""
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    next_year = year + (month == 12)
    next_month = month % 12 + 1
    if as_of <= date(next_year, next_month, 7):
        raise ValueError("The contribution window has not closed")

    record = db.scalar(
        select(MemberMonth).where(
            MemberMonth.group_id == group_id,
            MemberMonth.member_id == member_id,
            MemberMonth.year == year,
            MemberMonth.month == month,
        )
    )
    if record is not None:
        if record.contribution_cents > 0:
            raise PaymentConflict("A contribution is already recorded for this month")
        if not record.was_missed:
            record.was_missed = True
            record.fine_due_cents = FINE_PER_MISSED_MONTH_CENTS
            db.flush()
        return record

    record = MemberMonth(
        group_id=group_id,
        member_id=member_id,
        year=year,
        month=month,
        was_missed=True,
        fine_due_cents=FINE_PER_MISSED_MONTH_CENTS,
        fine_paid_cents=0,
        contribution_cents=0,
    )
    db.add(record)
    db.flush()
    return record


def _matches_existing(existing: ConfirmedPayment, request: PaymentInput) -> bool:
    return (
        existing.member_id == request.member_id
        and existing.payment_date == request.payment_date
        and existing.reference == request.reference
        and existing.amount_cents == request.amount_cents
    )


def _saved_preview(payment: ConfirmedPayment) -> PaymentPreview:
    snapshot = payment.preview_snapshot
    return PaymentPreview(
        snapshot["contribution_year"],
        snapshot["contribution_month"],
        Allocation(**snapshot["allocation"]),
        tuple(MonthSettlement(**item) for item in snapshot["missed_months"]),
    )


def confirm_payment(db: Session, request: PaymentInput) -> Confirmation:
    """Post a reviewed payment; the caller commits the entire DB transaction."""
    if not request.proof_key.strip() or not request.reference.strip():
        raise ValueError("proof_key and reference are required")

    existing = db.scalar(
        select(ConfirmedPayment).where(
            ConfirmedPayment.group_id == request.group_id,
            ConfirmedPayment.proof_key == request.proof_key,
        )
    )
    if existing is not None:
        if not _matches_existing(existing, request):
            raise PaymentConflict("This proof key belongs to a different payment")
        return Confirmation(existing.id, False, _saved_preview(existing))

    missed = _missed_months(db, request, lock=True)
    preview = _preview_from_months(request, missed)
    current = db.scalar(
        select(MemberMonth).where(
            MemberMonth.group_id == request.group_id,
            MemberMonth.member_id == request.member_id,
            MemberMonth.year == preview.contribution_year,
            MemberMonth.month == preview.contribution_month,
        ).with_for_update()
    )
    if current is not None and current.contribution_cents:
        raise PaymentConflict(
            "A contribution already exists for this month; split payments need review"
        )

    external = ensure_account(db, request.group_id, "external")
    legs = [Leg(external.id, -request.amount_cents)]
    if preview.allocation.contribution_cents:
        contribution = ensure_account(
            db, request.group_id, "member_contributions", request.member_id
        )
        legs.append(Leg(contribution.id, preview.allocation.contribution_cents))
    if preview.allocation.fines_received_cents:
        fines = ensure_account(db, request.group_id, "fine_income")
        legs.append(Leg(fines.id, preview.allocation.fines_received_cents))

    proof_hash = sha256(request.proof_key.encode("utf-8")).hexdigest()
    posted = post_transaction(
        db,
        PostingRequest(
            group_id=request.group_id,
            kind="contribution_payment",
            idempotency_key=f"payment:{proof_hash}",
            legs=tuple(legs),
        ),
    )
    if not posted.created:
        raise PaymentConflict("Ledger posting already exists for this proof")

    payment = ConfirmedPayment(
        group_id=request.group_id,
        member_id=request.member_id,
        proof_key=request.proof_key,
        payment_date=request.payment_date,
        reference=request.reference,
        amount_cents=request.amount_cents,
        contribution_year=preview.contribution_year,
        contribution_month=preview.contribution_month,
        old_fines_paid_cents=preview.allocation.old_fines_paid_cents,
        minimum_rule_fine_cents=preview.allocation.minimum_rule_fine_cents,
        contribution_cents=preview.allocation.contribution_cents,
        ledger_transaction_id=posted.transaction_id,
        preview_snapshot=asdict(preview),
    )
    db.add(payment)
    db.flush()

    by_month = {(item.year, item.month): item for item in missed}
    for settlement in preview.missed_months:
        if not settlement.fine_paid_cents:
            continue
        month_record = by_month[(settlement.year, settlement.month)]
        month_record.fine_paid_cents += settlement.fine_paid_cents
        db.add(
            FineSettlement(
                payment_id=payment.id,
                member_month_id=month_record.id,
                fine_paid_cents=settlement.fine_paid_cents,
            )
        )

    if current is None:
        current = MemberMonth(
            group_id=request.group_id,
            member_id=request.member_id,
            year=preview.contribution_year,
            month=preview.contribution_month,
            was_missed=False,
            fine_due_cents=0,
            fine_paid_cents=0,
            contribution_cents=0,
        )
        db.add(current)
    current.contribution_cents += preview.allocation.contribution_cents
    db.flush()
    return Confirmation(payment.id, True, preview)
