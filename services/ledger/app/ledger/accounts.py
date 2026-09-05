from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ledger import Account


def ensure_account(
    db: Session,
    group_id: UUID,
    kind: str,
    member_id: UUID | None = None,
    currency: str | None = None,
) -> Account:
    raise NotImplementedError
