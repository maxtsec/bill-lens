from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CHAR, CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (
        UniqueConstraint("file_sha256", name="uq_bills_file_sha256"),
        UniqueConstraint("storage_key", name="uq_bills_storage_key"),
        CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="ck_bills_hash"),
        CheckConstraint("storage_key ~ '^bills/[0-9a-f]{32}[.]pdf$'", name="ck_bills_storage_key"),
        CheckConstraint("size_bytes > 0", name="ck_bills_size"),
        CheckConstraint("processing_status IN ('processed', 'needs_review', 'failed')", name="ck_bills_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    file_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    processing_status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        CheckConstraint("provider ~ '[^[:space:]]'", name="ck_runs_provider"),
        CheckConstraint("model ~ '[^[:space:]]'", name="ck_runs_model"),
        CheckConstraint("prompt_version ~ '[^[:space:]]'", name="ck_runs_prompt_version"),
        CheckConstraint("error_code IN ('rate_limited', 'timeout', 'refused', 'truncated', 'invalid_output', 'provider_error')", name="ck_runs_error_code"),
        CheckConstraint("(fields IS NOT NULL) <> (error_code IS NOT NULL)", name="ck_runs_outcome"),
        CheckConstraint("(fields IS NULL AND error_code <> 'invalid_output') OR raw_response IS NOT NULL", name="ck_runs_raw_response"),
        CheckConstraint("jsonb_typeof(fields) = 'object'", name="ck_runs_fields_object"),
        CheckConstraint("(fields IS NULL AND fields_schema_version IS NULL) OR (fields IS NOT NULL AND fields_schema_version IS NOT NULL AND fields_schema_version > 0)", name="ck_runs_schema_version"),
        CheckConstraint("jsonb_typeof(review_flags) = 'array'", name="ck_runs_flags_array"),
        CheckConstraint("status IN ('processed', 'needs_review', 'failed')", name="ck_runs_status"),
        CheckConstraint("(status = 'failed') = (error_code IS NOT NULL)", name="ck_runs_failed"),
        CheckConstraint("(status = 'needs_review' AND review_flags <> '[]'::jsonb) OR (status IN ('processed', 'failed') AND review_flags = '[]'::jsonb)", name="ck_runs_status_flags"),
        CheckConstraint("input_tokens >= 0", name="ck_runs_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="ck_runs_output_tokens"),
        CheckConstraint("latency_ms >= 0", name="ck_runs_latency"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    bill_id: Mapped[UUID] = mapped_column(ForeignKey("bills.id", name="fk_runs_bill"), index=True)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    raw_response: Mapped[str | None] = mapped_column(Text)
    fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    fields_schema_version: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(Text)
    review_flags: Mapped[list[str]] = mapped_column(JSONB(none_as_null=True), server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    latency_ms: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
