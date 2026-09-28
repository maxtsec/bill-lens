from decimal import Decimal

import pytest

from bill_lens.contract import ExtractionFields
from scripts import live_openai_check as smoke


@pytest.mark.parametrize("enabled,key", [(None, None), ("1", None), (None, "test-key"), ("0", "test-key")])
def test_smoke_requires_both_gates_before_client_or_files(enabled, key, monkeypatch):
    if enabled is not None:
        monkeypatch.setenv("BILL_LENS_LIVE", enabled)
    if key is not None:
        monkeypatch.setenv("OPENAI_API_KEY", key)
    def forbidden(*args, **kwargs):
        pytest.fail("a closed gate must not create a client")
    monkeypatch.setattr(smoke, "OpenAIExtractor", forbidden)
    with pytest.raises(SystemExit) as error:
        smoke.main(["--dataset", "nonexistent"])
    assert error.value.code == 2


def test_smoke_matches_use_contract_comparison(valid_fields):
    expected = ExtractionFields.model_validate(valid_fields)
    actual = ExtractionFields.model_validate(valid_fields | {
        "retailer": " EXAMPLE   ENERGY ", "current_bill_amount": "108.070",
        "daily_supply_rate": {"value": "1.1023", "unit": "AUD/day", "gst_basis": "inclusive"},
    })
    assert all(smoke.field_matches(actual, expected).values())
    actual.daily_supply_rate.gst_basis = "exclusive"
    actual.current_bill_amount = "999.99"
    matches = smoke.field_matches(actual, expected)
    assert matches["daily_supply_rate"] is False and matches["current_bill_amount"] is False
    assert not any(smoke.field_matches(None, expected).values())


@pytest.mark.parametrize("resolved", ["gpt-5.4-mini", "gpt-5.4-mini-2026-03-17"])
def test_cost_estimate_uses_decimal_and_all_output_tokens(resolved):
    assert smoke.estimate_cost("gpt-5.4-mini", resolved, 1000, 200) == Decimal("0.00165")


@pytest.mark.parametrize("resolved,input_tokens,output_tokens", [
    ("unpriced-model", 1000, 200), ("gpt-5.4-mini", None, 200),
    ("gpt-5.4-mini", 1000, None), ("gpt-5.4-mini", 272001, 200),
])
def test_unknown_cost_is_not_zero(resolved, input_tokens, output_tokens):
    assert smoke.estimate_cost("gpt-5.4-mini", resolved, input_tokens, output_tokens) is None
