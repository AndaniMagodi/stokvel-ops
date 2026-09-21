"""Inbound WhatsApp messages awaiting treasurer review."""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WhatsAppInbound(Base):
    __tablename__ = "whatsapp_inbound"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    wa_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    sender_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False)
    media_id: Mapped[str | None] = mapped_column(String(200))
    filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="received")
    suggested_member_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())
    payment_date: Mapped[date | None] = mapped_column(Date())
    amount_cents: Mapped[int | None] = mapped_column(BigInteger())
    reference: Mapped[str | None] = mapped_column(String(200))
    extraction_method: Mapped[str | None] = mapped_column(String(30))
    warnings: Mapped[list] = mapped_column(JSONB(), nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_whatsapp_inbound_message", "wa_message_id", unique=True),
        Index("ix_whatsapp_inbound_group_status", "group_id", "status"),
    )
