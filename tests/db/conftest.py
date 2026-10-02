"""Real PostgreSQL, migrated in a disposable schema; never touch public tables."""

import os
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from bill_lens.db.config import database_url
from tests.db.helpers import migration_config


@pytest.fixture(scope="session")
def db_engine():
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL is not set; real PostgreSQL DB tests require Docker")
    url = database_url("TEST_DATABASE_URL")
    schema = "test_bill_lens_" + uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, hide_parameters=True,
        connect_args={"options": f"-csearch_path={schema} -cstatement_timeout=10000 -clock_timeout=5000"},
    )
    try:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture(autouse=True)
def empty_tables(db_engine):
    # Committed writes are necessary for the multi-session race test. Clean up
    # after *every* test, including assertion failures, inside our own schema.
    with db_engine.connect() as connection:
        for table in ("bills", "extraction_runs", "bill_reviews"):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
    try:
        yield
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("DELETE FROM bill_reviews"))
            connection.execute(text("DELETE FROM extraction_runs"))
            connection.execute(text("DELETE FROM bills"))
            assert connection.scalar(text("SELECT count(*) FROM extraction_runs")) == 0
            assert connection.scalar(text("SELECT count(*) FROM bills")) == 0
