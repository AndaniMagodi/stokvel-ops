"""Raw-SQL helpers used to exercise the database-level invariants directly.

These deliberately bypass app.ledger.service so that the migration's
guarantees can be tested before, and independently of, the service that is
supposed to uphold them.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

INSERT_TRANSACTION = text(
    """
    INSERT INTO ledger_transactions (id, group_id, kind, idempotency_key)
    VALUES (:id, :group_id, :kind, :idempotency_key)
    """
)

INSERT_ACCOUNT = text(
    """
    INSERT INTO accounts (id, group_id, kind, member_id, currency)
    VALUES (:id, :group_id, :kind, :member_id, :currency)
    """
)

INSERT_ENTRY = text(
    """
    INSERT INTO ledger_entries (transaction_id, account_id, amount_cents, currency)
    VALUES (:transaction_id, :account_id, :amount_cents, :currency)
    """
)


def make_account(
    db: Session,
    group_id: uuid.UUID,
    kind: str = "member_contributions",
    member_id: uuid.UUID | None = None,
    currency: str = "ZAR",
) -> uuid.UUID:
    account_id = uuid.uuid4()
    db.execute(
        INSERT_ACCOUNT,
        {
            "id": account_id,
            "group_id": group_id,
            "kind": kind,
            "member_id": member_id,
            "currency": currency,
        },
    )
    return account_id


def post_raw(
    db: Session,
    group_id: uuid.UUID,
    legs: list[tuple[uuid.UUID, int]],
    kind: str = "contribution",
    idempotency_key: str | None = None,
    currencies: list[str] | None = None,
) -> uuid.UUID:
    transaction_id = uuid.uuid4()
    db.execute(
        INSERT_TRANSACTION,
        {
            "id": transaction_id,
            "group_id": group_id,
            "kind": kind,
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
        },
    )
    for index, (account_id, amount_cents) in enumerate(legs):
        currency = currencies[index] if currencies else "ZAR"
        db.execute(
            INSERT_ENTRY,
            {
                "transaction_id": transaction_id,
                "account_id": account_id,
                "amount_cents": amount_cents,
                "currency": currency,
            },
        )
    return transaction_id
