import pytest

from bill_lens.contract import ExtractionFields
from bill_lens.document_validation import derive_document_flags
from bill_lens.pdf_text import PageText, PdfText
from bill_lens.validation import derive_flags, derive_review_flags, derive_status
from evals.dataset import load_cases
from tests.helpers import ROOT


CASES = [*load_cases(ROOT / "dataset"), *load_cases(ROOT / "dataset/holdout")]


def document(text):
    return PdfText("a" * 64, (PageText(1, text),))


def fields(**updates):
    return ExtractionFields.model_validate(dict.fromkeys(ExtractionFields.model_fields) | updates)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_all_eleven_manual_labels_have_no_document_flags(case):
    assert derive_document_flags(case.label.fields, case.document) == set()
    assert derive_review_flags(case.label.fields, case.document) == set(case.label.expected_flags)


@pytest.mark.parametrize("line", [
    "Current bill amount: AUD 90.15",
    "Your current bill amount is AUD 90.15.",
    "Current bill amount $90.15, due 14 May",
    "Current bill amount - AUD 90.15",
    "Current bill amount – AUD 90.15",
    "Current bill amount:$90.15",
], ids=["plain", "full-stop", "comma", "hyphen-separator", "en-dash", "colon"])
def test_review_probe_lines_keep_the_printed_amount_positive(line):
    extracted = fields(
        retailer="Example Energy", period_start="2026-04-01", period_end="2026-04-30",
        stated_billing_days=30, total_usage_kwh="250", current_bill_amount="90.15",
        daily_supply_rate={"value": "110.23", "unit": "cents/day", "gst_basis": "inclusive"},
    )
    source = document("Example Energy\nBilling days: 30\nTotal imported usage: 250 kWh\n"
                      "Supply: 110.23 c/day\n" + line)
    assert derive_document_flags(extracted, source) == set()
    # A separator must not also manufacture support for the negative amount.
    assert derive_document_flags(fields(current_bill_amount="-90.15"), source) == {"current_bill_amount_not_printed"}


@pytest.mark.parametrize("text,value", [
    ("AUD 108.070", "108.07"), ("$108.07", "108.070"),
    ("AUD1,234.50", "1234.5"), ("1,234,567.89", "1234567.89"),
    ("110.23c/day", "110.23"), ("95¢/day", "95"),
    ("110.23 c", "110.23"), ("110.23/day", "110.23"), ("250kWh", "250"),
    ("0", "0.00"), ("4.00 CR", "-4"), ("4.00 credit", "-4.000"),
    ("credit: AUD 4.00", "-4"), ("CR $4.00", "-4"),
    ("-4.00", "-4"), ("−4.00", "-4"), ("-$4.00", "-4"),
    ("−AUD 4.00", "-4"), ("-$ 4.00", "-4"),
    ("1,234.50.", "1234.5"), ("1,234.50, due tomorrow", "1234.5"),
    ("30.", "30"), ("30, due tomorrow", "30"),
    ("(4.00)", "-4"), ("(AUD 4.00)", "-4"), ("AUD (4.00)", "-4"),
    ("4.00 CR\n4.00", "4"),
    ("123456789012345678901234567890.01 CR", "-123456789012345678901234567890.01"),
])
def test_numeric_formats_and_exact_signs_match(text, value):
    assert derive_document_flags(fields(current_bill_amount=value), document(text)) == set()


@pytest.mark.parametrize("text", [" - 4.00", " − 4.00", " - AUD 4.00", " − $4.00", "-\t4.00"])
def test_spaced_minus_is_a_separator_not_a_negative_sign(text):
    assert derive_document_flags(fields(current_bill_amount="4"), document(text)) == set()
    assert derive_document_flags(fields(current_bill_amount="-4"), document(text)) == {"current_bill_amount_not_printed"}


@pytest.mark.parametrize("text", ["1.2.3", "1,23.45", "1,234,56", "1.234,50"])
def test_malformed_numeric_tokens_cannot_supply_any_fragments(text):
    from bill_lens.document_validation import _printed_numbers
    assert _printed_numbers(document(text)) == set()


