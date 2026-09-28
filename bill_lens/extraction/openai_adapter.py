"""Responses API boundary: preserve output text and validate it locally."""

from collections.abc import Callable
from importlib.resources import files
import re
from time import perf_counter_ns
from uuid import uuid4

from openai import APIError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from openai.types.responses import Response

from bill_lens.contract import ExtractionFields
from bill_lens.pdf_text import PdfText
from .port import ExtractionAttempt, build_attempt

SDK_TIMEOUT_SECONDS = 60.0
SDK_MAX_RETRIES = 0
MAX_OUTPUT_TOKENS = 4096
# Fixed execution setting for extract-v4 (unchanged from v2/v3).
# Changing effort requires a prompt version bump.
REASONING_EFFORT = "low"


class OpenAIConfigurationError(ValueError):
    """Safe configuration/request failure, with no SDK diagnostics attached."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"OpenAI request rejected: {reason}")


def structured_schema() -> dict:
    """Current generated schema needs no keyword removal; Python stays final gate."""
    return ExtractionFields.model_json_schema()


def document_message(document: PdfText) -> str:
    marker = uuid4().hex
    while any(marker in page.text for page in document.pages):
        marker = uuid4().hex
    pages = [f"<<<BILL_{marker}_BEGIN>>>"]
    for page in document.pages:
        pages.append(f"<<<PAGE_{marker}_{page.page_number}_BEGIN>>>\n{page.text}\n<<<PAGE_{marker}_{page.page_number}_END>>>")
    pages.append(f"<<<BILL_{marker}_END>>>")
    return "\n".join(pages)


def response_text(response: Response) -> tuple[str | None, bool]:
    # Match SDK output_text concatenation, also retaining refusal content. No
    # separators, stripping, JSON repairs or serialisation of parsed objects.
    chunks = []
    refused = False
    for item in response.output:
        if item.type != "message":
            continue
        for part in item.content:
            if part.type == "output_text":
                chunks.append(part.text)
            elif part.type == "refusal":
                refused = True
                chunks.append(part.refusal)
    return ("".join(chunks) if chunks else None), refused


class OpenAIExtractor:
    provider = "openai"

    def __init__(self, *, model: str, api_key: str | None = None,
                 client: OpenAI | None = None, clock_ns: Callable[[], int] = perf_counter_ns):
        if not isinstance(model, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", model) is None:
            raise ValueError("OPENAI_MODEL must be a nonblank model identifier")
        if client is None and (not isinstance(api_key, str) or not api_key
                               or not api_key.isascii() or any(not 33 <= ord(char) <= 126 for char in api_key)):
            raise ValueError("OPENAI_API_KEY must be set to a nonblank ASCII token")
        self.instructions = files("bill_lens.extraction").joinpath("prompts/extract_v4.md").read_text(encoding="utf-8")
        header = self.instructions.splitlines()[0]
        if header != "Prompt-Version: extract-v4":
            raise ValueError("prompt file version does not match its filename")
        self.prompt_version = header.removeprefix("Prompt-Version: ")
        self.model = model
        self._clock_ns = clock_ns
        self._owns_client = client is None
        self._client = client if client is not None else OpenAI(
            api_key=api_key, base_url="https://api.openai.com/v1",
            max_retries=SDK_MAX_RETRIES, timeout=SDK_TIMEOUT_SECONDS,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def extract(self, document: PdfText) -> ExtractionAttempt:
        if not isinstance(document, PdfText):
            raise TypeError("document must be PdfText")
        message = document_message(document)
        schema = structured_schema()
        started = self._clock_ns()
        error_code = None
        rejection = None
        response = None
        try:
            response = self._client.responses.create(
                model=self.model, instructions=self.instructions,
                input=[{"role": "user", "content": message}],
                text={"format": {"type": "json_schema", "name": "bill_fields", "strict": True, "schema": schema}},
                tools=[], store=False, stream=False, service_tier="default",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                reasoning={"effort": REASONING_EFFORT},
            )
        except APITimeoutError:
            error_code = "timeout"
        except RateLimitError:
            error_code = "rate_limited"
        except APIStatusError as error:
            # Codes/types are machine-readable. Never inspect the message, which
            # may contain document text, credentials or request details.
            code = error.code or error.type
            if error.status_code in {401, 403, 404}:
                rejection = {401: "authentication", 403: "permission", 404: "model_or_endpoint_not_found"}[error.status_code]
            elif error.status_code in {400, 422} and code in {"context_length_exceeded", "content_policy_violation"}:
                error_code = "refused" if code == "content_policy_violation" else "provider_error"
            elif error.status_code == 408:
                error_code = "timeout"
            elif error.status_code == 429:
                error_code = "rate_limited"
            elif 400 <= error.status_code < 500 and error.status_code != 409:
                rejection = "request_parameters_or_schema"
            else:
                error_code = "provider_error"
        except APIError:
            error_code = "provider_error"
        # Raise outside the handler: `from None` alone would still retain the
        # SDK exception (and its private body) in __context__.
        if rejection is not None:
            raise OpenAIConfigurationError(rejection)
        latency_ms = (self._clock_ns() - started) // 1_000_000
        raw, model, input_tokens, output_tokens = None, self.model, None, None
        if response is None and error_code is None:
            error_code = "provider_error"
        if response is not None:
            model = response.model or self.model
            raw, refused = response_text(response)
            if response.usage is not None:
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens  # Includes reasoning; never add it twice.
            if refused:
                error_code = "refused"
            elif response.status == "incomplete":
                error_code = "truncated"
            elif response.status != "completed" or response.error is not None or raw is None:
                error_code = "provider_error"
        return build_attempt(
            provider=self.provider, model=model, prompt_version=self.prompt_version,
            raw_response=raw, error_code=error_code, input_tokens=input_tokens,
            output_tokens=output_tokens, latency_ms=latency_ms,
        )
