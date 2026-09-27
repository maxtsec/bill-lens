"""Domain port and the shared gate from raw model text to a recordable attempt."""

import json
from dataclasses import dataclass
from typing import Literal, Protocol, get_args

from pydantic import ValidationError

from bill_lens.contract import ExtractionFields
from bill_lens.pdf_text import PdfText

ExtractionErrorCode = Literal[
    "rate_limited", "timeout", "refused", "truncated", "invalid_output", "provider_error",
]


@dataclass(frozen=True)
class ExtractionAttempt:
    provider: str
    model: str
    prompt_version: str
    raw_response: str | None
    fields: ExtractionFields | None
    error_code: ExtractionErrorCode | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int

    def __post_init__(self) -> None:
        for name in ("provider", "model", "prompt_version"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must not be blank")
        if self.raw_response is not None and not isinstance(self.raw_response, str):
            raise TypeError("raw_response must be a string or None")
        if self.fields is not None and not isinstance(self.fields, ExtractionFields):
            raise TypeError("fields must be ExtractionFields or None")
        if self.error_code is not None and self.error_code not in get_args(ExtractionErrorCode):
            raise ValueError("unknown extraction error_code")
        if (self.fields is None) == (self.error_code is None):
            raise ValueError("exactly one of fields and error_code must be set")
        if (self.fields is not None or self.error_code == "invalid_output") and self.raw_response is None:
            raise ValueError("success and invalid_output require a raw_response")
        for name in ("input_tokens", "output_tokens", "latency_ms"):
            value = getattr(self, name)
            if value is None and name != "latency_ms":
                continue
            # bool is an int subclass but is not meaningful usage/latency metadata.
            if type(value) is not int:
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be nonnegative")


class BillExtractor(Protocol):
    def extract(self, document: PdfText) -> ExtractionAttempt:
        """Return expected provider failures; raise invalid arguments and bugs."""
        ...


def _has_duplicate_keys(raw: str) -> bool:
    duplicate = False

    def inspect_object(pairs: list[tuple[str, object]]) -> None:
        nonlocal duplicate
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            duplicate = True
        # This pass only inspects keys; Pydantic validates the original raw text.

    try:
        json.loads(raw, object_pairs_hook=inspect_object)
    except (ValueError, RecursionError):
        # Malformed JSON, integer limits and excessive depth remain Pydantic's
        # responsibility. Do not turn preflight parser limits into app crashes.
        pass
    return duplicate


def build_attempt(
    *, provider: str, model: str, prompt_version: str,
    raw_response: str | None, latency_ms: int,
    error_code: ExtractionErrorCode | None = None,
    input_tokens: int | None = None, output_tokens: int | None = None,
) -> ExtractionAttempt:
    """Every adapter passes raw field-object JSON through this validation gate.

    An explicit provider failure takes precedence even if its raw text happens
    to be valid JSON. Never pass exception messages as raw_response: only actual
    model response text belongs there. No stripping, repairs or inferred fields.
    """
    if raw_response is not None and not isinstance(raw_response, str):
        raise TypeError("raw_response must be a string or None")
    fields = None
    if error_code is None:
        if raw_response is None:
            raise ValueError("a response or explicit provider failure is required")
        if _has_duplicate_keys(raw_response):
            error_code = "invalid_output"
        else:
            try:
                fields = ExtractionFields.model_validate_json(raw_response)
            except ValidationError:
                error_code = "invalid_output"
    return ExtractionAttempt(
        provider=provider, model=model, prompt_version=prompt_version,
        raw_response=raw_response, fields=fields, error_code=error_code,
        input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=latency_ms,
    )