@pytest.mark.parametrize("text,value", [
    ("132.66", "32.66"), ("132.66", "132"), ("132.66", "66"),
    ("1,23.45", "23.45"), ("4.00", "-4"),
    ("4.00 CR", "4"), ("credit: 4.00", "4"), ("(4.00)", "4"),
    ("-4.00", "4"), ("−4.00", "4"),
    ("credit heading\n4.00", "-4"), ("4.00\nCR", "-4"),
    ("Credit adjustment elsewhere: 4.00", "-4"),
])
def test_substrings_malformed_grouping_and_wrong_sign_do_not_match(text, value):
    assert derive_document_flags(fields(current_bill_amount=value), document(text)) == {"current_bill_amount_not_printed"}


@pytest.mark.parametrize("name,value,flag", [
    ("current_bill_amount", "9876.54", "current_bill_amount_not_printed"),
    ("total_usage_kwh", "9876.54", "total_usage_kwh_not_printed"),
    ("stated_billing_days", 9876, "stated_billing_days_not_printed"),
    ("daily_supply_rate", {"value": "9876.54", "unit": "cents/day", "gst_basis": "inclusive"}, "daily_supply_rate_not_printed"),
    ("retailer", "QVX Expanded From Memory", "retailer_not_printed"),
])
def test_each_non_null_field_has_its_own_flag(name, value, flag):
    assert derive_document_flags(fields(**{name: value}), document("QVX 1.00")) == {flag}


def test_null_fields_and_dates_do_not_produce_document_flags():
    assert derive_document_flags(fields(period_start="2099-01-01", period_end="2099-02-01"), document("no numbers")) == set()


def test_retailer_case_whitespace_and_line_break_normalisation():
    assert derive_document_flags(fields(retailer="  EXAMPLE   Energy "), document("Header\nExample\n\t energy\nBill")) == set()


@pytest.mark.parametrize("case_name,updates,expected", [
    ("bill_002", {"current_bill_amount": "132.66"}, {"current_bill_amount_not_printed"}),
    ("bill_002", {"current_bill_amount": "162.66"}, set()),
    ("bill_004", {"current_bill_amount": "-4.00"}, set()),
    ("bill_004", {"current_bill_amount": "4.00"}, {"current_bill_amount_not_printed"}),
    ("bill_001", {"daily_supply_rate": {"value": "110.23", "unit": "cents/day", "gst_basis": "inclusive"}}, set()),
    ("bill_005", {"daily_supply_rate": {"value": "95", "unit": "cents/day", "gst_basis": "inclusive"}}, set()),
])
def test_hand_authored_bill_cases(case_name, updates, expected):
    case = next(c for c in CASES if c.name == case_name)
    changed = ExtractionFields.model_validate(case.label.fields.model_dump(mode="json") | updates)
    before = changed.model_dump_json()
    assert derive_document_flags(changed, case.document) == expected
    assert changed.model_dump_json() == before  # Flags never repair or null fields.


def test_combined_decision_routes_unprinted_amount_to_review():
    case = next(c for c in CASES if c.name == "bill_002")
    changed = ExtractionFields.model_validate(case.label.fields.model_dump(mode="json") | {"current_bill_amount": "132.66"})
    assert derive_status(derive_flags(changed)) == "processed"
    assert derive_review_flags(changed, case.document) == {"current_bill_amount_not_printed"}
    assert derive_status(derive_review_flags(changed, case.document)) == "needs_review"


def test_document_checks_keep_the_original_rate_unit_without_conversion():
    rate = {"value": "110.23", "unit": "cents/day", "gst_basis": "inclusive"}
    assert derive_document_flags(fields(daily_supply_rate=rate), document("AUD 1.1023/day")) == {"daily_supply_rate_not_printed"}


def test_page_provenance_does_not_attach_a_credit_marker_from_another_page():
    source = PdfText("a" * 64, (PageText(1, "4.00"), PageText(2, "CR")))
    assert derive_document_flags(fields(current_bill_amount="-4"), source) == {"current_bill_amount_not_printed"}


def test_expected_label_accepts_new_document_codes(valid_fields):
    from bill_lens.contract import ExpectedLabel
    label = ExpectedLabel.model_validate({"schema_version": 1, "fields": valid_fields,
                                         "expected_status": "needs_review",
                                         "expected_flags": ["current_bill_amount_not_printed"]})
    assert label.expected_flags == ["current_bill_amount_not_printed"]
