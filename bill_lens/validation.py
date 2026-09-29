"""M0 domain checks. Inputs must already pass schema validation."""

from collections.abc import Collection
from decimal import Decimal, localcontext

from bill_lens.contract import ExtractionFields, ReviewFlag, Status, SupplyRate
from bill_lens.current_amount_role import derive_current_amount_role_flags
from bill_lens.document_validation import derive_document_flags
from bill_lens.pdf_text import PdfText


def billing_days(fields: ExtractionFields) -> int | None:
    start, end = fields.period_start, fields.period_end
    if start is None or end is None or end < start:
        return None
    return (end - start).days + 1


def supply_rate_aud(rate: SupplyRate | None) -> Decimal | None:
    """Convert units exactly. The caller must keep the original GST basis."""
    if rate is None:
        return None
    value = Decimal(rate.value)
    # Avoid rounding even when a valid printed rate exceeds Decimal's default precision.
    with localcontext() as context:
        context.prec = max(context.prec, len(value.as_tuple().digits))
        return value / Decimal(100) if rate.unit == "cents/day" else value


def derive_flags(fields: ExtractionFields) -> set[ReviewFlag]:
    flags: set[ReviewFlag] = set()
    missing_fields: dict[str, ReviewFlag] = {
        "retailer": "retailer_missing",
        "period_start": "period_start_missing",
        "period_end": "period_end_missing",
        "total_usage_kwh": "total_usage_kwh_missing",
        "daily_supply_rate": "daily_supply_rate_missing",
        "current_bill_amount": "current_bill_amount_missing",
    }
    for name, flag in missing_fields.items():
        if getattr(fields, name) is None:
            flags.add(flag)

    start, end = fields.period_start, fields.period_end
    if start is not None and end is not None and end < start:
        flags.add("period_end_before_start")
    days = billing_days(fields)
    if days is not None and fields.stated_billing_days is not None and days != fields.stated_billing_days:
        flags.add("stated_days_mismatch")
    if fields.daily_supply_rate is not None and fields.daily_supply_rate.gst_basis == "unknown":
        flags.add("supply_rate_gst_basis_unknown")
    return flags


def derive_status(flags: Collection[ReviewFlag]) -> Status:
    return "needs_review" if flags else "processed"


def derive_review_flags(fields: ExtractionFields, document: PdfText) -> set[ReviewFlag]:
    """One review decision for upload, evaluation and the smoke check."""
    return (derive_flags(fields) | derive_document_flags(fields, document)
            | derive_current_amount_role_flags(fields, document))
