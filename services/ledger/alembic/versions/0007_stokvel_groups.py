"""Named stokvel groups.

Revision ID: 0007_stokvel_groups
Revises: 0006_member_contact_number
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_stokvel_groups"
down_revision = "0006_member_contact_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stokvel_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
    )
    op.create_index(
        "uq_stokvel_group_normalized_name", "stokvel_groups",
        ["normalized_name"], unique=True,
    )


def downgrade() -> None:
    op.drop_table("stokvel_groups")
