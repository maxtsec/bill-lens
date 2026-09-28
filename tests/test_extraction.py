import json
from dataclasses import FrozenInstanceError
from shutil import copytree
from typing import get_args

import pytest
from pydantic import ValidationError

from bill_lens.contract import ExpectedLabel, ExtractionFields
from bill_lens.extraction import (
    BillExtractor, ExtractionAttempt, ExtractionErrorCode, FakeExtractor,
    ScriptedResponse, build_attempt,
)
from bill_lens.pdf_text import PdfText, extract_pdf_text
from bill_lens.validation import derive_flags, derive_status
from tests.helpers import CASES, ROOT


@pytest.fixture
def attempt_args(valid_fields):
    return dict(
        provider="fake", model="fake-v1", prompt_version="fixture-v1",
        raw_response=json.dumps(valid_fields),
        fields=ExtractionFields.model_validate(valid_fields), error_code=None,
        input_tokens=None, output_tokens=None, latency_ms=0,
    )


def test_shared_gate_preserves_response_and_metadata(valid_fields):
    raw = "\n" + json.dumps(valid_fields) + "\n"
    attempt = build_attempt(
        provider="test", model="model-v1", prompt_version="prompt-v2",
        raw_response=raw, input_tokens=12, output_tokens=0, latency_ms=7,
    )
    assert attempt.fields == ExtractionFields.model_validate(valid_fields)
    assert attempt.error_code is None
    assert attempt.raw_response == raw
    assert (attempt.provider, attempt.model, attempt.prompt_version) == ("test", "model-v1", "prompt-v2")
    assert (attempt.input_tokens, attempt.output_tokens, attempt.latency_ms) == (12, 0, 7)


@pytest.mark.parametrize("kind", [
    "non_json", "money_number", "missing_key", "extra_key", "date_number",
    "date_wrong_format", "wrapper", "null", "array", "empty",
])
def test_shared_gate_rejects_invalid_model_output_and_keeps_raw(valid_fields, kind):
    if kind == "money_number":
        valid_fields["current_bill_amount"] = 108.07
    elif kind == "missing_key":
        del valid_fields["retailer"]
    elif kind == "extra_key":
        valid_fields["amount_due"] = "108.07"
    elif kind == "date_number":
        valid_fields["period_start"] = 20260401
    elif kind == "date_wrong_format":
        valid_fields["period_start"] = "01/04/2026"
    raw = {
        "non_json": "sensitive non-JSON reply", "empty": "", "null": "null", "array": "[]",
        "wrapper": json.dumps({"fields": valid_fields}),
    }.get(kind, json.dumps(valid_fields))
    attempt = build_attempt(provider="test", model="m", prompt_version="v", raw_response=raw, latency_ms=0)
    assert attempt.error_code == "invalid_output"
    assert attempt.fields is None
    assert attempt.raw_response == raw


@pytest.mark.parametrize("kind", [
    "deep_nesting", "huge_integer", "bom", "markdown", "nan", "surrogate",
    "escaped_surrogate", "trailing_text", "duplicate_amount",
])
def test_review_json_edge_cases_are_invalid_output(valid_fields, kind):
    raw = json.dumps(valid_fields)
    if kind == "deep_nesting":
        raw = "[" * 100_000 + "0" + "]" * 100_000
    elif kind == "huge_integer":
        raw = raw.replace('"stated_billing_days": 30', '"stated_billing_days": ' + "9" * 5_000)
    elif kind == "bom":
        raw = "\ufeff" + raw
    elif kind == "markdown":
        raw = "```json\n" + raw + "\n```"
    elif kind == "nan":
        raw = raw.replace('"108.07"', "NaN")
    elif kind == "surrogate":
        raw = raw.replace("Example Energy", "\ud800")
    elif kind == "escaped_surrogate":
        raw = raw.replace("Example Energy", r"\ud800")
    elif kind == "trailing_text":
        raw += " extra response text"
    elif kind == "duplicate_amount":
        raw = raw[:-1] + ', "current_bill_amount": "999.99"}'
    attempt = build_attempt(
        provider="test", model="m", prompt_version="v", raw_response=raw, latency_ms=0,
    )
    assert attempt.error_code == "invalid_output"
    assert attempt.fields is None
    assert attempt.raw_response == raw


@pytest.mark.parametrize("digits", [4300, 4301])
def test_duplicate_keys_at_integer_parser_boundary(valid_fields, digits):
    raw = json.dumps(valid_fields).replace(
        '"stated_billing_days": 30', '"stated_billing_days": ' + "9" * digits,
    )
    # The 4300-digit control must be schema-valid: otherwise rejection could
    # conceal a duplicate-check regression. At 4301 both parsers reject it.
    if digits == 4300:
        assert json.loads(raw)["stated_billing_days"] > 0
        assert ExtractionFields.model_validate_json(raw).stated_billing_days > 0
    else:
        with pytest.raises(ValueError):
            json.loads(raw)
        with pytest.raises(ValidationError):
            ExtractionFields.model_validate_json(raw)
    raw = raw[:-1] + ', "current_bill_amount": "999.99"}'
    attempt = build_attempt(
        provider="test", model="m", prompt_version="v", raw_response=raw, latency_ms=0,
    )
    assert attempt.error_code == "invalid_output"
    assert attempt.fields is None
    assert attempt.raw_response == raw


