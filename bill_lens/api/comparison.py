"""Read-only comparisons of two reviewed snapshots, with decimal arithmetic."""
from decimal import Decimal, ROUND_HALF_UP, localcontext
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bill_lens.api.errors import UploadError
from bill_lens.api.reviews import detail_in_session
from bill_lens.api.schemas import BillComparison, ComparisonMetric
from bill_lens.contract import ExtractionFields
from bill_lens.validation import billing_days, derive_flags, supply_rate_aud


def comparable_days(fields: ExtractionFields) -> int | None:
    return None if "stated_days_mismatch" in derive_flags(fields) else billing_days(fields)


def _decimal(value):
    return Decimal(value) if value is not None else None


def _comparison_precision(*fields: ExtractionFields) -> int:
    values = [value for field in fields for value in (
        field.total_usage_kwh, field.current_bill_amount,
        field.daily_supply_rate.value if field.daily_supply_rate else None,
    ) if value is not None]
    # Plain decimal strings include fractional leading zeros. Twice the widest
    # input covers subtraction across magnitudes; guard digits cover division.
    return 2 * max((len(value.lstrip("-").replace(".", "")) for value in values), default=1) + 32


def _metric(key, label, unit, a, b, *, precision=2, reason=None, note=""):
    def shown(value, places=precision):
        if value is None:
            return None
        rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        return format(abs(rounded) if rounded == 0 else rounded, "f")

    if a is None or b is None:
        reason = reason or "A value is missing from one or both reviewed bills."
    delta = b - a if not reason else None
    baseline = shown(a)
    percent_reason = reason
    if not percent_reason:
        if a <= 0:
            percent_reason = "Percentage change needs a positive baseline."
        elif Decimal(baseline) == 0:
            percent_reason = "The positive baseline rounds to zero at this display precision; percentage change is not shown."
    percentage = delta / a * 100 if not percent_reason else None
    return ComparisonMetric(
        key=key, label=label, unit=unit, precision=precision,
        baseline=baseline, comparison=shown(b), delta=shown(delta), percent_change=shown(percentage, 1),
        direction=("unavailable" if delta is None else "increase" if delta > 0 else "decrease" if delta < 0 else "unchanged"),
        unavailable_reason=reason,
        percent_unavailable_reason=percent_reason,
        note=note,
    )


def compare_fields(a: ExtractionFields, b: ExtractionFields) -> list[ComparisonMetric]:
    # Preserve long printed decimals and round only the displayed results.
    with localcontext() as context:
        context.prec = _comparison_precision(a, b)
        days_a, days_b = comparable_days(a), comparable_days(b)
        usage_a, usage_b = _decimal(a.total_usage_kwh), _decimal(b.total_usage_kwh)
        daily_a = usage_a / days_a if usage_a is not None and days_a else None
        daily_b = usage_b / days_b if usage_b is not None and days_b else None
        daily_reason = ("Daily usage needs valid period dates and no conflict with stated billing days."
                        if days_a is None or days_b is None else None)
        rate_a, rate_b = a.daily_supply_rate, b.daily_supply_rate
        rate_reason = None
        if rate_a and rate_b:
            if "unknown" in (rate_a.gst_basis, rate_b.gst_basis):
                rate_reason = "Confirm the GST basis on both supply rates before comparing."
            elif rate_a.gst_basis != rate_b.gst_basis:
                rate_reason = "The supply rates use different GST bases. No tax adjustment is assumed."
        return [
            _metric("daily_usage", "Average daily usage", "kWh / day", daily_a, daily_b,
                    reason=daily_reason, note="Total usage divided by inclusive billing-period days."),
            _metric("current_charges", "Current-period charges", "AUD", _decimal(a.current_bill_amount),
                    _decimal(b.current_bill_amount), note="Period totals include credits. Different period lengths affect this comparison."),
            _metric("total_usage", "Total usage", "kWh", usage_a, usage_b,
                    note="Total grid electricity imported during each billing period."),
            _metric("supply_rate", "Daily supply rate", "AUD / day", supply_rate_aud(rate_a), supply_rate_aud(rate_b),
                    precision=4, reason=rate_reason,
                    note="Cents are converted to AUD. A difference is shown only when both GST bases are known and match."),
        ]


def compare_bills(engine: Engine, baseline_id: UUID, comparison_id: UUID, *, same_household: bool) -> BillComparison:
    if baseline_id == comparison_id:
        raise UploadError("comparison_requires_two_bills", 422)
    if not same_household:
        raise UploadError("comparison_household_required", 422)
    with Session(engine) as session:
        # Both effective field sets and review identities come from one snapshot.
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        a, b = (detail_in_session(session, bill_id) for bill_id in (baseline_id, comparison_id))
        if a.review is None or b.review is None:
            raise UploadError("comparison_requires_review", 409)
        fields_a, fields_b = a.review.fields, b.review.fields
        warnings = []
        if a.review.review_flags or b.review.review_flags:
            warnings.append("Automated warnings remain on these reviewed values. Check the original bills before relying on the comparison.")
        if a.status == "failed" or b.status == "failed":
            warnings.append("This comparison includes manually entered values from a failed extraction.")
        days_a, days_b = comparable_days(fields_a), comparable_days(fields_b)
        if days_a is not None and days_b is not None and days_a != days_b:
            warnings.append("The billing periods have different lengths. Use average daily usage to compare consumption.")
        if billing_days(fields_a) and billing_days(fields_b):
            if max(fields_a.period_start, fields_b.period_start) <= min(fields_a.period_end, fields_b.period_end):
                warnings.append("The billing periods overlap; some days may be included in both bills.")
            elif fields_b.period_start < fields_a.period_start:
                warnings.append("The comparison bill is earlier than the baseline. Swap bills to view the change over time.")
        return BillComparison(baseline=a, comparison=b, baseline_days=days_a, comparison_days=days_b,
                              metrics=compare_fields(fields_a, fields_b), warnings=warnings)
