"""The specification for app.ledger.service.

Every test here fails until the service is implemented. That is the point:
these are the requirements, written before the code, and they are what
"done" means for step 1.
"""

import uuid

import pytest
from hypothesis import given
from sqlalchemy import text

from app.ledger import service
from app.ledger.accounts import ensure_account
from app.ledger.errors import (
    AccountNotInGroup,
    CurrencyMismatch,
    EmptyTransaction,
    IdempotencyKeyConflict,
    TransactionAlreadyReversed,
    UnbalancedTransaction,
    ZeroAmountLeg,
)
from app.ledger.posting import Leg, PostingRequest
from tests.strategies import balanced_amounts, nonzero_cents, posting_plans


def request_for(group_id, amounts, accounts, kind="contribution", key=None):
    return PostingRequest(
        group_id=group_id,
        kind=kind,
        idempotency_key=key or str(uuid.uuid4()),
        legs=tuple(
            Leg(account_id=accounts[index], amount_cents=amount)
            for index, amount in enumerate(amounts)
        ),
    )


def accounts_for(db, group_id, count):
    return [
        ensure_account(db, group_id, "member_contributions", uuid.uuid4()).id
        for _ in range(count)
    ]


class TestEnsureAccount:
    def test_creates_an_account(self, db, group_id):
        member_id = uuid.uuid4()
        account = ensure_account(db, group_id, "member_contributions", member_id)

        assert account.group_id == group_id
        assert account.member_id == member_id
        assert account.currency == "ZAR"

    def test_is_idempotent_for_the_same_member(self, db, group_id):
        member_id = uuid.uuid4()
        first = ensure_account(db, group_id, "member_contributions", member_id)
        second = ensure_account(db, group_id, "member_contributions", member_id)

        assert first.id == second.id

    def test_distinct_members_get_distinct_accounts(self, db, group_id):
        first = ensure_account(db, group_id, "member_contributions", uuid.uuid4())
        second = ensure_account(db, group_id, "member_contributions", uuid.uuid4())

        assert first.id != second.id

    def test_group_pot_has_no_member(self, db, group_id):
        account = ensure_account(db, group_id, "group_pot")

        assert account.member_id is None


class TestPosting:
    @given(amounts=balanced_amounts())
    def test_balanced_postings_keep_the_books_balanced(
        self, db, group_id, assert_books_balance, amounts
    ):
        accounts = accounts_for(db, group_id, len(amounts))
        service.post_transaction(db, request_for(group_id, amounts, accounts))
        db.commit()

        assert_books_balance()

    @given(amount=nonzero_cents, drift=nonzero_cents)
    def test_unbalanced_posting_is_refused(self, db, group_id, amount, drift):
        accounts = accounts_for(db, group_id, 3)
        request = request_for(group_id, [amount, -amount, drift], accounts)

        with pytest.raises(UnbalancedTransaction):
            service.post_transaction(db, request)

    def test_refused_posting_leaves_nothing_behind(self, db, group_id):
        accounts = accounts_for(db, group_id, 2)
        db.commit()

        with pytest.raises(UnbalancedTransaction):
            service.post_transaction(db, request_for(group_id, [100, -99], accounts))

        db.rollback()
        count = db.execute(
            text("SELECT COUNT(*) FROM ledger_transactions")
        ).scalar_one()
        assert count == 0

    def test_empty_leg_list_is_refused(self, db, group_id):
        request = PostingRequest(
            group_id=group_id,
            kind="contribution",
            idempotency_key=str(uuid.uuid4()),
            legs=(),
        )

        with pytest.raises(EmptyTransaction):
            service.post_transaction(db, request)

    def test_zero_amount_leg_is_refused(self, db, group_id):
        accounts = accounts_for(db, group_id, 2)

        with pytest.raises(ZeroAmountLeg):
            service.post_transaction(db, request_for(group_id, [0, 0], accounts))

    def test_account_from_another_group_is_refused(self, db, group_id):
        mine = accounts_for(db, group_id, 1)
        theirs = accounts_for(db, uuid.uuid4(), 1)

        with pytest.raises(AccountNotInGroup):
            service.post_transaction(
                db, request_for(group_id, [100, -100], mine + theirs)
            )

    def test_mixed_currency_accounts_are_refused(self, db, group_id):
        zar = ensure_account(db, group_id, "member_contributions", uuid.uuid4())
        usd = ensure_account(db, group_id, "external", uuid.uuid4(), currency="USD")

        with pytest.raises(CurrencyMismatch):
            service.post_transaction(
                db, request_for(group_id, [100, -100], [zar.id, usd.id])
            )


