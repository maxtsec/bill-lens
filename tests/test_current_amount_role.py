import pytest

from bill_lens.contract import ExtractionFields
from bill_lens import current_amount_role as role
from bill_lens.document_validation import derive_document_flags, printed_number_occurrences
from bill_lens.pdf_text import PageText, PdfText
from bill_lens.validation import derive_review_flags
from evals.dataset import load_cases
from tests.helpers import ROOT


FLAG = "current_bill_amount_role_unconfirmed"
CASES = [*load_cases(ROOT / "dataset"), *load_cases(ROOT / "dataset/holdout")]


def fields(amount):
    return ExtractionFields.model_validate(dict.fromkeys(ExtractionFields.model_fields)
                                           | {"current_bill_amount": amount})


def document(text):
    return PdfText("a" * 64, (PageText(1, text),))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_all_eleven_correct_labels_have_no_role_flags(case):
    assert role.derive_current_amount_role_flags(case.label.fields, case.document) == set()
    assert derive_review_flags(case.label.fields, case.document) == set(case.label.expected_flags)


@pytest.mark.parametrize("name,amount,expected", [
    ("bill_001", "108.07", set()), ("bill_002", "162.66", {FLAG}),
    ("bill_002", "132.66", {FLAG}), ("bill_003", "113.40", set()),
    ("bill_003", "163.40", {FLAG}), ("bill_004", "-4.00", set()),
    ("bill_004", "4.00", {FLAG}), ("bill_005", "29.45", set()),
])
def test_required_bill_cases_preserve_values(name, amount, expected):
    case = next(c for c in CASES if c.name == name)
    actual = ExtractionFields.model_validate(case.label.fields.model_dump(mode="json")
                                             | {"current_bill_amount": amount})
    before = actual.model_dump_json()
    assert role.derive_current_amount_role_flags(actual, case.document) == expected
    assert actual.model_dump_json() == before


@pytest.mark.parametrize("label", role.CURRENT_LABELS)
def test_general_current_charge_vocabulary(label):
    assert role.derive_current_amount_role_flags(fields("90.15"), document(f"{label}: $90.15")) == set()


@pytest.mark.parametrize("label", role.DISTRACTOR_LABELS)
def test_distractor_vocabulary_never_confirms(label):
    assert role.derive_current_amount_role_flags(fields("90.15"), document(f"{label}: $90.15")) == {FLAG}


@pytest.mark.parametrize("text,amount,expected", [
    ("Total new charges $90.15", "90.15", set()),
    ("This bill: $90.15", "90.15", set()),
    ("Balance carried forward $40.00", "40.00", {FLAG}),
    ("Amount due $90.15.", "90.15", {FLAG}),
    ("$90.15", "90.15", {FLAG}),
    ("$90.15 Current charges", "90.15", {FLAG}),  # No forward label search.
    ("AMOUNT DUE: $90.15\nCurrent charges: $90.15", "90.15", set()),
    ("Current charges: $90.15\nAMOUNT DUE: $90.15", "90.15", set()),
    ("AMOUNT DUE: $100.00\nCurrent charges: $90.15", "100", {FLAG}),
    ("Current charges: $90.15 Amount due: $100.00", "100", {FLAG}),
    ("Amount due: $100.00 Current charges: $90.15", "90.15", set()),
    ("Current charges Amount due $90.15", "90.15", {FLAG}),
    ("Amount due Current charges $90.15", "90.15", {FLAG}),
    ("TOTAL\t  NeW  CHARGES: $90.15", "90.15", set()),
    ("notthis billable: $90.15", "90.15", {FLAG}),
    ("Current charges\n\n  \nAUD 90.15", "90.15", set()),
    ("Current charges\nMystery subtotal: AUD 90.15", "90.15", {FLAG}),
    ("Current charges\nAmount due: AUD 90.15", "90.15", {FLAG}),
    ("Current charges\nAn intervening notice\nAUD 90.15", "90.15", {FLAG}),
    ("Current bill amount\nAUD 4.00 CR", "-4.00", set()),
    ("Current charges: AUD 4.00 CR", "4.00", {FLAG}),
    ("Current charges: -$4.00.", "-4.00", set()),
    ("Current charges - AUD 4.00", "4.00", set()),
    ("Current charges - AUD 4.00", "-4.00", {FLAG}),
    ("Total new charges: $1,234.50, due tomorrow", "1234.5", set()),
    ("Current charges: $1,23.45", "23.45", {FLAG}),
    ("Current bill amount Supply charge: AUD 29.45\nAUD 29.45", "29.45", set()),
])
def test_windows_ordering_normalisation_and_shared_sign_rules(text, amount, expected):
    actual, source = fields(amount), document(text)
    assert role.derive_current_amount_role_flags(actual, source) == expected
    if not expected:
        assert derive_document_flags(actual, source) == set()


