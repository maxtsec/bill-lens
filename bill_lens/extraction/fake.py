"""Hash-keyed fixtures for exercising the pipeline without a model or network."""

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from bill_lens.contract import ExpectedLabel
from bill_lens.pdf_text import PdfText

from .port import ExtractionAttempt, ExtractionErrorCode, build_attempt


@dataclass(frozen=True)
class ScriptedResponse:
    raw_response: str | None
    error_code: ExtractionErrorCode | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0


class FakeExtractor:
    provider = "fake"
    model = "fake-v1"
    prompt_version = "fixture-v1"

    def __init__(self, responses: Mapping[str, ScriptedResponse]):
        self._responses = dict(responses)
        for digest, response in self._responses.items():
            if not isinstance(digest, str) or not digest.strip():
                raise ValueError("fixture keys must be nonblank document hashes")
            if not isinstance(response, ScriptedResponse):
                raise TypeError("fixture values must be ScriptedResponse")

    @classmethod
    def from_dataset(cls, root: str | Path) -> "FakeExtractor":
        """Load a dataset directory containing bill_*/bill.pdf and expected.json.

        Missing/malformed fixtures and duplicate hashes raise as setup errors;
        they must not be disguised as provider failures or silently overwritten.
        """
        root = Path(root)
        cases = sorted(root.glob("bill_*"))
        if not cases:
            raise ValueError("dataset must contain at least one bill_* case")
        responses = {}
        for case in cases:
            digest = sha256((case / "bill.pdf").read_bytes()).hexdigest()
            label = ExpectedLabel.model_validate_json((case / "expected.json").read_text(encoding="utf-8"))
            if digest in responses:
                raise ValueError("dataset contains duplicate PDF hashes")
            responses[digest] = ScriptedResponse(raw_response=label.fields.model_dump_json())
        return cls(responses)

    def extract(self, document: PdfText) -> ExtractionAttempt:
        if not isinstance(document, PdfText):
            raise TypeError("document must be PdfText")
        response = self._responses.get(document.file_sha256)
        if response is None:
            raise KeyError("no scripted outcome for document hash")
        return build_attempt(
            provider=self.provider, model=self.model, prompt_version=self.prompt_version,
            raw_response=response.raw_response, error_code=response.error_code,
            input_tokens=response.input_tokens, output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
        )
