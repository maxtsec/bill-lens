"""Human decisions are versioned independently of immutable extraction results."""
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, func, or_, select, update
from sqlalchemy.orm import Session, aliased, defer

from bill_lens.api.errors import UploadError
from bill_lens.api.schemas import BillDetail, BillList, ReviewHistory, ReviewRequest, ReviewResponse
from bill_lens.api.service import _response, bill_response
from bill_lens.contract import ExtractionFields
from bill_lens.db.models import Bill, BillReview, ExtractionRun
from bill_lens.db.repository import current_run_statement, load_fields
from bill_lens.pdf_text import extract_pdf_text
from bill_lens.validation import derive_review_flags


def latest_review_statement(bill_id):
    return select(BillReview).where(BillReview.bill_id == bill_id).order_by(BillReview.revision.desc()).limit(1)


def review_response(review: BillReview) -> ReviewResponse:
    if review.fields_schema_version != 1:
        raise ValueError("unsupported review fields schema")
    return ReviewResponse.model_validate(review, from_attributes=True)


def review_applies(latest, run):
    # Successful-first current-run selection means a current failure has no
    # successful extraction to supersede a manual review of this same PDF.
    return latest is not None and (latest.source_run_id == run.id or run.error_code is not None)


def _detail(original, latest):
    review = review_response(latest) if review_applies(latest, original.run) else None
    return BillDetail(**dict(original), review_state="reviewed" if review else "pending",
                      latest_review_id=latest.id if latest else None, review=review,
                      effective_fields=review.fields if review else original.fields)


def get_detail(engine: Engine, bill_id: UUID) -> BillDetail:
    with Session(engine) as session:
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return detail_in_session(session, bill_id)


def detail_in_session(session: Session, bill_id: UUID) -> BillDetail:
    bill = session.get(Bill, bill_id)
    if bill is None:
        raise UploadError("bill_not_found", 404)
    return _detail(_response(session, bill), session.scalar(latest_review_statement(bill.id)))


def list_bills(engine: Engine, *, limit=20, offset=0, status=None, review_state=None):
    # Correlated scalar IDs use the same successful-first ordering as GET/upload.
    run_id = (select(ExtractionRun.id).where(ExtractionRun.bill_id == Bill.id)
              .order_by(ExtractionRun.error_code.is_(None).desc(), ExtractionRun.created_at.desc(),
                        ExtractionRun.id.desc()).limit(1).correlate(Bill).scalar_subquery())
    review_id = (select(BillReview.id).where(BillReview.bill_id == Bill.id)
                 .order_by(BillReview.revision.desc()).limit(1).correlate(Bill).scalar_subquery())
    latest = aliased(BillReview)
    statement = (select(Bill, ExtractionRun, latest).select_from(Bill)
                 .join(ExtractionRun, ExtractionRun.id == run_id).outerjoin(latest, latest.id == review_id))
    base = statement
    applicable = latest.id.is_not(None) & or_(latest.source_run_id == ExtractionRun.id,
                                            ExtractionRun.error_code.is_not(None))
    if status:
        statement = statement.where(ExtractionRun.status == status)
    if review_state == "reviewed":
        statement = statement.where(applicable)
    elif review_state == "pending":
        statement = statement.where(~applicable)
    with Session(engine) as session:
        # Repeatable read keeps count, filtering and all page details in one snapshot.
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        counts = session.execute(base.with_only_columns(
            func.count().label("all"),
            func.count().filter(~applicable).label("pending"),
            func.count().filter(applicable).label("reviewed"),
        )).mappings().one()
        records = session.execute(statement.options(defer(ExtractionRun.raw_response, raiseload=True))
                                  .order_by(Bill.created_at.desc(), Bill.id.desc()).offset(offset).limit(limit)).all()
        return BillList(items=[_detail(bill_response(bill, run), review) for bill, run, review in records],
                        total=total, limit=limit, offset=offset, counts=dict(counts))


def pdf_path(session: Session, bill_id: UUID, storage_root: Path) -> Path:
    bill = session.get(Bill, bill_id)
    if bill is None:
        raise UploadError("bill_not_found", 404)
    root = storage_root.resolve()
    path = (root / bill.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise UploadError("pdf_not_found", 404)
    return path


def get_pdf(engine: Engine, bill_id: UUID, storage_root: Path) -> Path:
    with Session(engine) as session:
        return pdf_path(session, bill_id, storage_root)


def history(engine: Engine, bill_id: UUID, *, limit=20, offset=0, before_revision=None):
    if before_revision is not None and offset:
        raise UploadError("invalid_request", 422)
    with Session(engine) as session:
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        if session.get(Bill, bill_id) is None:
            raise UploadError("bill_not_found", 404)
        query = select(BillReview).where(BillReview.bill_id == bill_id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        if before_revision is not None:
            query = query.where(BillReview.revision < before_revision)
        records = session.scalars(query.order_by(BillReview.revision.desc()).offset(offset).limit(limit + 1)).all()
        next_cursor = records[limit - 1].revision if len(records) > limit else None
        return ReviewHistory(items=[review_response(r) for r in records[:limit]], total=total,
                             limit=limit, offset=offset, next_before_revision=next_cursor)


def save_review(engine: Engine, storage_root: Path, bill_id: UUID, request: ReviewRequest):
    if not request.acknowledged:
        raise UploadError("review_acknowledgement_required", 422)
    # Parse the saved PDF without holding a DB connection or the bill's row lock.
    with Session(engine) as session:
        path = pdf_path(session, bill_id, storage_root)
        digest = session.get(Bill, bill_id).file_sha256
    document = extract_pdf_text(path.read_bytes())
    if document.file_sha256 != digest:
        raise UploadError("pdf_integrity_error", 409)
    fields = ExtractionFields.model_validate(request.fields.model_dump(mode="json"))
    flags = sorted(derive_review_flags(fields, document))
    with Session(engine) as session, session.begin():
        bill = session.scalar(select(Bill).where(Bill.id == bill_id).with_for_update())
        if bill is None:
            raise UploadError("bill_not_found", 404)
        run = session.scalar(current_run_statement(bill_id))
        latest = session.scalar(latest_review_statement(bill_id))
        if (run.id != request.source_run_id or (latest.id if latest else None) != request.expected_review_id):
            raise UploadError("review_conflict", 409)
        previous = (ExtractionFields.model_validate(latest.fields) if review_applies(latest, run)
                    else load_fields(run))
        if previous is None:
            previous = ExtractionFields.model_validate({key: None for key in ExtractionFields.model_fields})
        review = BillReview(bill_id=bill.id, source_run_id=run.id, revision=latest.revision + 1 if latest else 1,
                            action="confirmed" if fields == previous else "corrected", reviewer=request.reviewer,
                            note=request.note, fields=fields.model_dump(mode="json"), fields_schema_version=1,
                            review_flags=flags)
        session.add(review)
        session.flush()
        # Existing trigger advances updated_at; machine status is not changed.
        session.execute(update(Bill).where(Bill.id == bill_id).values(processing_status=bill.processing_status))
        return review_response(review)
