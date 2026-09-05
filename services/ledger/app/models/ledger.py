import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    member_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="account")

    __table_args__ = (
        Index(
            "uq_accounts_group_kind_member",
            "group_id",
            "kind",
            "member_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_accounts_group_id", "group_id"),
    )


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reverses_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("ledger_transactions.id"), nullable=True
    )

    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="transaction")

    __table_args__ = (
        Index(
            "uq_ledger_transactions_group_idempotency",
            "group_id",
            "idempotency_key",
            unique=True,
        ),
        Index(
            "uq_ledger_transactions_reverses",
            "reverses_transaction_id",
            unique=True,
            postgresql_where=(reverses_transaction_id.isnot(None)),
        ),
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(BigInteger(), primary_key=True, autoincrement=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("ledger_transactions.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("accounts.id"), nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    transaction: Mapped["LedgerTransaction"] = relationship(back_populates="entries")
    account: Mapped["Account"] = relationship(back_populates="entries")

    __table_args__ = (
        CheckConstraint("amount_cents <> 0", name="ck_ledger_entries_nonzero"),
        Index("ix_ledger_entries_account_id", "account_id"),
        Index("ix_ledger_entries_transaction_id", "transaction_id"),
    )
