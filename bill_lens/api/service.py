"""Upload orchestration, independent of HTTP request/response objects."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bill_lens.api.errors import UploadError
from bill_lens.api.schemas import BillResponse, RunMetadata
from bill_lens.api.storage import write_pdf
from bill_lens.db.models import Bill, ExtractionRun
from bill_lens.db.repository import (
    BillAlreadyExists, append_extraction_run, create_bill_with_run,
    current_run_statement, get_bill_by_hash, load_fields,
)
from bill_lens.extraction import BillExtractor
from bill_lens.pdf_text import extract_pdf_text
from bill_lens.validation import billing_days, derive_flags, derive_status, supply_rate_aud

RETRYABLE_ERRORS = frozenset({"rate_limited", "timeout", "provider_error"})


def _response(session: Session, bill: Bill) -> BillResponse:
    # One statement snapshots both current run and Bill metadata. Refresh a Bill
    # already loaded by an earlier lookup if a retry committed in between.
    run, bill = session.execute(
        current_run_statement(bill.id).add_columns(Bill)
        .join(Bill, Bill.id == ExtractionRun.bill_id)
        .execution_options(populate_existing=True)
    ).one()
    fields = load_fields(run)
    days = billing_days(fields) if fields else None
    rate = supply_rate_aud(fields.daily_supply_rate) if fields else None
    return BillResponse(
        id=bill.id, file_sha256=bill.file_sha256, status=run.status,
        flags=run.review_flags, fields=fields,
        billing_days=str(days) if days is not None else None,
        daily_supply_rate_aud=format(rate, "f") if rate is not None else None,
        created_at=bill.created_at, updated_at=bill.updated_at,
        run=RunMetadata.model_validate(run, from_attributes=True),
    )


def get_bill(engine: Engine, bill_id: UUID) -> BillResponse:
    with Session(engine) as session:
        bill = session.get(Bill, bill_id)
        if bill is None:
            raise UploadError("bill_not_found", 404)
        return _response(session, bill)


def _existing(engine: Engine, digest: str) -> BillResponse | None:
    with Session(engine) as session:
        bill = get_bill_by_hash(session, digest)
        return _response(session, bill) if bill else None


def upload_bill(data: bytes, *, engine: Engine, storage_root: Path,
                extractor: BillExtractor) -> tuple[BillResponse, bool]:
    document = extract_pdf_text(data)
    digest = document.file_sha256
    existing = _existing(engine, digest)
    if existing and existing.run.error_code not in RETRYABLE_ERRORS:
        return existing, False
    # _existing closes its session before this call: no connection or transaction
    # is held during extraction. First-upload races use UNIQUE; existing-bill
    # retries each append their result under a short row lock afterwards.
    attempt = extractor.extract(document)
    flags = derive_flags(attempt.fields) if attempt.fields else set()
    status = derive_status(flags) if attempt.fields else "failed"
    if existing:
        # Keep the original file. Even if another retry has now succeeded, save
        # this attempt; the repository prevents a late failure from downgrading it.
        with Session(engine) as session, session.begin():
            bill = append_extraction_run(session, bill_id=existing.id,
                                         attempt=attempt, flags=flags, status=status)
            result = _response(session, bill)
        return result, False
    key, path = write_pdf(storage_root, data)
    commit_started = False
    try:
        with Session(engine) as session, session.begin():
            bill = create_bill_with_run(
                session, file_sha256=digest, storage_key=key, size_bytes=len(data),
                attempt=attempt, flags=flags, status=status,
            )
            result = _response(session, bill)
            commit_started = True
    except BillAlreadyExists:
        path.unlink(missing_ok=True)
        existing = _existing(engine, digest)
        if existing is None:
            raise RuntimeError("duplicate bill disappeared") from None
        return existing, False
    except Exception:
        if not commit_started:
            path.unlink(missing_ok=True)
        else:
            # A lost commit acknowledgement may still mean committed rows.
            # Verify before deleting; if the DB is unavailable, retain the
            # opaque file for reconciliation instead of breaking a saved bill.
            with Session(engine) as check:
                saved = get_bill_by_hash(check, digest)
                if saved is None or saved.storage_key != key:
                    path.unlink(missing_ok=True)
        raise
    return result, True
