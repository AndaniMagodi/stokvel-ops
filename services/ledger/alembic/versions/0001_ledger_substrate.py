"""ledger substrate: accounts, transactions, entries, and the database-level invariants

Revision ID: 0001_ledger_substrate
Revises:
Create Date: 2026-09-05

"""

from alembic import op
import sqlalchemy as sa


revision = "0001_ledger_substrate"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounts_group_id", "accounts", ["group_id"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_accounts_group_kind_member
        ON accounts (group_id, kind, member_id) NULLS NOT DISTINCT
        """
    )

    op.create_table(
        "ledger_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reverses_transaction_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["reverses_transaction_id"], ["ledger_transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_ledger_transactions_group_idempotency",
        "ledger_transactions",
        ["group_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_ledger_transactions_reverses",
        "ledger_transactions",
        ["reverses_transaction_id"],
        unique=True,
        postgresql_where=sa.text("reverses_transaction_id IS NOT NULL"),
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("amount_cents <> 0", name="ck_ledger_entries_nonzero"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["ledger_transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])
    op.create_index(
        "ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"]
    )

    op.execute(
        """
        CREATE FUNCTION assert_entries_balance() RETURNS trigger AS $fn$
        DECLARE
            imbalance bigint;
        BEGIN
            SELECT COALESCE(SUM(amount_cents), 0) INTO imbalance
            FROM ledger_entries
            WHERE transaction_id = NEW.transaction_id;

            IF imbalance <> 0 THEN
                RAISE EXCEPTION
                    'ledger transaction % does not balance (imbalance %)',
                    NEW.transaction_id, imbalance
                    USING ERRCODE = 'check_violation';
            END IF;

            RETURN NULL;
        END;
        $fn$ LANGUAGE plpgsql
        """
    )

    op.execute(
        """
        CREATE FUNCTION assert_transaction_well_formed() RETURNS trigger AS $fn$
        DECLARE
            leg_count integer;
            currency_count integer;
            imbalance bigint;
        BEGIN
            SELECT COUNT(*), COUNT(DISTINCT currency), COALESCE(SUM(amount_cents), 0)
            INTO leg_count, currency_count, imbalance
            FROM ledger_entries
            WHERE transaction_id = NEW.id;

            IF leg_count < 2 THEN
                RAISE EXCEPTION
                    'ledger transaction % has % leg(s); at least 2 are required',
                    NEW.id, leg_count
                    USING ERRCODE = 'check_violation';
            END IF;

            IF currency_count > 1 THEN
                RAISE EXCEPTION
                    'ledger transaction % mixes % currencies', NEW.id, currency_count
                    USING ERRCODE = 'check_violation';
            END IF;

            IF imbalance <> 0 THEN
                RAISE EXCEPTION
                    'ledger transaction % does not balance (imbalance %)',
                    NEW.id, imbalance
                    USING ERRCODE = 'check_violation';
            END IF;

            RETURN NULL;
        END;
        $fn$ LANGUAGE plpgsql
        """
    )

    op.execute(
        """
        CREATE FUNCTION reject_mutation() RETURNS trigger AS $fn$
        BEGIN
            RAISE EXCEPTION
                'append-only: % on % is not permitted', TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'restrict_violation';
        END;
        $fn$ LANGUAGE plpgsql
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_entries_balance
        AFTER INSERT ON ledger_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION assert_entries_balance()
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_transaction_well_formed
        AFTER INSERT ON ledger_transactions
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION assert_transaction_well_formed()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_append_only
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION reject_mutation()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ledger_transactions_append_only
        BEFORE UPDATE OR DELETE ON ledger_transactions
        FOR EACH ROW EXECUTE FUNCTION reject_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_ledger_transactions_append_only ON ledger_transactions")
    op.execute("DROP TRIGGER trg_ledger_entries_append_only ON ledger_entries")
    op.execute("DROP TRIGGER trg_transaction_well_formed ON ledger_transactions")
    op.execute("DROP TRIGGER trg_entries_balance ON ledger_entries")
    op.execute("DROP FUNCTION reject_mutation()")
    op.execute("DROP FUNCTION assert_transaction_well_formed()")
    op.execute("DROP FUNCTION assert_entries_balance()")
    op.drop_table("ledger_entries")
    op.drop_table("ledger_transactions")
    op.drop_table("accounts")