@pytest.mark.parametrize("kind", ["nested_rate", "escaped_key", "same_value"])
def test_duplicate_keys_are_rejected_at_every_object_level(valid_fields, kind):
    raw = json.dumps(valid_fields)
    if kind == "nested_rate":
        raw = raw.replace('"value": "110.23"', '"value": "110.23", "value": "999"')
    elif kind == "escaped_key":
        raw = raw[:-1] + r', "current_bill_\u0061mount": "999.99"}'
    else:
        raw = raw[:-1] + ', "current_bill_amount": "108.07"}'
    attempt = build_attempt(
        provider="test", model="m", prompt_version="v", raw_response=raw, latency_ms=0,
    )
    assert attempt.error_code == "invalid_output"
    assert attempt.fields is None
    assert attempt.raw_response == raw


@pytest.mark.parametrize("error_code", [None, "timeout"])
def test_helper_requires_explicit_latency(valid_fields, error_code):
    with pytest.raises(TypeError, match="latency_ms"):
        build_attempt(
            provider="test", model="m", prompt_version="v",
            raw_response=json.dumps(valid_fields), error_code=error_code,
        )


@pytest.mark.parametrize("code,has_response", [
    (code, has_response)
    for code in get_args(ExtractionErrorCode)
    for has_response in (False, True)
    if code != "invalid_output" or has_response
])
def test_scripted_failures_preserve_raw_and_metadata(code, has_response, valid_fields):
    # A refused/truncated response must remain a failure even if valid JSON arrived.
    raw = json.dumps(valid_fields) if has_response else None
    if code == "invalid_output":
        raw = "supplied malformed response"
    document = PdfText(file_sha256="a" * 64, pages=())
    extractor = FakeExtractor({document.file_sha256: ScriptedResponse(
        raw_response=raw, error_code=code, input_tokens=12, output_tokens=3, latency_ms=9,
    )})
    attempt = extractor.extract(document)
    assert attempt.fields is None
    assert attempt.error_code == code
    assert attempt.raw_response == raw
    assert (attempt.input_tokens, attempt.output_tokens, attempt.latency_ms) == (12, 3, 9)


@pytest.mark.parametrize("case", CASES)
def test_golden_pdf_to_fake_to_domain_checks(case):
    extractor: BillExtractor = FakeExtractor.from_dataset(ROOT / "dataset")
    path = ROOT / "dataset" / case
    label = ExpectedLabel.model_validate_json((path / "expected.json").read_text())
    document = extract_pdf_text((path / "bill.pdf").read_bytes())
    attempt = extractor.extract(document)
    assert attempt == extractor.extract(document)
    assert attempt.error_code is None
    assert attempt.fields == label.fields
    assert json.loads(attempt.raw_response) == label.fields.model_dump(mode="json")
    assert derive_flags(attempt.fields) == set(label.expected_flags)
    assert derive_status(derive_flags(attempt.fields)) == label.expected_status
    assert (attempt.provider, attempt.model, attempt.prompt_version) == ("fake", "fake-v1", "fixture-v1")
    assert (attempt.input_tokens, attempt.output_tokens, attempt.latency_ms) == (None, None, 0)


def test_bill_002_missing_current_total_is_a_successful_attempt_requiring_review():
    document = extract_pdf_text((ROOT / "dataset/bill_002/bill.pdf").read_bytes())
    attempt = FakeExtractor.from_dataset(ROOT / "dataset").extract(document)
    assert attempt.error_code is None
    assert attempt.fields.current_bill_amount is None
    assert derive_flags(attempt.fields) == {"current_bill_amount_missing"}


def test_fake_uses_validation_gate_and_does_not_cache_mutable_fields(valid_fields):
    document = PdfText(file_sha256="a" * 64, pages=())
    responses = {document.file_sha256: ScriptedResponse(json.dumps(valid_fields))}
    fake = FakeExtractor(responses)
    responses.clear()
    first = fake.extract(document)
    first.fields.daily_supply_rate.value = "999"
    assert fake.extract(document).fields.daily_supply_rate.value == "110.23"
    bad = FakeExtractor({document.file_sha256: ScriptedResponse('{"retailer": 42}')})
    attempt = bad.extract(document)
    assert attempt.error_code == "invalid_output"
    assert attempt.fields is None
    assert attempt.raw_response == '{"retailer": 42}'


