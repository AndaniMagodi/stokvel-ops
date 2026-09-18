from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ledger.errors import (
    AccountNotInGroup,
    CurrencyMismatch,
    EmptyTransaction,
    IdempotencyKeyConflict,
    TransactionAlreadyReversed,
    TransactionNotFound,
    UnbalancedTransaction,
    ZeroAmountLeg,
)
from app.ledger.posting import Leg, PostingRequest, PostingResult
from app.models.ledger import Account, LedgerEntry, LedgerTransaction


def _same_posting(transaction: LedgerTransaction, request: PostingRequest) -> bool:
    recorded_legs = sorted(
        (entry.account_id, entry.amount_cents) for entry in transaction.entries
    )
    requested_legs = sorted(
        (leg.account_id, leg.amount_cents) for leg in request.legs
    )
    return transaction.kind == request.kind and recorded_legs == requested_legs


def post_transaction(
    db: Session,
    request: PostingRequest,
    *,
    _reverses_transaction_id: UUID | None = None,
) -> PostingResult:
    existing = db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.group_id == request.group_id,
            LedgerTransaction.idempotency_key == request.idempotency_key,
        )
    )
    if existing is not None:
        if not _same_posting(existing, request):
            raise IdempotencyKeyConflict(request.idempotency_key)
        return PostingResult(transaction_id=existing.id, created=False)

    if not request.legs:
        raise EmptyTransaction()
    if any(leg.amount_cents == 0 for leg in request.legs):
        raise ZeroAmountLeg()
    if len(request.legs) < 2 or sum(leg.amount_cents for leg in request.legs) != 0:
        raise UnbalancedTransaction()

    account_ids = {leg.account_id for leg in request.legs}
    accounts = {
        account.id: account
        for account in db.scalars(select(Account).where(Account.id.in_(account_ids)))
    }
    if len(accounts) != len(account_ids) or any(
        account.group_id != request.group_id for account in accounts.values()
    ):
        raise AccountNotInGroup()
    if len({account.currency for account in accounts.values()}) != 1:
        raise CurrencyMismatch()

    values = {
        "group_id": request.group_id,
        "kind": request.kind,
        "idempotency_key": request.idempotency_key,
        "reverses_transaction_id": _reverses_transaction_id,
    }
    if request.occurred_at is not None:
        values["occurred_at"] = request.occurred_at

    try:
        # The savepoint lets a concurrent duplicate fail without breaking the
        # caller's surrounding transaction.
        with db.begin_nested():
            transaction = LedgerTransaction(**values)
            db.add(transaction)
            db.flush()
            db.add_all(
                LedgerEntry(
                    transaction_id=transaction.id,
                    account_id=leg.account_id,
                    amount_cents=leg.amount_cents,
                    currency=accounts[leg.account_id].currency,
                )
                for leg in request.legs
            )
            db.flush()
    except IntegrityError:
        existing = db.scalar(
            select(LedgerTransaction).where(
                LedgerTransaction.group_id == request.group_id,
                LedgerTransaction.idempotency_key == request.idempotency_key,
            )
        )
        if existing is None:
            raise
        if not _same_posting(existing, request):
            raise IdempotencyKeyConflict(request.idempotency_key)
        return PostingResult(transaction_id=existing.id, created=False)

    return PostingResult(transaction_id=transaction.id, created=True)


def account_balance(db: Session, account_id: UUID) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
            LedgerEntry.account_id == account_id
        )
    )
    return int(total)


def group_balances(db: Session, group_id: UUID) -> dict[UUID, int]:
    rows = db.execute(
        select(Account.id, func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .outerjoin(LedgerEntry, LedgerEntry.account_id == Account.id)
        .where(Account.group_id == group_id)
        .group_by(Account.id)
    )
    return {account_id: int(balance) for account_id, balance in rows}


def reverse_transaction(
    db: Session, transaction_id: UUID, idempotency_key: str
) -> PostingResult:
    original = db.get(LedgerTransaction, transaction_id)
    if original is None:
        raise TransactionNotFound(transaction_id)

    existing_key = db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.group_id == original.group_id,
            LedgerTransaction.idempotency_key == idempotency_key,
        )
    )
    if existing_key is not None:
        if existing_key.reverses_transaction_id != transaction_id:
            raise IdempotencyKeyConflict(idempotency_key)
        return PostingResult(transaction_id=existing_key.id, created=False)

    already_reversed = db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.reverses_transaction_id == transaction_id
        )
    )
    if already_reversed is not None:
        raise TransactionAlreadyReversed(transaction_id)

    result = post_transaction(
        db,
        PostingRequest(
            group_id=original.group_id,
            kind="reversal",
            idempotency_key=idempotency_key,
            legs=tuple(
                Leg(account_id=entry.account_id, amount_cents=-entry.amount_cents)
                for entry in original.entries
            ),
        ),
        _reverses_transaction_id=transaction_id,
    )
    return result
