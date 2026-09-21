"""Stokvel groups that own members and financial records."""

import uuid

from sqlalchemy import Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StokvelGroup(Base):
    __tablename__ = "stokvel_groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (
        Index("uq_stokvel_group_normalized_name", "normalized_name", unique=True),
    )
