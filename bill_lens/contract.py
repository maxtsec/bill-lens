"""Validate the M0 wire format without inferring missing source values."""

import re
import unicodedata
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
    value: NonnegativeDecimal = Field(description=(
        "Printed nonnegative daily unit price as a plain decimal string. Preserve "
        "printed precision; do not convert units, change GST basis or use the period charge."
    ))
    unit: Literal["cents/day", "AUD/day"] = Field(description=(
        "Map c/day, c per day and cents-symbol/day to cents/day. Map $/day and "
        "AUD/day to AUD/day only when the currency is clearly Australian dollars."
    ))
    gst_basis: Literal["inclusive", "exclusive", "unknown"] = Field(description=(
        "GST basis of the printed supply rate: inclusive or exclusive only when "
        "supported by the bill; unknown when unstated or unclear. Never assume inclusive."
    ))


class ExtractionFields(ContractModel):
    # Nullable keys are still required: omission is a schema error.
    retailer: StrictStr | None = Field(description=(
        "Retailer selection in priority order: (1) Extract the most complete "
        "customer-facing brand name as printed, over a stylised logo abbreviation "
        "when both clearly identify the same retailer. (2) A legal-entity name "
        "(Pty Ltd, Limited, ABN/ACN in fine print or a legal notice) does not replace "
        "a printed brand name. (3) If only a legal-entity name identifies the retailer, "
        "extract it exactly as printed, including its suffix; exclude ABN/ACN labels "
        "and identifier numbers from the name. (4) If only an unambiguous abbreviation "
        "is printed, keep it; never expand it from memory or outside data. "
        "(5) Never substitute a distributor, network operator, parent or group company. "
        "(6) If missing or not unambiguously identifiable, return null. Use context; "
        "do not choose the longest name or blindly strip suffixes. "
        "Control characters (Unicode Cc) and "
        "surrogate code points (Cs) are invalid; never include them in a name."
    ))
    period_start: ISODate | None = Field(description=(
        "First inclusive date of the electricity service period, as YYYY-MM-DD. "
        "Use the bill's stated date format or unambiguous context for Australian dates; "
        "do not assume US month/day order. Use null if missing or unresolved. "
        "Do not substitute the issue date or payment due date."
    ))
    period_end: ISODate | None = Field(description=(
        "Last inclusive date of the electricity service period, as YYYY-MM-DD. "
        "Use the bill's stated date format or unambiguous context for Australian dates; "
        "do not assume US month/day order. Use null if missing or unresolved. "
        "Preserve source dates even if reversed; Python checks their order."
    ))
    stated_billing_days: Annotated[StrictInt, Field(gt=0)] | None = Field(
        description=(
            "The explicitly labelled billing-period day count, such as Billing days "
            "or Days in period. Exclude quantities on charge lines, including supply days. "
            "Use null if no unambiguous period-level count is printed. Never calculate it "
            "from dates or select a value because it agrees with the dates."
        )
    )
    total_usage_kwh: NonnegativeDecimal | None = Field(description=(
        "Explicitly printed total grid electricity imported during the period in kWh, "
        "as a nonnegative plain decimal string preserving printed precision. Zero is valid. "
        "Do not add tariff lines or subtract/include solar exports. Use null if no "
        "unambiguous import total is printed."
    ))
    daily_supply_rate: SupplyRate | None = Field(description=(
        "One printed daily supply unit price with its unit and GST basis, not the "
        "period's total supply charge. Do not convert or average rates. Use null if "
        "missing, if multiple rates have no single representative rate, or if the unit "
        "cannot be identified. A readable rate with unstated GST basis uses unknown."
    ))
    current_bill_amount: DecimalString | None = Field(description=(
        "Explicitly printed net current-period total in AUD as a signed plain decimal "
        "string, preserving printed precision. Includes current charges, fees, adjustments, "
        "already-applied discounts, solar credits and GST; excludes previous balances and "
        "account payments. Exclude unapplied conditional discounts; use null if alternative "
        "totals are ambiguous. A current-period 4.00 CR becomes -4.00. Do not copy amount "
        "due or calculate a total from line items. Use null if no identifiable current "
        "total is printed."
    ))

    @field_validator("retailer")
    @classmethod
    def retailer_not_blank(cls, value: str | None) -> str | None:
        if value is not None and any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
            raise ValueError("retailer must not contain control characters or surrogate code points")
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
