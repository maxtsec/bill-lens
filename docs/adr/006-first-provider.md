# ADR-006: First real extraction provider

Status: Proposed (awaiting review)

## Context

The M1 HTTP/persistence path works with a deterministic fake. The owner has
OpenAI pay-as-you-go credit and selected OpenAI for the first adapter. This is
a practical constraint, **not measured superiority** in bill extraction. The
`BillExtractor` port preserves the option of other providers; M2 will compare
accuracy, latency and cost using evidence.

No live API call has been made for this implementation. Account access, model
availability, real schema acceptance and extraction quality remain unverified.
Only offline stubs and an SDK MockTransport have exercised the new adapter.

## Decision

### Configuration and lifetime

`BILL_EXTRACTOR=fake|openai` defaults to fake. OpenAI requires a nonblank
`OPENAI_MODEL` and a nonblank printable ASCII `OPENAI_API_KEY`. Invalid provider,
missing key and syntactically invalid model/key fail at app construction. Remote
credential validity and model access cannot be checked without a request;
authentication/model-access API errors become `provider_error` on a real call.
No startup request lists models or validates the key against the API.

Pin `openai==3.20.0`. The SDK uses httpx2; its resolved dependencies are pinned in
requirements-dev.txt. Use the synchronous Responses API with `tools=[]`,
`store=False`, `stream=False`, `service_tier="default"`, and a 4096-output-token
cap. The model is supplied by config, never selected in adapter code. Other
generation settings use the model's API defaults; the first baseline should
record those defaults before interpreting comparisons. No native PDF input,
conversation history or tools are enabled. `store=False` is not a claim of zero
provider retention; consult the provider's data controls before real customer data.

The client pins the official API base URL instead of taking an ambient alternate
endpoint. API keys, document text and raw responses are never logged by this
adapter. Error handling never copies SDK exception messages or HTTP error bodies
into attempts. The app closes a client it creates at shutdown; injected clients
remain owned by their callers. The existing service holds no DB connection while
the adapter calls the provider (ADR-005).

### Prompt and document boundary

The packaged file `bill_lens/extraction/prompts/extract_v1.md` declares
`Prompt-Version: extract-v1`; that header supplies attempt.prompt_version.
Any wording change must create the next versioned file and update the loader.
Package data includes the file so non-editable installations retain the prompt.

The prompt states printed facts only, no arithmetic, all required keys, and
untrusted document text. Field semantics come from the Pydantic schema's existing
descriptions. Page text is sent in one user message, inside a unique BILL marker
chosen not to occur in the source and explicit numbered PAGE delimiters. The
instructions are a separate higher-priority API parameter. These measures and
the absence of tools reduce opportunities for document instructions to affect
behavior; they are not a complete prompt-injection defence. Adversarial evaluation
and stronger document provenance controls remain future work.

### Schema compatibility and raw text

Send `ExtractionFields.model_json_schema()` in `text.format` with
`type=json_schema`, `strict=true`, and the name `bill_fields`.

**Dropped schema keywords: none.** The generated schema has a required object
root, nullable fields via anyOf, nested $defs/$ref, additionalProperties=false,
descriptions/titles, enums, date formats and exclusiveMinimum for positive days.
Current [Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs)
lists the relevant date/numeric constraints as supported for base models.
This is a documentation-based compatibility finding, not a successful live probe.
Fine-tuned or other models may support a narrower subset. Any future compatibility
transform belongs here, must list its dropped keywords, and must have tests.

Python custom validators (decimal strings, retailer controls, exact ISO input)
are not all expressible in the generated schema. Structured Outputs also does
not establish field accuracy. `build_attempt` remains the final gate, including
duplicate-key rejection. The adapter never passes SDK-parsed fields through it.

Collect output_text and refusal content in API order. Preserve each text string
exactly; concatenate multiple parts without separators, matching the SDK's text
aggregation convention. Do not strip, repair or re-serialise. Reasoning items and
HTTP diagnostics are not raw_response. A refusal records its returned refusal
text. No text content means None; an explicitly empty output text stays "".

### Outcomes and telemetry

| Situation | Attempt error |
| --- | --- |
| SDK rate limit (429) | rate_limited |
| SDK client timeout | timeout |
| Refusal content (including on an incomplete response) | refused |
| Other incomplete response | truncated |
| Other API/connection errors; non-completed response; missing output | provider_error |
| Completed output rejected by build_attempt | invalid_output |

Explicit refusal/truncation/failure takes precedence over apparently valid JSON.
Partial/refusal text is retained, and usage is recorded if the response includes
it. Unexpected application errors still raise. HTTP error attempts have no raw
text or usage because only the exception diagnostics were returned.

`ExtractionAttempt.model` records the **API-returned model** when available;
otherwise (including request failure) it records the requested identifier.
The request uses OPENAI_MODEL, and the smoke report prints both names. If the API
returns only an alias, the adapter cannot invent an immutable snapshot; record
that limitation when retaining live evidence.

SDK `max_retries=0` and `timeout=60.0` are explicit. There is one request attempt,
no application retry and no repair loop. The timeout applies to HTTP operations,
not a guaranteed absolute wall-clock deadline. Monotonic timing surrounds the
entire SDK call on success and error; any future SDK retries would be included.
Input/output token counts come directly from usage. Output includes reasoning
tokens; the reasoning breakdown is **not added again**. Missing usage is None.
The [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)
describes reasoning token billing as output tokens.

### Owner-run live smoke check and prices

`python -m scripts.live_openai_check` refuses to construct a client unless both
`BILL_LENS_LIVE=1` and OPENAI_API_KEY are set. It preloads the five golden PDFs and
labels before any call, then runs two explicitly listed baseline candidates:
gpt-5.4-mini (small) and gpt-5.4 (mid-tier baseline). These are baseline choices,
not a latest/best-model claim. This script does not constrain OPENAI_MODEL in the
app. Extending its candidates requires adding a dated price entry first.

Price snapshot checked **2026-09-29**, standard USD per million text tokens:

| Model | Uncached input | Output |
| --- | ---: | ---: |
| [gpt-5.4-mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) | 0.75 | 4.50 |
| [gpt-5.4](https://developers.openai.com/api/docs/models/gpt-5.4) | 2.50 | 15.00 |

Estimate = (input_tokens * input_price + output_tokens * output_price) / 1,000,000,
using Decimal. All input is priced uncached, so caching savings are not included.
Prices assume at most 272k input tokens, standard service, no tools, and exclude
taxes, regional adjustments and account-specific terms. Estimates are not a
billing reconciliation. Usage missing, an unpriced resolved model, or longer
input makes the total estimate unknown rather than zero; known subtotals and
counts of missing calls are still printed. Recheck prices before a live run.

Output contains only per-bill status, code, flags, field-match booleans, tokens,
latency, model names and estimates. Comparisons follow the contract: case/whitespace
normalisation for retailers, Decimal numbers, unit-normalised supply rates with
GST basis checked separately. This is a smoke check, not an M2 accuracy estimate.
It neither writes files nor commits outputs; the owner chooses evidence to retain.

## Tests and deferred work

Default pytest tests remove live credentials/config and block real HTTP transports
for both httpx and httpx2. Stubs exercise all golden labels and all outcome classes;
MockTransport tests exercise actual SDK request/response parsing without a socket.
Unit tests check the closed live gates, comparisons and cost calculation. Neither
CI nor the default suite runs the live script with the gates open.

Deferred: M2 evaluation/provider comparison, native PDF input, retry/backoff policy,
prompt-injection experiments, pricing history/cached-token accounting and M6
tracking of paid calls discarded by the simultaneous duplicate path (ADR-005).
