"""Test harness for the ledger.

The suite runs against a real Postgres instance because most of the ledger's
guarantees are database guarantees — deferred constraint triggers, unique
indexes, append-only triggers. Substituting SQLite would test a different
system.

Isolation is by TRUNCATE rather than by wrapping each test in a transaction
that gets rolled back. That is deliberate: deferred constraint triggers fire
at COMMIT, so a test that never really commits would never see them fire.
TRUNCATE is safe here because it does not fire the row-level append-only
triggers.
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from hypothesis import HealthCheck, settings
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

TABLES = ("ledger_entries", "ledger_transactions", "accounts")

settings.register_profile(
    "db",
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
settings.register_profile(
    "thorough",
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "db"))


def _test_database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        return url
    from app.core.config import settings as app_settings

    if app_settings.test_database_url:
        return app_settings.test_database_url
    pytest.fail(
        "TEST_DATABASE_URL is not set. Run `make up` and copy .env.example to .env."
    )


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = _test_database_url()
    eng = create_engine(url, future=True)

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with engine.begin() as conn:
            conn.execute(
                text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
            )


@pytest.fixture()
def group_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture()
def assert_books_balance(db: Session):
    def _assert() -> None:
        rows = db.execute(
            text(
                """
                SELECT transaction_id, SUM(amount_cents) AS imbalance
                FROM ledger_entries
                GROUP BY transaction_id
                HAVING SUM(amount_cents) <> 0
                """
            )
        ).all()
        assert rows == [], f"unbalanced transactions found: {rows}"

        total = db.execute(
            text("SELECT COALESCE(SUM(amount_cents), 0) FROM ledger_entries")
        ).scalar_one()
        assert total == 0, f"ledger does not sum to zero overall: {total}"

    return _assert