def test_null_does_not_get_role_flag():
    assert role.derive_current_amount_role_flags(fields(None), document("Amount due $90.15")) == set()


def test_previous_line_is_page_local_but_any_current_occurrence_can_confirm():
    source = PdfText("a" * 64, (PageText(1, "Current charges"), PageText(2, "AUD 90.15")))
    assert role.derive_current_amount_role_flags(fields("90.15"), source) == {FLAG}
    source = PdfText("a" * 64, (PageText(1, "Amount due $90.15"), PageText(2, "This bill $90.15")))
    assert role.derive_current_amount_role_flags(fields("90.15"), source) == set()


def test_equal_end_tie_prefers_distractor_even_over_longer_current_label(monkeypatch):
    # Vocabularies currently have no cross-class overlap. A distractor vetoes
    # confirmation even when the current label is longer or just as near.
    monkeypatch.setattr(role, "_DISTRACTORS", role._patterns(("charges",)))
    assert role.derive_current_amount_role_flags(fields("90.15"), document("Total current charges $90.15")) == {FLAG}


@pytest.mark.parametrize("text,amount,expected", [
    ("Amount due for this bill $162.66", "162.66", {FLAG}),
    ("Total amount due on this bill: $162.66", "162.66", {FLAG}),
    ("Balance on this bill: $162.66", "162.66", {FLAG}),
    ("This bill: $113.40\nAmount due for this bill: $163.40", "113.40", set()),
    ("This bill: $113.40\nAmount due for this bill: $163.40", "163.40", {FLAG}),
    ("Current charges $113.40\n$163.40\nTotal amount due", "163.40", {FLAG}),
    ("Total amount due $163.40\n$113.40\nCurrent charges", "113.40", {FLAG}),
    ("Current charges $113.40 $163.40 Total amount due", "163.40", {FLAG}),
    ("Current charges $113.40 AUD $163.40", "163.40", {FLAG}),
    ("Amount due $163.40 Current charges\n$113.40", "113.40", {FLAG}),
    ("Total amount due $163.40 Current charges $113.40", "113.40", set()),
])
def test_distractor_veto_and_first_number_ownership(text, amount, expected):
    assert role.derive_current_amount_role_flags(fields(amount), document(text)) == expected


def test_occurrences_keep_sign_offsets_and_previous_nonempty_line():
    tokens = list(printed_number_occurrences(document("Current bill amount\n\nAUD 4.00 CR")))
    assert len(tokens) == 1
    token = tokens[0]
    assert str(token.value) == "-4.00"
    assert token.line[token.start:token.end] == "4.00"
    assert token.previous_line == "Current bill amount"
    assert token.previous_number_end == 0
    assert token.previous_line_has_number is False
    tokens = list(printed_number_occurrences(document("Current charges $113.40\n$163.40")))
    assert tokens[1].previous_line_has_number is True
    tokens = list(printed_number_occurrences(document("Current charges $113.40 AUD $163.40")))
    assert tokens[1].line[tokens[1].previous_number_end:tokens[1].start] == " AUD $"


def test_documented_column_limitation_does_not_claim_layout_reconstruction():
    # The recognised current label precedes both column values; supply charge
    # is not in the distractor vocabulary. This can also confirm the wrong column.
    source = document("Current bill amount Supply charge: AUD 40.00\nAUD 29.45")
    assert role.derive_current_amount_role_flags(fields("40"), source) == set()
