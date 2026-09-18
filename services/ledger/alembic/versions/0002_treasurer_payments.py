"""Treasurer month and confirmed-payment records.

Revision ID: 0002_treasurer_payments
Revises: 0001_ledger_substrate
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0002_treasurer_payments"
down_revision = "0001_ledger_substrate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_months",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("was_missed", sa.Boolean(), nullable=False),
        sa.Column("fine_due_cents", sa.BigInteger(), nullable=False),
        sa.Column("fine_paid_cents", sa.BigInteger(), nullable=False),
        sa.Column("contribution_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_member_month_valid_month"),
        sa.CheckConstraint("fine_due_cents >= 0", name="ck_member_month_fine_due"),
        sa.CheckConstraint("fine_paid_cents >= 0 AND fine_paid_cents <= fine_due_cents", name="ck_member_month_fine_paid"),
        sa.CheckConstraint("contribution_cents >= 0", name="ck_member_month_contribution"),
    )
    op.create_index(
        "uq_member_month", "member_months",
        ["group_id", "member_id", "year", "month"], unique=True,
    )

    op.create_table(
        "confirmed_payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("proof_key", sa.String(200), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(200), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("contribution_year", sa.Integer(), nullable=False),
        sa.Column("contribution_month", sa.Integer(), nullable=False),
        sa.Column("old_fines_paid_cents", sa.BigInteger(), nullable=False),
        sa.Column("minimum_rule_fine_cents", sa.BigInteger(), nullable=False),
        sa.Column("contribution_cents", sa.BigInteger(), nullable=False),
        sa.Column("ledger_transaction_id", sa.Uuid(), sa.ForeignKey("ledger_transactions.id"), nullable=False),
        sa.Column("preview_snapshot", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="ck_confirmed_payment_positive"),
        sa.CheckConstraint("contribution_month BETWEEN 1 AND 12", name="ck_confirmed_payment_month"),
    )
    op.create_index(
        "uq_confirmed_payment_proof", "confirmed_payments",
        ["group_id", "proof_key"], unique=True,
    )

    op.create_table(
        "fine_settlements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("payment_id", sa.Uuid(), sa.ForeignKey("confirmed_payments.id"), nullable=False),
        sa.Column("member_month_id", sa.Uuid(), sa.ForeignKey("member_months.id"), nullable=False),
        sa.Column("fine_paid_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("fine_paid_cents > 0", name="ck_fine_settlement_positive"),
    )
    op.create_index(
        "uq_fine_settlement_payment_month", "fine_settlements",
        ["payment_id", "member_month_id"], unique=True,
    )


def downgrade() -> None:
    op.drop_table("fine_settlements")
    op.drop_table("confirmed_payments")
    op.drop_table("member_months")
