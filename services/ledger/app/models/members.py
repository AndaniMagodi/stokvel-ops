"""Members and bank reference aliases used for review suggestions."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Member(Base):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    first_expected_year: Mapped[int | None] = mapped_column(nullable=True)
    first_expected_month: Mapped[int | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ix_members_group", "group_id"),
        CheckConstraint(
            "(first_expected_year IS NULL AND first_expected_month IS NULL) OR "
            "(first_expected_year IS NOT NULL AND first_expected_month BETWEEN 1 AND 12)",
            name="ck_member_first_expected_month",
        ),
    )


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
