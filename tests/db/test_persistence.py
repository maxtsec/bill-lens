from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from pydantic import ValidationError
from sqlalchemy import JSON, bindparam, inspect, null, select, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from bill_lens.db.models import Base, Bill, ExtractionRun
from bill_lens.db.repository import BillAlreadyExists, create_bill_with_run, get_bill_by_hash, load_fields, new_storage_key
from bill_lens.extraction import FakeExtractor, build_attempt
from bill_lens.pdf_text import extract_pdf_text
from bill_lens.validation import derive_flags, derive_status
from tests.db.helpers import migration_config
from tests.helpers import CASES, ROOT

pytestmark = pytest.mark.db


def golden(case="bill_001"):
    document = extract_pdf_text((ROOT / "dataset" / case / "bill.pdf").read_bytes())
    return FakeExtractor.from_dataset(ROOT / "dataset").extract(document)


def persist(session, attempt=None, **overrides):
    attempt = attempt or golden()
    flags = derive_flags(attempt.fields) if attempt.fields is not None else set()
    values = dict(file_sha256=uuid4().hex * 2, storage_key=new_storage_key(), size_bytes=100,
                  attempt=attempt, flags=flags, status=derive_status(flags) if attempt.fields else "failed")
    return create_bill_with_run(session, **(values | overrides))


@pytest.mark.parametrize("case", CASES)
def test_golden_jsonb_round_trip(db_engine, case):
    attempt = golden(case)
    with Session(db_engine, expire_on_commit=False) as session, session.begin():
        bill = persist(session, attempt)
        bill_id = bill.id
        assert isinstance(bill_id, UUID)
        assert bill.created_at.tzinfo is not None
        assert bill.updated_at.tzinfo is not None
    with Session(db_engine) as session:
        loaded = session.get(Bill, bill_id)
        run = session.scalar(select(ExtractionRun).where(ExtractionRun.bill_id == bill_id))
        assert run.fields == attempt.fields.model_dump(mode="json")
        assert load_fields(run) == attempt.fields
        assert run.raw_response == attempt.raw_response
        assert run.fields_schema_version == 1
        assert run.review_flags == sorted(derive_flags(attempt.fields))
        assert loaded.processing_status == run.status == derive_status(run.review_flags)
        assert get_bill_by_hash(session, loaded.file_sha256).id == bill_id
        assert get_bill_by_hash(session, "f" * 64) is None
        if case == "bill_001":
            assert run.fields["current_bill_amount"] == "108.07"
            assert isinstance(run.fields["current_bill_amount"], str)
        if case == "bill_002":
            assert "current_bill_amount" in run.fields
            assert run.fields["current_bill_amount"] is None


@pytest.mark.parametrize("code", ["rate_limited", "timeout", "refused", "truncated", "invalid_output", "provider_error"])
def test_failed_attempt_round_trip(db_engine, code):
    attempt = build_attempt(provider="test", model="m", prompt_version="v",
                            raw_response="actual provider response", error_code=code, latency_ms=5)
    with Session(db_engine) as session, session.begin():
        bill = persist(session, attempt)
        run = session.scalar(select(ExtractionRun).where(ExtractionRun.bill_id == bill.id))
        assert run.status == bill.processing_status == "failed"
        assert run.error_code == code
        assert run.raw_response == "actual provider response"
        assert run.fields is None and load_fields(run) is None
        assert run.fields_schema_version is None
        assert run.review_flags == []
        assert run.input_tokens is None and run.output_tokens is None
        assert run.latency_ms == 5


def test_migration_downgrade_upgrade_and_no_model_drift(db_engine):
    with db_engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
        assert connection.scalar(text("SELECT count(*) FROM pg_proc WHERE proname='touch_bill_updated_at' AND pronamespace=current_schema()::regnamespace")) == 0
        command.upgrade(config, "head")
        context = MigrationContext.configure(connection, opts={"compare_type": True, "compare_server_default": True})
        assert compare_metadata(context, Base.metadata) == []
        command.check(config)
        assert inspect(connection).get_indexes("extraction_runs")[0]["column_names"] == ["bill_id"]