@pytest.mark.parametrize("overrides", [
    {"fields": None},
    {"error_code": "timeout"},
    {"raw_response": None},
    {"fields": None, "error_code": "invalid_output", "raw_response": None},
    {"fields": None, "error_code": "typo"},
])
def test_attempt_rejects_inconsistent_states(attempt_args, overrides):
    with pytest.raises(ValueError):
        ExtractionAttempt(**(attempt_args | overrides))


@pytest.mark.parametrize("name", ["provider", "model", "prompt_version"])
@pytest.mark.parametrize("value", ["", " \t\n", None, 123])
def test_attempt_rejects_invalid_identity(attempt_args, name, value):
    with pytest.raises((TypeError, ValueError)):
        ExtractionAttempt(**(attempt_args | {name: value}))


@pytest.mark.parametrize("name", ["input_tokens", "output_tokens", "latency_ms"])
@pytest.mark.parametrize("value", [-1, True, 1.5, "1"])
def test_attempt_rejects_invalid_counts(attempt_args, name, value):
    with pytest.raises((TypeError, ValueError)):
        ExtractionAttempt(**(attempt_args | {name: value}))


@pytest.mark.parametrize("name", ["input_tokens", "output_tokens", "latency_ms"])
@pytest.mark.parametrize("value", [2**63 - 1, 2**63])
@pytest.mark.parametrize("failed", [False, True])
def test_attempt_metadata_bigint_boundary(attempt_args, name, value, failed):
    args = attempt_args | {name: value}
    if failed:
        args.update(fields=None, error_code="timeout")
    helper_args = {key: item for key, item in args.items() if key != "fields"}
    if value == 2**63:
        # Both direct construction and the adapter helper reject without a DB.
        with pytest.raises(ValueError, match=f"{name} must be at most"):
            ExtractionAttempt(**args)
        with pytest.raises(ValueError, match=f"{name} must be at most"):
            build_attempt(**helper_args)
    else:
        assert getattr(ExtractionAttempt(**args), name) == value
        assert getattr(build_attempt(**helper_args), name) == value


@pytest.mark.parametrize("overrides", [{"latency_ms": None}, {"raw_response": b"{}"}, {"fields": {}}])
def test_attempt_rejects_wrong_types(attempt_args, overrides):
    with pytest.raises(TypeError):
        ExtractionAttempt(**(attempt_args | overrides))


def test_attempt_is_frozen(attempt_args):
    attempt = ExtractionAttempt(**attempt_args)
    with pytest.raises(FrozenInstanceError):
        attempt.error_code = "timeout"


@pytest.mark.parametrize("raw,error_code", [(None, None), (None, "invalid_output"), (b"{}", None)])
def test_helper_rejects_invalid_arguments(raw, error_code):
    with pytest.raises((TypeError, ValueError)):
        build_attempt(provider="test", model="m", prompt_version="v", raw_response=raw, error_code=error_code, latency_ms=0)


def test_helper_does_not_hide_programming_errors(monkeypatch):
    def bug(*args, **kwargs):
        raise RuntimeError("implementation defect")

    monkeypatch.setattr(ExtractionFields, "model_validate_json", bug)
    with pytest.raises(RuntimeError, match="implementation defect"):
        build_attempt(provider="test", model="m", prompt_version="v", raw_response="{}", latency_ms=0)


def test_unknown_hash_and_wrong_input_are_setup_errors():
    fake = FakeExtractor({})
    with pytest.raises(KeyError, match="no scripted outcome"):
        fake.extract(PdfText(file_sha256="b" * 64, pages=()))
    with pytest.raises(TypeError, match="document must be PdfText"):
        fake.extract("bill.pdf")


@pytest.mark.parametrize("response", [
    ScriptedResponse(None),
    ScriptedResponse(None, error_code="invalid_output"),
    ScriptedResponse(None, error_code="timeout", latency_ms=-1),
])
def test_invalid_script_configuration_raises(response):
    document = PdfText(file_sha256="a" * 64, pages=())
    with pytest.raises(ValueError):
        FakeExtractor({document.file_sha256: response}).extract(document)


def test_dataset_loader_rejects_missing_or_invalid_labels_and_duplicate_hashes(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        FakeExtractor.from_dataset(tmp_path)
    case = tmp_path / "bill_001"
    copytree(ROOT / "dataset/bill_001", case)
    label = case / "expected.json"
    original = label.read_bytes()
    label.unlink()
    with pytest.raises(FileNotFoundError):
        FakeExtractor.from_dataset(tmp_path)
    label.write_text("{}")
    with pytest.raises(ValidationError):
        FakeExtractor.from_dataset(tmp_path)
    label.write_bytes(original)
    copytree(case, tmp_path / "bill_002")
    with pytest.raises(ValueError, match="duplicate PDF hashes"):
        FakeExtractor.from_dataset(tmp_path)
