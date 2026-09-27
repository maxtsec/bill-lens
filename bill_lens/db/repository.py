"""Small persistence boundary. The caller owns commit/rollback of its transaction."""

from collections.abc import Collection
from typing import get_args
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bill_lens.contract import ExtractionFields, ReviewFlag
from bill_lens.db.models import Bill, ExtractionRun
from bill_lens.extraction import ExtractionAttempt
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


def create_bill_with_run(
    session: Session, *, file_sha256: str, storage_key: str, size_bytes: int,
    attempt: ExtractionAttempt, flags: Collection[ReviewFlag], status: str,
) -> Bill:
    """Flush bill + run atomically; caller commits, including before responding.

    Use a clean session inside `with session.begin():`. A savepoint rolls back
    both inserts on failure and leaves the outer transaction usable for a hash
    lookup after BillAlreadyExists. Other integrity failures are not duplicates.
    """
    if not session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ValueError("requires an active transaction with no pending writes")
    if not isinstance(attempt, ExtractionAttempt):
        raise TypeError("attempt must be ExtractionAttempt")
    attempt.__post_init__()
    # Nested Pydantic models are mutable: revalidate their JSON representation.
    fields_json = None
    if attempt.fields is not None:
        fields_json = attempt.fields.model_dump(mode="json")
        validated = ExtractionFields.model_validate(fields_json)
        expected_flags = derive_flags(validated)
        expected_status = derive_status(expected_flags)
    else:
        expected_flags, expected_status = set(), "failed"
    if isinstance(flags, (str, bytes)) or any(flag not in get_args(ReviewFlag) for flag in flags):
        raise ValueError("unknown review flags")
    if set(flags) != expected_flags or status != expected_status:
        raise ValueError("flags/status must match the current attempt's domain checks")
    bill = Bill(file_sha256=file_sha256, storage_key=storage_key,
                size_bytes=size_bytes, processing_status=status)
    try:
        with session.begin_nested():
            session.add(bill)
            session.flush()
            session.add(ExtractionRun(
                bill_id=bill.id, provider=attempt.provider, model=attempt.model,
                prompt_version=attempt.prompt_version, raw_response=attempt.raw_response,
                fields=fields_json,
                fields_schema_version=FIELDS_SCHEMA_VERSION if fields_json is not None else None,
                error_code=attempt.error_code, review_flags=sorted(expected_flags), status=status,
                input_tokens=attempt.input_tokens, output_tokens=attempt.output_tokens,
                latency_ms=attempt.latency_ms,
            ))
            session.flush()
    except IntegrityError as exc:
        if (getattr(exc.orig, "sqlstate", None) == "23505"
                and getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == "uq_bills_file_sha256"):
            raise BillAlreadyExists(file_sha256) from None
        raise
    return bill


def load_fields(run: ExtractionRun) -> ExtractionFields | None:
    if run.fields is None:
        if run.fields_schema_version is not None:
            raise ValueError("schema version without fields")
        return None
    if run.fields_schema_version != FIELDS_SCHEMA_VERSION:
        raise ValueError("unsupported fields schema version")
    return ExtractionFields.model_validate(run.fields)
