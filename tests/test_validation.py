from decimal import Decimal

import pytest

from bill_lens.contract import ExtractionFields, SupplyRate
from bill_lens.validation import billing_days, derive_flags, derive_status, supply_rate_aud


@pytest.mark.parametrize("field,expected", [
    ("retailer", "retailer_missing"),
    ("period_start", "period_start_missing"),
    ("period_end", "period_end_missing"),
    ("total_usage_kwh", "total_usage_kwh_missing"),
    ("daily_supply_rate", "daily_supply_rate_missing"),
    ("current_bill_amount", "current_bill_amount_missing"),
])
def test_each_missing_field_has_one_distinct_flag(valid_fields, field, expected):
    valid_fields[field] = None
    assert derive_flags(ExtractionFields.model_validate(valid_fields)) == {expected}


def test_multiple_missing_fields_are_all_reported(valid_fields):
    fields = ExtractionFields.model_validate(dict.fromkeys(valid_fields))
    assert derive_flags(fields) == {
        "retailer_missing", "period_start_missing", "period_end_missing",
        "total_usage_kwh_missing", "daily_supply_rate_missing", "current_bill_amount_missing",
    }
    assert billing_days(fields) is None


def test_unstated_day_count_is_optional(valid_fields):
    valid_fields["stated_billing_days"] = None
    fields = ExtractionFields.model_validate(valid_fields)
    assert billing_days(fields) == 30
    assert derive_flags(fields) == set()


@pytest.mark.parametrize("start,end,expected", [
    ("2026-04-01", "2026-04-01", 1),
    ("2024-02-01", "2024-02-29", 29),
    ("2026-12-31", "2027-01-01", 2),
    ("2026-06-05", "2026-07-04", 30),
])
def test_inclusive_calendar_days(valid_fields, start, end, expected):
    valid_fields.update(period_start=start, period_end=end, stated_billing_days=expected)
    fields = ExtractionFields.model_validate(valid_fields)
    assert billing_days(fields) == expected
    assert derive_flags(fields) == set()


def test_reversed_period_suppresses_day_comparison(valid_fields):
    valid_fields.update(period_start="2026-05-06", period_end="2026-04-07")
    fields = ExtractionFields.model_validate(valid_fields)
    assert billing_days(fields) is None
    assert derive_flags(fields) == {"period_end_before_start"}


def test_source_day_disagreement_is_retained(valid_fields):
    valid_fields.update(period_start="2026-08-01", period_end="2026-08-31")
    fields = ExtractionFields.model_validate(valid_fields)
    assert billing_days(fields) == 31
    assert derive_flags(fields) == {"stated_days_mismatch"}
    assert fields.stated_billing_days == 30


def test_unknown_gst_keeps_rate_and_flags_review(valid_fields):
    valid_fields["daily_supply_rate"]["gst_basis"] = "unknown"
    fields = ExtractionFields.model_validate(valid_fields)
    assert derive_flags(fields) == {"supply_rate_gst_basis_unknown"}
    assert supply_rate_aud(fields.daily_supply_rate) == Decimal("1.1023")
    assert fields.daily_supply_rate.gst_basis == "unknown"


@pytest.mark.parametrize("value,unit,expected", [
    ("110.23", "cents/day", "1.1023"),
    ("1.00", "AUD/day", "1.00"),
    ("0", "cents/day", "0"),
    ("123456789012345678901234567890.1234", "cents/day", "1234567890123456789012345678.901234"),
])
@pytest.mark.parametrize("gst_basis", ["inclusive", "exclusive", "unknown"])
def test_rate_conversion_is_exact_and_retains_gst(value, unit, expected, gst_basis):
    rate = SupplyRate(value=value, unit=unit, gst_basis=gst_basis)
    assert supply_rate_aud(rate) == Decimal(expected)
    assert rate.gst_basis == gst_basis


def test_missing_rate_has_no_derived_value():
    assert supply_rate_aud(None) is None


def test_status_depends_on_presence_of_flags():
    assert derive_status(set()) == "processed"
    assert derive_status({"retailer_missing"}) == "needs_review"


def test_zero_usage_and_net_credit_do_not_require_review(valid_fields):
    valid_fields.update(total_usage_kwh="0", current_bill_amount="-4.00")
    assert derive_flags(ExtractionFields.model_validate(valid_fields)) == set()