class TestBalances:
    @given(amounts=balanced_amounts())
    def test_balance_is_the_sum_of_entries(self, db, group_id, amounts):
        accounts = accounts_for(db, group_id, len(amounts))
        service.post_transaction(db, request_for(group_id, amounts, accounts))
        db.commit()

        for account_id, amount in zip(accounts, amounts):
            assert service.account_balance(db, account_id) == amount

    @given(plans=posting_plans())
    def test_group_balances_always_net_to_zero(self, db, group_id, plans):
        for amounts in plans:
            accounts = accounts_for(db, group_id, len(amounts))
            service.post_transaction(db, request_for(group_id, amounts, accounts))
        db.commit()

        assert sum(service.group_balances(db, group_id).values()) == 0

    @given(plans=posting_plans())
    def test_final_balances_do_not_depend_on_posting_order(self, db, plans):
        members = [uuid.uuid4() for _ in range(4)]

        def apply(target_group, ordered):
            accounts = {
                member: ensure_account(
                    db, target_group, "member_contributions", member
                ).id
                for member in members
            }
            for amounts in ordered:
                legs = [accounts[members[index]] for index in range(len(amounts))]
                service.post_transaction(
                    db, request_for(target_group, amounts, legs)
                )
            db.commit()
            return sorted(service.group_balances(db, target_group).values())

        forwards = apply(uuid.uuid4(), plans)
        backwards = apply(uuid.uuid4(), list(reversed(plans)))

        assert forwards == backwards


class TestIdempotency:
    def test_replaying_the_same_posting_creates_one_transaction(self, db, group_id):
        accounts = accounts_for(db, group_id, 2)
        request = request_for(group_id, [100, -100], accounts, key="webhook-1")

        first = service.post_transaction(db, request)
        db.commit()
        second = service.post_transaction(db, request)
        db.commit()

        assert first.created is True
        assert second.created is False
        assert first.transaction_id == second.transaction_id
        assert service.account_balance(db, accounts[0]) == 100

    def test_repeated_replay_does_not_move_the_balance(self, db, group_id):
        accounts = accounts_for(db, group_id, 2)
        request = request_for(group_id, [250, -250], accounts, key="webhook-2")

        for _ in range(5):
            service.post_transaction(db, request)
            db.commit()

        assert service.account_balance(db, accounts[0]) == 250

    def test_same_key_with_different_legs_is_a_conflict(self, db, group_id):
        accounts = accounts_for(db, group_id, 2)
        service.post_transaction(
            db, request_for(group_id, [100, -100], accounts, key="webhook-3")
        )
        db.commit()

        with pytest.raises(IdempotencyKeyConflict):
            service.post_transaction(
                db, request_for(group_id, [900, -900], accounts, key="webhook-3")
            )

    def test_the_same_key_in_another_group_is_independent(self, db, group_id):
        mine = accounts_for(db, group_id, 2)
        other_group = uuid.uuid4()
        theirs = accounts_for(db, other_group, 2)

        service.post_transaction(
            db, request_for(group_id, [100, -100], mine, key="shared")
        )
        result = service.post_transaction(
            db, request_for(other_group, [100, -100], theirs, key="shared")
        )
        db.commit()

        assert result.created is True


class TestReversal:
    @given(amounts=balanced_amounts())
    def test_reversal_restores_the_prior_balances(
        self, db, group_id, assert_books_balance, amounts
    ):
        accounts = accounts_for(db, group_id, len(amounts))
        posted = service.post_transaction(db, request_for(group_id, amounts, accounts))
        db.commit()

        service.reverse_transaction(db, posted.transaction_id, str(uuid.uuid4()))
        db.commit()

        for account_id in accounts:
            assert service.account_balance(db, account_id) == 0
        assert_books_balance()

    def test_a_transaction_cannot_be_reversed_twice(self, db, group_id):
        accounts = accounts_for(db, group_id, 2)
        posted = service.post_transaction(
            db, request_for(group_id, [100, -100], accounts)
        )
        db.commit()
        service.reverse_transaction(db, posted.transaction_id, str(uuid.uuid4()))
        db.commit()

        with pytest.raises(TransactionAlreadyReversed):
            service.reverse_transaction(db, posted.transaction_id, str(uuid.uuid4()))
            db.commit()
