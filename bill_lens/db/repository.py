"""Small persistence boundary. The caller owns commit/rollback of its transaction."""

from collections.abc import Collection
from datetime import timedelta
from typing import get_args
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from bill_lens.contract import ExtractionFields, ReviewFlag
from bill_lens.db.models import Bill, ExtractionRun
from bill_lens.extraction import ExtractionAttempt
from bill_lens.document_validation import DOCUMENT_FLAG_FIELDS
from bill_lens.validation import derive_flags, derive_status

FIELDS_SCHEMA_VERSION = 1


class BillAlreadyExists(Exception):
    def __init__(self, file_sha256: str):
        self.file_sha256 = file_sha256
        super().__init__("a bill with this file hash already exists")


def new_storage_key() -> str:
    """Generate an opaque relative key, independent of the upload filename."""
    return f"bills/{uuid4().hex}.pdf"


def get_bill_by_hash(session: Session, sha256: str) -> Bill | None:
    return session.scalar(select(Bill).where(Bill.file_sha256 == sha256))


def _require_transaction(session: Session) -> None:
    if not session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ValueError("requires an active transaction with no pending writes")


def _validated_run(attempt: ExtractionAttempt, flags: Collection[ReviewFlag], status: str) -> ExtractionRun:
    if not isinstance(attempt, ExtractionAttempt):
        raise TypeError("attempt must be ExtractionAttempt")
    attempt.__post_init__()
    if isinstance(flags, (str, bytes)) or any(flag not in get_args(ReviewFlag) for flag in flags):
        raise ValueError("unknown review flags")
    supplied_flags = set(flags)
    # Nested Pydantic models are mutable: revalidate their JSON representation.
    fields_json = None
    if attempt.fields is not None:
        fields_json = attempt.fields.model_dump(mode="json")
        validated = ExtractionFields.model_validate(fields_json)
        expected_flags = derive_flags(validated)
        # Without PdfText the repository cannot re-prove presence or role. Allow
        # document codes for non-null fields, retaining exact field-rule checks.
        allowed_document_flags = {flag for flag, name in DOCUMENT_FLAG_FIELDS.items()
                                  if getattr(validated, name) is not None}
        if not expected_flags <= supplied_flags or supplied_flags - expected_flags - allowed_document_flags:
            raise ValueError("flags/status must match the current attempt's domain checks")
        expected_status = derive_status(supplied_flags)
    else:
        expected_flags, expected_status = set(), "failed"
        if supplied_flags:
            raise ValueError("failed attempts cannot have review flags")
    if status != expected_status:
        raise ValueError("flags/status must match the current attempt's domain checks")
    return ExtractionRun(
        provider=attempt.provider, model=attempt.model,
        prompt_version=attempt.prompt_version, raw_response=attempt.raw_response,
        fields=fields_json,
        fields_schema_version=FIELDS_SCHEMA_VERSION if fields_json is not None else None,
        error_code=attempt.error_code, review_flags=sorted(supplied_flags), status=status,
        input_tokens=attempt.input_tokens, output_tokens=attempt.output_tokens,
        latency_ms=attempt.latency_ms,
    )


def current_run_statement(bill_id: UUID):
    """Latest validated result (processed/needs_review), else latest failure.

    UUID breaks historical timestamp ties deterministically. Appended runs use
    increasing timestamps under the bill lock. Never decode raw text on reads.
    """
    return (select(ExtractionRun).where(ExtractionRun.bill_id == bill_id)
            .order_by(ExtractionRun.error_code.is_(None).desc(),
                      ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
            .options(defer(ExtractionRun.raw_response, raiseload=True)).limit(1))


def create_bill_with_run(
    session: Session, *, file_sha256: str, storage_key: str, size_bytes: int,
    attempt: ExtractionAttempt, flags: Collection[ReviewFlag], status: str,
) -> Bill:
    """Flush bill + run atomically; caller commits, including before responding.

    Use a clean session inside `with session.begin():`. A savepoint rolls back
    both inserts on failure and leaves the outer transaction usable for a hash
    lookup after BillAlreadyExists. Other integrity failures are not duplicates.
    """
    _require_transaction(session)
    run = _validated_run(attempt, flags, status)
    bill = Bill(file_sha256=file_sha256, storage_key=storage_key,
                size_bytes=size_bytes, processing_status=status)
    try:
        with session.begin_nested():
            session.add(bill)
            session.flush()
            run.bill_id = bill.id
            session.add(run)
            session.flush()
    except IntegrityError as exc:
        if (getattr(exc.orig, "sqlstate", None) == "23505"
                and getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == "uq_bills_file_sha256"):
            raise BillAlreadyExists(file_sha256) from None
        raise
    return bill


def append_extraction_run(
    session: Session, *, bill_id: UUID, attempt: ExtractionAttempt,
    flags: Collection[ReviewFlag], status: str,
) -> Bill:
    """Record every completed retry; preserve a validated current result.

    Extraction must finish before entering this short transaction. All append
    writers lock the same Bill row; current-run selection/status change commit
    together. This helper flushes only; the caller owns the outer transaction.
    """
    _require_transaction(session)
    run = _validated_run(attempt, flags, status)
    with session.begin_nested():
        bill = session.scalars(select(Bill).where(Bill.id == bill_id)
                               .with_for_update().execution_options(populate_existing=True)).one()
        latest = session.scalar(select(func.max(ExtractionRun.created_at))
                                .where(ExtractionRun.bill_id == bill_id))
        if latest is None:
            raise ValueError("existing bill has no extraction run")
        # now() is transaction-start time: an older transaction can acquire the
        # lock later. Use wall-clock time and a floor to guarantee append order,
        # including timestamp ties or a backwards clock adjustment.
        run.created_at = session.scalar(select(func.greatest(
            func.clock_timestamp(), latest + timedelta(microseconds=1))))
        run.bill_id = bill.id
        session.add(run)
        session.flush()
        current = session.scalars(current_run_statement(bill.id)).one()
        # Issue UPDATE even if status is unchanged, so the DB trigger advances
        # updated_at for every appended run, including a late failed attempt.
        session.execute(update(Bill).where(Bill.id == bill.id)
                        .values(processing_status=current.status))
        session.refresh(bill)
    return bill


def load_fields(run: ExtractionRun) -> ExtractionFields | None:
    if run.fields is None:
        if run.fields_schema_version is not None:
            raise ValueError("schema version without fields")
        return None
    if run.fields_schema_version != FIELDS_SCHEMA_VERSION:
        raise ValueError("unsupported fields schema version")
    return ExtractionFields.model_validate(run.fields)
