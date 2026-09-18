from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ledger import Account


def ensure_account(
    db: Session,
    group_id: UUID,
    kind: str,
    member_id: UUID | None = None,
    currency: str | None = None,
) -> Account:
    effective_currency = currency or settings.default_currency

    account = (
        db.query(Account)
        .filter_by(group_id=group_id, kind=kind, member_id=member_id)
        .first()
    )

    if account is None:
        account = Account(
            group_id=group_id,
            kind=kind,
            member_id=member_id,
            currency=effective_currency,
        )
        db.add(account)
        db.flush()

    return account