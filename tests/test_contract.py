import pytest
from pydantic import ValidationError

from bill_lens.contract import ExpectedLabel, ExtractionFields


@pytest.mark.parametrize("field,value", [
    ("retailer", "  "),
    ("retailer", 123),
    ("period_start", "05/06/2026"),
    ("period_start", "2026-02-30"),
    ("period_start", "2026-4-1"),
    ("period_start", "2026-04-01T00:00:00"),
    ("stated_billing_days", True),
    ("stated_billing_days", "30"),
    ("stated_billing_days", 0),
    ("stated_billing_days", -1),
    ("total_usage_kwh", "-1"),
    ("total_usage_kwh", 250.0),
    ("current_bill_amount", 108.07),
    ("current_bill_amount", "NaN"),
    ("current_bill_amount", "Infinity"),
    ("current_bill_amount", "1e2"),
    ("current_bill_amount", "AUD 100"),
    ("current_bill_amount", "4.00 CR"),
    ("current_bill_amount", " 108.07 "),
])
def test_reject_malformed_values(valid_fields, field, value):
    valid_fields[field] = value
    with pytest.raises(ValidationError):
        ExtractionFields.model_validate(valid_fields)


@pytest.mark.parametrize("field,value", [
    ("value", "-1"), ("value", 1.0), ("value", "NaN"),
    ("unit", "c/day"), ("gst_basis", "incl"),
])
def test_supply_rate_requires_contract_values(valid_fields, field, value):
    valid_fields["daily_supply_rate"][field] = value
    with pytest.raises(ValidationError):
        ExtractionFields.model_validate(valid_fields)


@pytest.mark.parametrize("field", [
    "retailer", "period_start", "period_end", "stated_billing_days",
    "total_usage_kwh", "daily_supply_rate", "current_bill_amount",
])
def test_nullable_keys_cannot_be_omitted(valid_fields, field):
    del valid_fields[field]
    with pytest.raises(ValidationError):
        ExtractionFields.model_validate(valid_fields)


@pytest.mark.parametrize("nested", [False, True])
def test_extra_keys_rejected(valid_fields, nested):
    target = valid_fields["daily_supply_rate"] if nested else valid_fields
    target["amount_due"] = "108.07"
    with pytest.raises(ValidationError):
        ExtractionFields.model_validate(valid_fields)


def test_zero_usage_credit_and_precision_survive_roundtrip(valid_fields):
    valid_fields.update(total_usage_kwh="0", current_bill_amount="-4.00")
    fields = ExtractionFields.model_validate(valid_fields)
    assert fields.model_dump(mode="json") == valid_fields
    assert ExtractionFields.model_validate_json(fields.model_dump_json()) == fields


@pytest.mark.parametrize("flags", [
    ["retailer_missing", "retailer_missing"],
    ["retailer_missing", "current_bill_amount_missing"],
    ["daily_supply_rate_unusable"],
])
def test_label_flags_are_known_sorted_and_unique(valid_fields, flags):
    with pytest.raises(ValidationError):
        ExpectedLabel.model_validate({
            "schema_version": 1, "fields": valid_fields,
            "expected_status": "needs_review", "expected_flags": flags,
        })


@pytest.mark.parametrize("version", [True, "1", 2])
def test_label_version_is_exact(valid_fields, version):
    with pytest.raises(ValidationError):
        ExpectedLabel.model_validate({
            "schema_version": version, "fields": valid_fields,
            "expected_status": "processed", "expected_flags": [],
        })


def test_generated_schema_keeps_described_fields_required_and_nullable():
    schema = ExtractionFields.model_json_schema()
    expected = {
        "retailer", "period_start", "period_end", "stated_billing_days",
        "total_usage_kwh", "daily_supply_rate", "current_bill_amount",
    }
    assert set(schema["properties"]) == set(schema["required"]) == expected
    assert schema["additionalProperties"] is False
    for field in schema["properties"].values():
        assert field["description"].strip()
        assert {"type": "null"} in field["anyOf"]
        assert "default" not in field
    rate = schema["$defs"]["SupplyRate"]
    assert set(rate["required"]) == {"value", "unit", "gst_basis"}
    assert rate["additionalProperties"] is False
    assert all(field["description"].strip() for field in rate["properties"].values())
