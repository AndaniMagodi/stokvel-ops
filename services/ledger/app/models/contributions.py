"""Treasurer records for reviewed payments and monthly allocations."""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MemberMonth(Base):
    __tablename__ = "member_months"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    month: Mapped[int] = mapped_column(nullable=False)
    was_missed: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    fine_due_cents: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0)
    fine_paid_cents: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0)
    contribution_cents: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0)

    __table_args__ = (
        Index("uq_member_month", "group_id", "member_id", "year", "month", unique=True),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_member_month_valid_month"),
        CheckConstraint("fine_due_cents >= 0", name="ck_member_month_fine_due"),
        CheckConstraint("fine_paid_cents >= 0 AND fine_paid_cents <= fine_due_cents", name="ck_member_month_fine_paid"),
        CheckConstraint("contribution_cents >= 0", name="ck_member_month_contribution"),
    )


class ConfirmedPayment(Base):
    __tablename__ = "confirmed_payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    proof_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date(), nullable=False)
    reference: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    contribution_year: Mapped[int] = mapped_column(nullable=False)
    contribution_month: Mapped[int] = mapped_column(nullable=False)
    old_fines_paid_cents: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    minimum_rule_fine_cents: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    contribution_cents: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    ledger_transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("ledger_transactions.id"), nullable=False
    )
    preview_snapshot: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("uq_confirmed_payment_proof", "group_id", "proof_key", unique=True),
        CheckConstraint("amount_cents > 0", name="ck_confirmed_payment_positive"),
        CheckConstraint("contribution_month BETWEEN 1 AND 12", name="ck_confirmed_payment_month"),
        CheckConstraint(
            "old_fines_paid_cents >= 0 AND minimum_rule_fine_cents >= 0 "
            "AND contribution_cents >= 0 AND "
            "old_fines_paid_cents + minimum_rule_fine_cents + contribution_cents = amount_cents",
            name="ck_confirmed_payment_allocation_balances",
        ),
    )


class FineSettlement(Base):
    __tablename__ = "fine_settlements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("confirmed_payments.id"), nullable=False
    )
    member_month_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("member_months.id"), nullable=False
    )
    fine_paid_cents: Mapped[int] = mapped_column(BigInteger(), nullable=False)

    __table_args__ = (
        Index("uq_fine_settlement_payment_month", "payment_id", "member_month_id", unique=True),
        CheckConstraint("fine_paid_cents > 0", name="ck_fine_settlement_positive"),
    )
