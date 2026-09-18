"""Members and bank reference aliases used for review suggestions."""

import uuid

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Member(Base):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (Index("ix_members_group", "group_id"),)


class MemberReference(Base):
    __tablename__ = "member_references"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("members.id"), nullable=False)
    reference: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_reference: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (
        Index("uq_member_reference_group_normalized", "group_id", "normalized_reference", unique=True),
        Index("ix_member_references_member", "member_id"),
    )
