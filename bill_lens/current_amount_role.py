"""A conservative label heuristic, not proof of accounting semantics (ADR-010)."""

from decimal import Decimal
import re

from bill_lens.contract import ExtractionFields, ReviewFlag
from bill_lens.document_validation import printed_number_occurrences
from bill_lens.pdf_text import PdfText


# General Australian bill terminology, not retailer/layout-specific templates.
# Sources and the deliberately limited synonym choices are recorded in ADR-010.
CURRENT_LABELS = (
    "current bill amount", "current charges", "this bill", "total new charges",
    "new charges", "total current charges", "amount of this bill",
)
DISTRACTOR_LABELS = (
    "amount due", "total due", "balance", "previous balance", "payment",
    "payments", "overdue", "carried forward", "account balance",
)


def _patterns(labels):
    return tuple(re.compile(r"(?<!\w)" + re.escape(label) + r"(?!\w)") for label in labels)


_CURRENT = _patterns(CURRENT_LABELS)
_DISTRACTORS = _patterns(DISTRACTOR_LABELS)
_DECORATION_WORDS = re.compile(r"\b(?:aud|cr|credit)\b")


def _normalise(text):
    return " ".join(text.casefold().split())


def _current_label_wins(window: str) -> bool:
    matches = [(match.end(), distractor, match.end() - match.start())
               for distractor, patterns in ((False, _CURRENT), (True, _DISTRACTORS))
               for pattern in patterns for match in pattern.finditer(window)]
    # Distance is from the label's end to the number/window end. On equal ends,
    # a distractor wins; within one class the longest phrase is the tie-breaker.
    return bool(matches) and not max(matches)[1]


def derive_current_amount_role_flags(fields: ExtractionFields, document: PdfText) -> set[ReviewFlag]:
    """Confirm any signed occurrence; nulls add nothing and values are untouched."""
    if fields.current_bill_amount is None:
        return set()
    amount = Decimal(fields.current_bill_amount)
    for occurrence in printed_number_occurrences(document):
        if occurrence.value != amount:
            continue
        before = _normalise(occurrence.line[:occurrence.start])
        # Any alphabetic text except currency/credit decorations is label-like,
        # even if unrecognised. Unknown same-line labels must not borrow a heading.
        label_like = any(c.isalpha() for c in _DECORATION_WORDS.sub("", before))
        window = before if label_like else _normalise(occurrence.previous_line)
        if _current_label_wins(window):
            # Presence of a recognised label is still not a column/role proof.
            return set()
    return {"current_bill_amount_role_unconfirmed"}
