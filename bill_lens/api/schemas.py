from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

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
