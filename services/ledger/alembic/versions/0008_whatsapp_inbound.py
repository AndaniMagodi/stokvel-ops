"""add WhatsApp inbound review queue

Revision ID: 0008_whatsapp_inbound
Revises: 0007_stokvel_groups
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_whatsapp_inbound"
down_revision = "0007_stokvel_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_inbound",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("wa_message_id", sa.String(200), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("sender_phone", sa.String(30), nullable=False),
        sa.Column("message_type", sa.String(30), nullable=False),
        sa.Column("media_id", sa.String(200)),
        sa.Column("filename", sa.String(255)),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("suggested_member_id", sa.Uuid()),
        sa.Column("payment_date", sa.Date()),
        sa.Column("amount_cents", sa.BigInteger()),
        sa.Column("reference", sa.String(200)),
        sa.Column("extraction_method", sa.String(30)),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("uq_whatsapp_inbound_message", "whatsapp_inbound", ["wa_message_id"], unique=True)
    op.create_index("ix_whatsapp_inbound_group_status", "whatsapp_inbound", ["group_id", "status"])


def downgrade() -> None:
    op.drop_table("whatsapp_inbound")
