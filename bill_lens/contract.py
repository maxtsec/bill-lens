"""Validate the M0 wire format without inferring missing source values."""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
)


def decimal_string(value: str) -> str:
    if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value) is None:
        raise ValueError("expected a plain decimal string")
    return value


def nonnegative(value: str) -> str:
    if Decimal(value) < 0:
        raise ValueError("value must be nonnegative")
    return value


def iso_date(value: object) -> date:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("expected an ISO YYYY-MM-DD date string")
    return date.fromisoformat(value)


DecimalString = Annotated[StrictStr, AfterValidator(decimal_string)]
NonnegativeDecimal = Annotated[DecimalString, AfterValidator(nonnegative)]
ISODate = Annotated[date, BeforeValidator(iso_date)]
ReviewFlag = Literal[
    "current_bill_amount_missing",
    "daily_supply_rate_missing",
    "period_end_before_start",
    "period_end_missing",
    "period_start_missing",
    "retailer_missing",
    "stated_days_mismatch",
    "supply_rate_gst_basis_unknown",
    "total_usage_kwh_missing",
]
Status = Literal["processed", "needs_review"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SupplyRate(ContractModel):
    value: NonnegativeDecimal
    unit: Literal["cents/day", "AUD/day"]
    gst_basis: Literal["inclusive", "exclusive", "unknown"]


class ExtractionFields(ContractModel):
    # Nullable keys are still required: omission is a schema error.
    retailer: StrictStr | None
    period_start: ISODate | None
    period_end: ISODate | None
    stated_billing_days: Annotated[StrictInt, Field(gt=0)] | None
    total_usage_kwh: NonnegativeDecimal | None
    daily_supply_rate: SupplyRate | None
    current_bill_amount: DecimalString | None

    @field_validator("retailer")
    @classmethod
    def retailer_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("use null for an unidentified retailer")
        return value


class ExpectedLabel(ContractModel):
    schema_version: Annotated[StrictInt, Field(ge=1, le=1)]
    fields: ExtractionFields
    expected_status: Status
    expected_flags: list[ReviewFlag]

    @field_validator("expected_flags")
    @classmethod
    def sorted_unique_flags(cls, value: list[ReviewFlag]) -> list[ReviewFlag]:
        if value != sorted(set(value)):
            raise ValueError("expected_flags must be sorted and unique")
        return value
