"""Deterministic scoring against independently authored expected.json labels."""

from decimal import Decimal

from bill_lens.contract import ExpectedLabel, ExtractionFields
from bill_lens.extraction import ExtractionAttempt
from bill_lens.pdf_text import PdfText
from bill_lens.validation import derive_review_flags, derive_status, supply_rate_aud

FIELDS = tuple(ExtractionFields.model_fields)
OUTCOMES = ("correct", "wrong_value", "missing", "false_extraction", "no_fields")


def score_fields(actual: ExtractionFields | None, expected: ExtractionFields) -> dict:
    # docs/extraction-contract.md: Retailer, Billing period, Total usage,
    # Daily supply rate, Current bill amount, and final evaluation paragraph.
    outcomes = {}
    components = {"rate_value": None, "gst_basis": None}
    for name in FIELDS:
        if actual is None:
            outcomes[name] = "no_fields"
            continue
        left, right = getattr(actual, name), getattr(expected, name)
        if left is None or right is None:
            outcomes[name] = ("correct" if left is right else
                              "missing" if left is None else "false_extraction")
            continue
        if name == "retailer":
            equal = " ".join(left.casefold().split()) == " ".join(right.casefold().split())
        elif name in {"total_usage_kwh", "current_bill_amount"}:
            equal = Decimal(left) == Decimal(right)
        elif name == "daily_supply_rate":
            components = {"rate_value": supply_rate_aud(left) == supply_rate_aud(right),
                          "gst_basis": left.gst_basis == right.gst_basis}
            equal = all(components.values())
        else:
            equal = left == right  # Validated ISO dates and positive integer days.
        outcomes[name] = "correct" if equal else "wrong_value"
    return {"field_outcomes": outcomes, "supply_components": components}


def field_matches(actual: ExtractionFields | None, expected: ExtractionFields) -> dict[str, bool]:
    """Compatibility view for the original live smoke check; no second scorer."""
    return {key: value == "correct" for key, value in score_fields(actual, expected)["field_outcomes"].items()}


def score_attempt(attempt: ExtractionAttempt, expected: ExpectedLabel, document: PdfText) -> dict:
    scored = score_fields(attempt.fields, expected.fields)
    # Contract: JSON shape and review rules. Expected flags remain the manual
    # oracle; production functions compute predictions only, never the answer.
    flags = sorted(derive_review_flags(attempt.fields, document)) if attempt.fields is not None else None
    status = derive_status(flags) if flags is not None else "failed"
    return scored | {
        "predicted": attempt.fields.model_dump(mode="json") if attempt.fields else None,
        "expected": expected.fields.model_dump(mode="json"),
        "flags": flags, "expected_flags": expected.expected_flags,
        "status": status, "expected_status": expected.expected_status,
        "flags_match": flags is not None and set(flags) == set(expected.expected_flags),
        "status_match": status == expected.expected_status,
        "exact_bill_match": all(value == "correct" for value in scored["field_outcomes"].values()),
    }