# Each named CHECK has an independently chosen violating UPDATE, through raw
# SQL and ORM. Updating avoids ORM omission/default behavior masking SQL NULLs.
CHECK_CASES = [
    ("bills", "ck_bills_hash", {"file_sha256": "z" * 64}),
    ("bills", "ck_bills_storage_key", {"storage_key": "../customer.pdf"}),
    ("bills", "ck_bills_size", {"size_bytes": 0}),
    ("bills", "ck_bills_status", {"processing_status": "unknown"}),
    ("extraction_runs", "ck_runs_provider", {"provider": " \t\n"}),
    ("extraction_runs", "ck_runs_model", {"model": ""}),
    ("extraction_runs", "ck_runs_prompt_version", {"prompt_version": " "}),
    ("extraction_runs", "ck_runs_error_code", {"fields": None, "fields_schema_version": None, "error_code": "typo", "status": "failed"}),
    ("extraction_runs", "ck_runs_outcome", {"fields": None, "fields_schema_version": None}),
    ("extraction_runs", "ck_runs_outcome", {"error_code": "timeout", "status": "failed"}),
    ("extraction_runs", "ck_runs_raw_response", {"raw_response": None}),
    ("extraction_runs", "ck_runs_raw_response", {"fields": None, "fields_schema_version": None, "error_code": "invalid_output", "status": "failed", "raw_response": None}),
    ("extraction_runs", "ck_runs_fields_object", {"fields": []}),
    ("extraction_runs", "ck_runs_fields_object", {"fields": JSON.NULL}),
    ("extraction_runs", "ck_runs_schema_version", {"fields_schema_version": None}),
    ("extraction_runs", "ck_runs_schema_version", {"fields_schema_version": 0}),
    ("extraction_runs", "ck_runs_schema_version", {"fields": None, "error_code": "timeout", "status": "failed"}),
    ("extraction_runs", "ck_runs_flags_array", {"review_flags": {}, "status": "needs_review"}),
    ("extraction_runs", "ck_runs_flags_array", {"review_flags": JSON.NULL, "status": "needs_review"}),
    ("extraction_runs", "ck_runs_status", {"status": "typo"}),
    ("extraction_runs", "ck_runs_failed", {"status": "failed"}),
    ("extraction_runs", "ck_runs_failed", {"fields": None, "fields_schema_version": None, "error_code": "timeout"}),
    ("extraction_runs", "ck_runs_status_flags", {"status": "needs_review"}),
    ("extraction_runs", "ck_runs_status_flags", {"review_flags": ["retailer_missing"]}),
    ("extraction_runs", "ck_runs_input_tokens", {"input_tokens": -1}),
    ("extraction_runs", "ck_runs_output_tokens", {"output_tokens": -1}),
    ("extraction_runs", "ck_runs_latency", {"latency_ms": -1}),
]


def change_row(session, row, changes, via):
    if via == "orm":
        for key, value in changes.items():
            setattr(row, key, value)
        session.flush()
    else:
        table = row.__table__
        statement = text(f"UPDATE {table.name} SET " + ", ".join(f"{key} = :{key}" for key in changes) + " WHERE id = :row_id")
        statement = statement.bindparams(*(bindparam(key, type_=table.c[key].type) for key in changes))
        session.execute(statement, changes | {"row_id": row.id})


@pytest.mark.parametrize("via", ["sql", "orm"])
@pytest.mark.parametrize("table,constraint,changes", CHECK_CASES, ids=[x[1] for x in CHECK_CASES])
def test_check_constraints(db_engine, via, table, constraint, changes):
    with Session(db_engine) as session, session.begin():
        bill = persist(session)
        row = bill if table == "bills" else session.scalar(select(ExtractionRun))
        with pytest.raises(IntegrityError) as error, session.begin_nested():
            change_row(session, row, changes, via)
        assert error.value.orig.diag.constraint_name == constraint


def test_every_database_check_has_a_rejection_case(db_engine):
    with db_engine.connect() as connection:
        for table in ("bills", "extraction_runs"):
            actual = {c["name"] for c in inspect(connection).get_check_constraints(table)}
            expected = {name for target, name, _ in CHECK_CASES if target == table}
            assert actual == expected
            assert actual == {c.name for c in Base.metadata.tables[table].constraints if c.__class__.__name__ == "CheckConstraint"}


@pytest.mark.parametrize("via", ["sql", "orm"])
@pytest.mark.parametrize("column", ["file_sha256", "storage_key"])
def test_unique_constraints(db_engine, via, column):
    with Session(db_engine) as session, session.begin():
        first, second = persist(session), persist(session)
        with pytest.raises(IntegrityError) as error, session.begin_nested():
            change_row(session, second, {column: getattr(first, column)}, via)
        assert error.value.orig.diag.constraint_name == f"uq_bills_{column}"


