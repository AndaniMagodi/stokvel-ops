"""The guarantees the database itself enforces.

These pass before any service code exists. They are the floor: whatever the
application layer does, these are the things that cannot happen.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.factories import make_account, post_raw


class TestTransactionsMustBalance:
    def test_balanced_transaction_commits(self, db, group_id, assert_books_balance):
        debit = make_account(db, group_id, member_id=uuid.uuid4())
        credit = make_account(db, group_id, "group_pot", member_id=None)
        post_raw(db, group_id, [(debit, 50_000), (credit, -50_000)])
        db.commit()

        assert_books_balance()

    def test_unbalanced_transaction_is_rejected_at_commit(self, db, group_id):
        debit = make_account(db, group_id, member_id=uuid.uuid4())
        credit = make_account(db, group_id, "group_pot", member_id=None)
        post_raw(db, group_id, [(debit, 50_000), (credit, -49_999)])

        with pytest.raises(DBAPIError, match="does not balance"):
            db.commit()

    def test_single_leg_transaction_is_rejected(self, db, group_id):
        account = make_account(db, group_id, member_id=uuid.uuid4())
        post_raw(db, group_id, [(account, 50_000)])

        with pytest.raises(DBAPIError, match="leg"):
            db.commit()

    def test_zero_amount_leg_is_rejected(self, db, group_id):
        debit = make_account(db, group_id, member_id=uuid.uuid4())
        credit = make_account(db, group_id, "group_pot", member_id=None)

        with pytest.raises(IntegrityError, match="ck_ledger_entries_nonzero"):
            post_raw(db, group_id, [(debit, 0), (credit, 0)])
            db.commit()

    def test_mixed_currency_transaction_is_rejected(self, db, group_id):
        debit = make_account(db, group_id, member_id=uuid.uuid4())
        credit = make_account(db, group_id, "group_pot", member_id=None)
        post_raw(
            db,
            group_id,
            [(debit, 50_000), (credit, -50_000)],
            currencies=["ZAR", "USD"],
        )

        with pytest.raises(DBAPIError, match="currencies"):
            db.commit()


class TestAppendOnly:
    @pytest.fixture()
    def posted(self, db, group_id):
        debit = make_account(db, group_id, member_id=uuid.uuid4())
        credit = make_account(db, group_id, "group_pot", member_id=None)
        transaction_id = post_raw(db, group_id, [(debit, 50_000), (credit, -50_000)])
        db.commit()
        return transaction_id

    def test_entries_cannot_be_updated(self, db, posted):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text("UPDATE ledger_entries SET amount_cents = 1"))
            db.commit()

    def test_entries_cannot_be_deleted(self, db, posted):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text("DELETE FROM ledger_entries"))
            db.commit()

    def test_transactions_cannot_be_updated(self, db, posted):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text("UPDATE ledger_transactions SET kind = 'tampered'"))
            db.commit()


class TestIdempotencyKeyUniqueness:
    def test_same_key_twice_in_one_group_is_rejected(self, db, group_id):
        debit = make_account(db, group_id, member_id=uuid.uuid4())
        credit = make_account(db, group_id, "group_pot", member_id=None)
        post_raw(db, group_id, [(debit, 100), (credit, -100)], idempotency_key="k1")
        db.commit()

        with pytest.raises(IntegrityError):
            post_raw(db, group_id, [(debit, 100), (credit, -100)], idempotency_key="k1")
            db.commit()

    def test_same_key_in_a_different_group_is_allowed(self, db, group_id):
        other_group = uuid.uuid4()
        debit = make_account(db, group_id, member_id=uuid.uuid4())
        credit = make_account(db, group_id, "group_pot", member_id=None)
        post_raw(db, group_id, [(debit, 100), (credit, -100)], idempotency_key="k1")
        db.commit()

        debit2 = make_account(db, other_group, member_id=uuid.uuid4())
        credit2 = make_account(db, other_group, "group_pot", member_id=None)
        post_raw(
            db, other_group, [(debit2, 100), (credit2, -100)], idempotency_key="k1"
        )
        db.commit()


class TestAccountUniqueness:
    def test_one_pot_account_per_group(self, db, group_id):
        make_account(db, group_id, "group_pot", member_id=None)
        db.commit()

        with pytest.raises(IntegrityError):
            make_account(db, group_id, "group_pot", member_id=None)
            db.commit()
