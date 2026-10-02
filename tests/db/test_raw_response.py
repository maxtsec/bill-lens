import json

import pytest
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from bill_lens.db.models import Bill, ExtractionRun
from bill_lens.db.repository import create_bill_with_run, new_storage_key
from bill_lens.extraction import build_attempt
from tests.db.helpers import migration_config

pytestmark = pytest.mark.db


@pytest.mark.parametrize("kind", ["escaped_nul", "literal_nul", "high_surrogate", "low_surrogate"])
def test_unstorable_model_characters_leave_one_failed_run(db_engine, valid_fields, kind):
    valid_fields["retailer"] = "Example\x00Energy"
    raw = json.dumps(valid_fields)
    if kind == "literal_nul":
        raw = raw.replace(r"\u0000", "\x00")
    elif kind == "high_surrogate":
        raw = raw.replace(r"\u0000", "\ud800")
    elif kind == "low_surrogate":
        raw = raw.replace(r"\u0000", "\udfff")
    attempt = build_attempt(provider="test", model="m", prompt_version="v",
                            raw_response=raw, latency_ms=0)
    assert attempt.error_code == "invalid_output"
    assert attempt.raw_response == raw
    with Session(db_engine) as session, session.begin():
        create_bill_with_run(session, file_sha256="a" * 64, storage_key=new_storage_key(),
                             size_bytes=1, attempt=attempt, flags=[], status="failed")
    # New session after COMMIT: verify actual reload, not the identity map.
    with Session(db_engine) as session:
        bill, = session.scalars(select(Bill)).all()
        run, = session.scalars(select(ExtractionRun)).all()
        assert run.bill_id == bill.id
        assert bill.processing_status == run.status == "failed"
        assert run.error_code == "invalid_output"
        assert run.fields is None and run.fields_schema_version is None
        assert run.raw_response == raw
        assert session.scalar(text("SELECT raw_response FROM extraction_runs")) == raw.encode("utf-8", "surrogatepass")


@pytest.mark.parametrize("raw", [None, "", "電力 ⚡ 😀", r"literal \u0000", "\x00\ud800\udc00😀\udfff"])
def test_explicit_failure_preserves_every_raw_codepoint(db_engine, raw):
    attempt = build_attempt(provider="test", model="m", prompt_version="v",
                            raw_response=raw, error_code="timeout", latency_ms=0)
    with Session(db_engine) as session, session.begin():
        create_bill_with_run(session, file_sha256="b" * 64, storage_key=new_storage_key(),
                             size_bytes=1, attempt=attempt, flags=[], status="failed")
    with Session(db_engine) as session:
        run = session.scalar(select(ExtractionRun))
        assert run.error_code == "timeout"
        assert run.raw_response == raw


def test_populated_migration_preserves_legacy_text_and_null(db_engine):
    originals = [None, "", "電力 😀\n" + r"\u0000"]
    with db_engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0001")
        bill_id = connection.scalar(text("""
            INSERT INTO bills(file_sha256, storage_key, size_bytes, processing_status)
            VALUES (:hash, :key, 1, 'failed') RETURNING id
        """), {"hash": "c" * 64, "key": new_storage_key()})
        for index, raw in enumerate(originals):
            connection.execute(text("""
                INSERT INTO extraction_runs(bill_id, provider, model, prompt_version,
                    raw_response, error_code, status, latency_ms)
                VALUES (:bill, 'test', :model, 'v', :raw, 'timeout', 'failed', 0)
            """), {"bill": bill_id, "model": str(index), "raw": raw})
        command.upgrade(config, "head")
        with Session(bind=connection) as session:
            assert [run.raw_response for run in session.scalars(select(ExtractionRun).order_by(ExtractionRun.model))] == originals
        command.downgrade(config, "0001")
        assert connection.scalars(text("SELECT raw_response FROM extraction_runs ORDER BY model")).all() == originals
        command.upgrade(config, "head")


@pytest.mark.parametrize("raw", ["NUL\x00", "surrogate\ud800"])
def test_downgrade_refuses_unrepresentable_evidence_without_data_loss(db_engine, raw):
    attempt = build_attempt(provider="test", model="m", prompt_version="v",
                            raw_response=raw, error_code="invalid_output", latency_ms=0)
    with Session(db_engine) as session, session.begin():
        create_bill_with_run(session, file_sha256="d" * 64, storage_key=new_storage_key(),
                             size_bytes=1, attempt=attempt, flags=[], status="failed")
    with pytest.raises(DataError), db_engine.begin() as connection:
        command.downgrade(migration_config(connection), "0001")
    with Session(db_engine) as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
        assert session.scalar(select(ExtractionRun)).raw_response == raw