@pytest.mark.parametrize("via", ["sql", "orm"])
@pytest.mark.parametrize("table,column", [
    ("bills", key) for key in ("id", "file_sha256", "storage_key", "size_bytes", "processing_status", "created_at", "updated_at")
] + [("extraction_runs", key) for key in ("id", "bill_id", "provider", "model", "prompt_version", "review_flags", "status", "latency_ms", "created_at")])
def test_not_null_constraints(db_engine, via, table, column):
    with Session(db_engine) as session, session.begin():
        bill = persist(session)
        row = bill if table == "bills" else session.scalar(select(ExtractionRun))
        with pytest.raises(IntegrityError) as error, session.begin_nested():
            if table == "bills" and column == "updated_at":
                # On UPDATE the trigger supplies a timestamp. Explicit NULL on
                # INSERT must still fail rather than use the server default.
                if via == "orm":
                    session.add(Bill(file_sha256="b" * 64, storage_key=new_storage_key(),
                                     size_bytes=1, processing_status="processed", updated_at=null()))
                    session.flush()
                else:
                    session.execute(text("INSERT INTO bills (file_sha256, storage_key, size_bytes, processing_status, updated_at) VALUES (:hash, :key, 1, 'processed', NULL)"),
                                    {"hash": "b" * 64, "key": new_storage_key()})
            else:
                change_row(session, row, {column: None}, via)
        assert error.value.orig.sqlstate == "23502"
        assert error.value.orig.diag.column_name == column


@pytest.mark.parametrize("via", ["sql", "orm"])
@pytest.mark.parametrize("model", [Bill, ExtractionRun])
def test_primary_keys_reject_duplicates(db_engine, via, model):
    with Session(db_engine) as session, session.begin():
        persist(session)
        persist(session)
        first, second = session.scalars(select(model)).all()
        with pytest.raises(IntegrityError) as error, session.begin_nested():
            change_row(session, second, {"id": first.id}, via)
        assert error.value.orig.sqlstate == "23505"


@pytest.mark.parametrize("via", ["sql", "orm"])
def test_foreign_key_constraint(db_engine, via):
    with Session(db_engine) as session, session.begin():
        persist(session)
        run = session.scalar(select(ExtractionRun))
        with pytest.raises(IntegrityError) as error, session.begin_nested():
            change_row(session, run, {"bill_id": uuid4()}, via)
        assert error.value.orig.diag.constraint_name == "fk_runs_bill"


@pytest.mark.parametrize("via", ["sql", "orm"])
def test_updated_at_is_set_by_database(db_engine, via):
    with Session(db_engine) as session, session.begin():
        bill = persist(session)
        previous = bill.updated_at
        change_row(session, bill, {"size_bytes": 101}, via)
        session.refresh(bill)
        assert bill.updated_at > previous


def test_concurrent_duplicate_has_one_winner_and_no_partial_run(db_engine):
    barrier = Barrier(2, timeout=5)
    file_hash = "a" * 64
    attempt = golden()

    def upload():
        with Session(db_engine) as session, session.begin():
            # Both transactions observe absence before either inserts.
            assert get_bill_by_hash(session, file_hash) is None
            barrier.wait()
            try:
                bill = persist(session, attempt, file_sha256=file_hash)
                return "created", bill.id
            except BillAlreadyExists as error:
                assert error.file_sha256 == file_hash
                # SAVEPOINT rollback leaves this session usable.
                return "existing", get_bill_by_hash(session, file_hash).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(upload) for _ in range(2)]
        outcomes = [future.result(timeout=15) for future in futures]
    assert sorted(outcome for outcome, _ in outcomes) == ["created", "existing"]
    assert outcomes[0][1] == outcomes[1][1]
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM bills")) == 1
        assert connection.scalar(text("SELECT count(*) FROM extraction_runs")) == 1


def test_run_failure_rolls_back_bill_and_storage_collision_is_not_duplicate(db_engine):
    with Session(db_engine) as session, session.begin():
        # PostgreSQL text cannot store NUL. The first bill INSERT succeeds,
        # but its run fails; the savepoint must remove that bill as well.
        attempt = build_attempt(provider="fake", model="m", prompt_version="v", raw_response="bad\x00reply", error_code="invalid_output", latency_ms=0)
        with pytest.raises(DataError):
            persist(session, attempt)
        assert session.scalar(select(Bill)) is None
        assert session.scalar(select(ExtractionRun)) is None
        first = persist(session)
        with pytest.raises(IntegrityError) as error:
            persist(session, storage_key=first.storage_key)
        assert error.value.orig.diag.constraint_name == "uq_bills_storage_key"
        assert len(session.scalars(select(Bill)).all()) == 1


def test_outer_rollback_removes_both_rows(db_engine):
    with Session(db_engine) as session:
        with pytest.raises(RuntimeError), session.begin():
            persist(session)
            raise RuntimeError("caller aborted")
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM bills")) == 0
        assert connection.scalar(text("SELECT count(*) FROM extraction_runs")) == 0


def test_untrusted_jsonb_is_validated_on_read(db_engine):
    with Session(db_engine) as session, session.begin():
        persist(session)
        run = session.scalar(select(ExtractionRun))
        change_row(session, run, {"fields": {"current_bill_amount": 108.07}}, "sql")
        session.refresh(run)
        with pytest.raises(ValidationError):
            load_fields(run)
        change_row(session, run, {"fields_schema_version": 2}, "sql")
        session.refresh(run)
        with pytest.raises(ValueError, match="unsupported"):
            load_fields(run)
