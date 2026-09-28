"""Upload orchestration, independent of HTTP request/response objects."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, defer

from bill_lens.api.errors import UploadError
from bill_lens.api.schemas import BillResponse, RunMetadata
from bill_lens.api.storage import write_pdf
from bill_lens.db.models import Bill, ExtractionRun
from bill_lens.db.repository import BillAlreadyExists, create_bill_with_run, get_bill_by_hash, load_fields
from bill_lens.extraction import BillExtractor
from bill_lens.pdf_text import extract_pdf_text
from bill_lens.validation import billing_days, derive_flags, derive_status, supply_rate_aud


def _response(session: Session, bill: Bill) -> BillResponse:
    run = session.scalars(
        select(ExtractionRun).where(ExtractionRun.bill_id == bill.id)
        .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
        .options(defer(ExtractionRun.raw_response, raiseload=True)).limit(1)
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
    if existing := _existing(engine, digest):
        return existing, False
    # _existing closes its session before this call: no connection or transaction
    # is held during extraction. Simultaneous identical uploads may both extract;
    # the full-hash UNIQUE constraint decides which result is persisted.
    attempt = extractor.extract(document)
    flags = derive_flags(attempt.fields) if attempt.fields else set()
    status = derive_status(flags) if attempt.fields else "failed"
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
