"""Printed-value presence checks on the exact PdfText supplied to extraction.

A match proves presence somewhere, never the number's role or its unit/GST basis.
These conservative review flags do not repair fields or establish correctness.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
import re

from bill_lens.contract import ExtractionFields, ReviewFlag
from bill_lens.pdf_text import PdfText

PRESENCE_FLAG_FIELDS: dict[ReviewFlag, str] = {
    "current_bill_amount_not_printed": "current_bill_amount",
    "total_usage_kwh_not_printed": "total_usage_kwh",
    "daily_supply_rate_not_printed": "daily_supply_rate",
    "stated_billing_days_not_printed": "stated_billing_days",
    "retailer_not_printed": "retailer",
}
DOCUMENT_FLAG_FIELDS: dict[ReviewFlag, str] = PRESENCE_FLAG_FIELDS | {
    "current_bill_amount_role_unconfirmed": "current_bill_amount",
}

# Whole decimal tokens only: no substring matches inside larger numbers or
# malformed comma groups. Commas must group exactly three digits. Decorations
# such as AUD, $, cents symbols and kWh are outside the numeric token.
# A trailing dot/comma is punctuation unless followed by another digit.
_NUMBER = re.compile(r"(?<![0-9.,])(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?(?![0-9]|[.,][0-9])")
_CURRENCY = r"(?:(?:AUD|\$)[ \t]*)?"
# The minus must touch the number or currency; a spaced dash is a separator.
_MINUS = re.compile(r"[-−]" + _CURRENCY + r"$", re.IGNORECASE)
_OPEN_PAREN = re.compile(r"\([ \t]*" + _CURRENCY + r"$", re.IGNORECASE)
_CLOSE_PAREN = re.compile(r"^[ \t]*\)")
_CREDIT_BEFORE = re.compile(r"\b(?:CR|credit)[ \t]*[:=]?[ \t]*" + _CURRENCY + r"$", re.IGNORECASE)
_CREDIT_AFTER = re.compile(r"^[ \t]*(?:CR|credit)\b", re.IGNORECASE)


@dataclass(frozen=True)
class PrintedNumber:
    value: Decimal
    line: str
    start: int
    end: int
    previous_line: str
    previous_number_end: int
    previous_line_has_number: bool


def printed_number_occurrences(document: PdfText) -> Iterator[PrintedNumber]:
    """One tokenizer/sign policy for both presence and label-role checks."""
    for page in document.pages:
        previous_line = ""  # Never inherit a label across a page boundary.
        previous_line_has_number = False
        # Sign/credit markers must be adjacent on the same line. A distant
        # 'credit' heading must not flip every number on the page.
        for line in page.text.splitlines():
            tokens = list(_NUMBER.finditer(line))
            for index, token in enumerate(tokens):
                # Inspect neighbouring gaps, not growing line prefixes/suffixes:
                # a long numeric line should not need quadratic string copies.
                start = tokens[index - 1].end() if index else 0
                end = tokens[index + 1].start() if index + 1 < len(tokens) else len(line)
                before, after = line[start:token.start()], line[token.end():end]
                credit = (_MINUS.search(before) or _CREDIT_BEFORE.search(before)
                          or _CREDIT_AFTER.match(after)
                          or (_OPEN_PAREN.search(before) and _CLOSE_PAREN.match(after)))
                value = Decimal(token.group().replace(",", ""))
                # copy_negate is exact even beyond the current Decimal precision.
                yield PrintedNumber(value.copy_negate() if credit else value,
                                    line, token.start(), token.end(), previous_line,
                                    tokens[index - 1].end() if index else 0,
                                    previous_line_has_number)
            if line.strip():
                previous_line = line
                previous_line_has_number = bool(tokens)


def _printed_numbers(document: PdfText) -> set[Decimal]:
    return {occurrence.value for occurrence in printed_number_occurrences(document)}


def _normalise(text: str) -> str:
    return " ".join(text.casefold().split())


def derive_document_flags(fields: ExtractionFields, document: PdfText) -> set[ReviewFlag]:
    """Flag non-null values absent from the document; dates are intentionally out of scope."""
    numbers = _printed_numbers(document)
    flags: set[ReviewFlag] = set()
    for flag, name in PRESENCE_FLAG_FIELDS.items():
        value = getattr(fields, name)
        if value is None:
            continue  # Missing-value rules belong to field-derived checks.
        if name == "retailer":
            found = _normalise(value) in _normalise(document.text)
        else:
            # Compare the printed rate value, not its normalised AUD/day amount.
            value = value.value if name == "daily_supply_rate" else value
            found = Decimal(value) in numbers
        if not found:
            flags.add(flag)
    return flags
