"""Member's first month expected to contribute.

Revision ID: 0005_member_first_expected_month
Revises: 0004_member_directory
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_member_first_expected_month"
down_revision = "0004_member_directory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("members", sa.Column("first_expected_year", sa.Integer(), nullable=True))
    op.add_column("members", sa.Column("first_expected_month", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_member_first_expected_month", "members",
        "(first_expected_year IS NULL AND first_expected_month IS NULL) OR "
        "(first_expected_year IS NOT NULL AND first_expected_month BETWEEN 1 AND 12)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_member_first_expected_month", "members", type_="check")
    op.drop_column("members", "first_expected_month")
    op.drop_column("members", "first_expected_year")
