from copy import deepcopy

import pytest

from bill_lens.api.comparison import _comparison_precision, comparable_days, compare_fields
from bill_lens.contract import ExtractionFields


def fields(base, **changes):
    return ExtractionFields.model_validate(deepcopy(base) | changes)


def metrics(a, b):
    return {metric.key: metric for metric in compare_fields(a, b)}


def test_daily_usage_normalises_different_period_lengths(valid_fields):
    a = fields(valid_fields, total_usage_kwh="300")
    b = fields(valid_fields, period_start="2026-05-01", period_end="2026-05-15",
               stated_billing_days=15, total_usage_kwh="180", current_bill_amount="100.00")
    result = metrics(a, b)
    assert result["total_usage"].delta == "-120.00"
    daily = result["daily_usage"]
    assert (daily.baseline, daily.comparison, daily.delta, daily.percent_change) == ("10.00", "12.00", "2.00", "20.0")
    assert daily.direction == "increase"
    assert result["current_charges"].delta == "-8.07"


@pytest.mark.parametrize("changes", [
    {"period_start": None}, {"period_end": None}, {"stated_billing_days": 29},
    {"period_start": "2026-05-01"},
])
def test_invalid_or_conflicting_dates_suppress_only_daily_comparison(valid_fields, changes):
    a, b = fields(valid_fields), fields(valid_fields, **changes)
    result = metrics(a, b)
    assert comparable_days(b) is None
    assert result["daily_usage"].comparison is None
    assert result["daily_usage"].delta is None and result["daily_usage"].unavailable_reason
    assert result["total_usage"].delta == "0.00"
    assert result["current_charges"].delta == "0.00"


def test_missing_stated_days_uses_inclusive_reviewed_dates(valid_fields):
    a = fields(valid_fields, period_start="2024-02-28", period_end="2024-03-01", stated_billing_days=None)
    assert comparable_days(a) == 3


def test_missing_values_are_not_zero(valid_fields):
    a = fields(valid_fields)
    b = fields(valid_fields, total_usage_kwh=None, current_bill_amount=None, daily_supply_rate=None)
    for metric in metrics(a, b).values():
        assert metric.baseline is not None and metric.comparison is None
        assert metric.delta is None and metric.percent_change is None
        assert metric.direction == "unavailable"


@pytest.mark.parametrize("baseline,compared,delta,direction", [
    ("0", "10", "10.00", "increase"), ("0", "0", "0.00", "unchanged"),
    ("-4.00", "5.00", "9.00", "increase"), ("-4", "-10", "-6.00", "decrease"),
])
def test_zero_and_credit_baselines_have_no_percentage(valid_fields, baseline, compared, delta, direction):
    metric = metrics(fields(valid_fields, current_bill_amount=baseline), fields(valid_fields, current_bill_amount=compared))["current_charges"]
    assert metric.delta == delta and metric.direction == direction
    assert metric.percent_change is None and metric.percent_unavailable_reason


def test_exact_unit_conversion_and_matching_gst(valid_fields):
    a = fields(valid_fields)
    b = fields(valid_fields, daily_supply_rate={"value": "1.1023", "unit": "AUD/day", "gst_basis": "inclusive"})
    result = metrics(a, b)["supply_rate"]
    assert result.baseline == result.comparison == "1.1023"
    assert result.delta == "0.0000" and result.percent_change == "0.0"


@pytest.mark.parametrize("basis", ["exclusive", "unknown"])
def test_unknown_or_different_gst_suppresses_rate_change(valid_fields, basis):
    a = fields(valid_fields)
    rate = valid_fields["daily_supply_rate"] | {"gst_basis": basis}
    result = metrics(a, fields(valid_fields, daily_supply_rate=rate))["supply_rate"]
    assert result.baseline == result.comparison == "1.1023"
    assert result.delta is None and result.percent_change is None and result.unavailable_reason


def test_two_unknown_gst_bases_are_not_assumed_equal(valid_fields):
    a = fields(valid_fields, daily_supply_rate=valid_fields["daily_supply_rate"] | {"gst_basis": "unknown"})
    assert metrics(a, a)["supply_rate"].delta is None


def test_differences_use_unrounded_values_and_preserve_small_direction(valid_fields):
    result = metrics(fields(valid_fields, current_bill_amount="10.004"), fields(valid_fields, current_bill_amount="10.006"))["current_charges"]
    assert (result.baseline, result.comparison, result.delta) == ("10.00", "10.01", "0.00")
    assert result.direction == "increase" and result.percent_change == "0.0"


def test_long_decimal_inputs_remain_exact_and_are_not_mutated(valid_fields):
    a = fields(valid_fields, current_bill_amount="1000000000000000000000000000000.01")
    b = fields(valid_fields, current_bill_amount="1000000000000000000000000000000.02")
    before = a.model_dump_json(), b.model_dump_json()
    assert metrics(a, b)["current_charges"].delta == "0.01"
    assert (a.model_dump_json(), b.model_dump_json()) == before


@pytest.mark.parametrize("baseline,shown,has_percentage", [
    ("0.0001", "0.00", False), ("0.004999", "0.00", False),
    ("0.005", "0.01", True), ("0.01", "0.01", True),
])
def test_percentage_requires_a_visibly_positive_baseline(valid_fields, baseline, shown, has_percentage):
    result = metrics(fields(valid_fields, current_bill_amount=baseline),
                     fields(valid_fields, current_bill_amount="1"))["current_charges"]
    assert result.baseline == shown
    assert (result.percent_change is not None) == has_percentage
    assert result.delta is not None and result.direction == "increase"
    if not has_percentage:
        assert "positive baseline rounds to zero" in result.percent_unavailable_reason


def test_near_zero_daily_usage_and_supply_rate_use_their_display_precision(valid_fields):
    a = fields(valid_fields, total_usage_kwh="0.12",
               daily_supply_rate={"value": "0.0049", "unit": "cents/day", "gst_basis": "inclusive"})
    result = metrics(a, fields(valid_fields))
    for key, shown in [("daily_usage", "0.00"), ("supply_rate", "0.0000")]:
        assert result[key].baseline == shown
        assert result[key].percent_change is None
        assert "rounds to zero" in result[key].percent_unavailable_reason
    assert result["total_usage"].percent_change is not None


def test_precision_ignores_retailer_text_and_preserves_widely_separated_magnitudes(valid_fields):
    a = fields(valid_fields, current_bill_amount="1" + "0" * 60 + ".01")
    b = fields(valid_fields, current_bill_amount="0." + "0" * 60 + "1")
    renamed = fields(valid_fields, retailer="Long retailer name " * 1000, current_bill_amount=a.current_bill_amount)
    assert _comparison_precision(a, b) == _comparison_precision(renamed, b)
    forward, reverse = metrics(a, b)["current_charges"], metrics(b, a)["current_charges"]
    assert forward.delta == "-" + a.current_bill_amount
    assert reverse.delta == a.current_bill_amount
    assert reverse.percent_change is None
    assert metrics(renamed, b) == metrics(a, b)


def test_equal_daily_usage_from_different_periods_remains_equal(valid_fields):
    a = fields(valid_fields, total_usage_kwh="1", period_start="2026-04-01", period_end="2026-04-03", stated_billing_days=3)
    b = fields(valid_fields, total_usage_kwh="2", period_start="2026-04-01", period_end="2026-04-06", stated_billing_days=6)
    daily = metrics(a, b)["daily_usage"]
    assert daily.direction == "unchanged" and daily.delta == "0.00"
