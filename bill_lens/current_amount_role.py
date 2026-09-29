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


def _has_current_without_distractor(window: str) -> bool:
    # A distractor anywhere in this number's window vetoes a current label,
    # including "amount due for this bill" where the current phrase is nearer.
    return (any(pattern.search(window) for pattern in _CURRENT)
            and not any(pattern.search(window) for pattern in _DISTRACTORS))


def derive_current_amount_role_flags(fields: ExtractionFields, document: PdfText) -> set[ReviewFlag]:
    """Confirm any signed occurrence; nulls add nothing and values are untouched."""
    if fields.current_bill_amount is None:
        return set()
    amount = Decimal(fields.current_bill_amount)
    for occurrence in printed_number_occurrences(document):
        if occurrence.value != amount:
            continue
        # A label belongs to the first numeric token after it. Earlier numbers
        # on this line consume their labels, so inspect only the intervening text.
        before = _normalise(occurrence.line[occurrence.previous_number_end:occurrence.start])
        # Any alphabetic text except currency/credit decorations is label-like,
        # even if unrecognised. Unknown same-line labels must not borrow a heading.
        label_like = any(c.isalpha() for c in _DECORATION_WORDS.sub("", before))
        # A previous line with a number has already consumed its label. Refuse
        # this fallback even if PDF reading order put the next value below it.
        window = (before if label_like else
                  "" if occurrence.previous_line_has_number else _normalise(occurrence.previous_line))
        if _has_current_without_distractor(window):
            # Presence of a recognised label is still not a column/role proof.
            return set()
    return {"current_bill_amount_role_unconfirmed"}
