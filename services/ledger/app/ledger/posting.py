from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Leg:
    account_id: UUID
    amount_cents: int


@dataclass(frozen=True)
class PostingRequest:
    group_id: UUID
    kind: str
    idempotency_key: str
    legs: tuple[Leg, ...]
    occurred_at: datetime | None = None


@dataclass(frozen=True)
class PostingResult:
    transaction_id: UUID
    created: bool
