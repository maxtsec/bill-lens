from datetime import datetime
from typing import Literal
from uuid import UUID

import unicodedata

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from bill_lens.contract import ExtractionFields, ReviewFlag
from bill_lens.extraction import ExtractionErrorCode


class RunMetadata(BaseModel):
    id: UUID
    provider: str
    model: str
    prompt_version: str
    fields_schema_version: int | None
    error_code: ExtractionErrorCode | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    created_at: datetime


class BillResponse(BaseModel):
    id: UUID
    file_sha256: str
    status: Literal["processed", "needs_review", "failed"]
    flags: list[ReviewFlag]
    fields: ExtractionFields | None
    billing_days: str | None
    daily_supply_rate_aud: str | None
    created_at: datetime
    updated_at: datetime
    run: RunMetadata


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_run_id: UUID
    expected_review_id: UUID | None  # Required, including null for the first review.
    fields: ExtractionFields
    reviewer: str = Field(min_length=1, max_length=80, strict=True)
    note: str = Field(default="", max_length=2000, strict=True)
    acknowledged: StrictBool

    @field_validator("reviewer", "note")
    @classmethod
    def safe_text(cls, value: str) -> str:
        if any(unicodedata.category(c) in {"Cc", "Cs"} and c not in "\n\t" for c in value):
            raise ValueError("invalid control character")
        return value.strip()

    @field_validator("reviewer")
    @classmethod
    def visible_reviewer(cls, value: str) -> str:
        if any(unicodedata.category(c) in {"Cf", "Zl", "Zp"} for c in value):
            raise ValueError("reviewer must not contain invisible formatting or line separators")
        if not any(unicodedata.category(c)[0] in "LNPS" for c in value):
            raise ValueError("reviewer must contain visible characters")
        return value

    @field_validator("reviewer", mode="before")
    @classmethod
    def single_line_reviewer(cls, value):
        if isinstance(value, str) and any(unicodedata.category(c) in {"Cc", "Cs", "Cf", "Zl", "Zp"} for c in value):
            raise ValueError("reviewer must be a single-line name without control characters")
        return value

    @field_validator("reviewer")
    @classmethod
    def named_reviewer(cls, value: str) -> str:
        if not value or "\n" in value or "\t" in value:
            raise ValueError("reviewer must be a nonblank single-line name")
        return value


class ReviewResponse(BaseModel):
    id: UUID
    source_run_id: UUID
    revision: int
    action: Literal["confirmed", "corrected"]
    reviewer: str
    note: str
    fields: ExtractionFields
    review_flags: list[ReviewFlag]
    created_at: datetime


class BillDetail(BillResponse):
    review_state: Literal["pending", "reviewed"]
    latest_review_id: UUID | None
    review: ReviewResponse | None
    effective_fields: ExtractionFields | None


class BillCounts(BaseModel):
    all: int
    pending: int
    reviewed: int


class BillList(BaseModel):
    items: list[BillDetail]
    total: int
    limit: int
    offset: int
    counts: BillCounts


class ReviewHistory(BaseModel):
    items: list[ReviewResponse]
    total: int
    limit: int
    offset: int
    next_before_revision: int | None


class ComparisonMetric(BaseModel):
    key: str
    label: str
    unit: str
    precision: int
    baseline: str | None
    comparison: str | None
    delta: str | None
    percent_change: str | None
    direction: Literal["increase", "decrease", "unchanged", "unavailable"]
    unavailable_reason: str | None
    percent_unavailable_reason: str | None
    note: str


class BillComparison(BaseModel):
    baseline: BillDetail
    comparison: BillDetail
    baseline_days: int | None
    comparison_days: int | None
    metrics: list[ComparisonMetric]
    warnings: list[str]
