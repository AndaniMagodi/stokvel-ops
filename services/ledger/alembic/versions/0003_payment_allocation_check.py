"""Require confirmed payment allocations to add up to the amount received.

Revision ID: 0003_payment_allocation_check
Revises: 0002_treasurer_payments
"""

from alembic import op


revision = "0003_payment_allocation_check"
down_revision = "0002_treasurer_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_confirmed_payment_allocation_balances",
        "confirmed_payments",
        "old_fines_paid_cents >= 0 AND minimum_rule_fine_cents >= 0 "
        "AND contribution_cents >= 0 AND "
        "old_fines_paid_cents + minimum_rule_fine_cents + contribution_cents = amount_cents",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_confirmed_payment_allocation_balances",
        "confirmed_payments",
        type_="check",
    )
