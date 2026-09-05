from uuid import UUID

from sqlalchemy.orm import Session

from app.ledger.posting import PostingRequest, PostingResult


def post_transaction(db: Session, request: PostingRequest) -> PostingResult:
    raise NotImplementedError


def account_balance(db: Session, account_id: UUID) -> int:
    raise NotImplementedError


def group_balances(db: Session, group_id: UUID) -> dict[UUID, int]:
    raise NotImplementedError


def reverse_transaction(
    db: Session, transaction_id: UUID, idempotency_key: str
) -> PostingResult:
    raise NotImplementedError
