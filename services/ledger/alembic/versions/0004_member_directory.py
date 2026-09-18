"""Member directory and unique payment reference aliases.

Revision ID: 0004_member_directory
Revises: 0003_payment_allocation_check
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_member_directory"
down_revision = "0003_payment_allocation_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
    )
    op.create_index("ix_members_group", "members", ["group_id"])
    op.create_table(
        "member_references",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), sa.ForeignKey("members.id"), nullable=False),
        sa.Column("reference", sa.String(200), nullable=False),
        sa.Column("normalized_reference", sa.String(200), nullable=False),
    )
    op.create_index("ix_member_references_member", "member_references", ["member_id"])
    op.create_index(
        "uq_member_reference_group_normalized", "member_references",
        ["group_id", "normalized_reference"], unique=True,
    )


def downgrade() -> None:
    op.drop_table("member_references")
    op.drop_table("members")
