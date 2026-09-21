"""Normalized member contact number for POP sender matching.

Revision ID: 0006_member_contact_number
Revises: 0005_member_first_expected_month
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_member_contact_number"
down_revision = "0005_member_first_expected_month"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("members", sa.Column("contact_number", sa.String(20), nullable=True))
    op.create_index("ix_members_group_contact", "members", ["group_id", "contact_number"])


def downgrade() -> None:
    op.drop_index("ix_members_group_contact", table_name="members")
    op.drop_column("members", "contact_number")
