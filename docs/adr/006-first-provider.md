# ADR-006: First real extraction provider

Status: Accepted after Claude review of 8893b39 and owner approval

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

The standalone `configured_extractor()` helper accepts
`BILL_EXTRACTOR=fake|openai`, defaulting to fake. OpenAI requires a nonblank
`OPENAI_MODEL` and a nonblank printable ASCII `OPENAI_API_KEY`. Invalid provider,
missing key and syntactically invalid model/key fail at helper construction. Remote
credential validity and model access cannot be checked without a request;
authentication/model-access rejections raise the safe `OpenAIConfigurationError`
on a real call. No construction-time request lists models or validates the key.

**API wiring moves to a separate follow-up PR.** `create_app` constructs the
fixture-backed fake regardless of `BILL_EXTRACTOR`; existing test injection stays
available. It does not call the config helper or construct an OpenAI client.
The adapter, prompt, standalone config helper and gated live script stay in this PR.

Review exposed that the current hash-idempotency path permanently returns the
first saved failure. The owner chose **option A** for the follow-up: re-uploading
a bill whose latest run failed with `rate_limited`, `timeout` or `provider_error`
will retry extraction, append an ExtractionRun (preserving history), and update
Bill status atomically. Concurrent re-uploads need regression coverage before
enabling real extraction in the API. This recovery is an M1 follow-up prerequisite,
not deferred to M6. Successful/non-retryable results keep the existing reuse rule.

Pin `openai==3.20.0`. The SDK uses httpx2; its resolved dependencies are pinned in
requirements-dev.txt. Use the synchronous Responses API with `tools=[]`,
`store=False`, `stream=False`, `service_tier="default"`, and a 4096-output-token
cap. Set `reasoning={"effort": "low"}` explicitly for both baseline models: a
bounded starting point for printed-fact extraction, not an accuracy finding.
The `extract-v2` execution profile fixes this effort; changing effort requires a
version bump, so each attempt's existing prompt_version identifies it without a
DB migration. The smoke report also prints reasoning_effort. Independently
configurable effort and a dedicated per-run column can follow in M2 if needed.
The model is supplied by config, never selected in adapter code. No native PDF input,
conversation history or tools are enabled. `store=False` is not a claim of zero
provider retention; consult the provider's data controls before real customer data.

The client pins the official API base URL instead of taking an ambient alternate
endpoint. API keys, document text and raw responses are never logged by this
adapter. Error handling never copies SDK exception messages or HTTP error bodies
into attempts. Standalone callers close their extractor; the live script does so
in a finally block. The extractor closes only SDK clients it creates; injected
clients remain caller-owned. The existing service holds no DB connection during
extraction (ADR-005); HTTP integration is deferred as described above.

### Prompt and document boundary

The packaged file `bill_lens/extraction/prompts/extract_v2.md` declares
`Prompt-Version: extract-v2`; that header supplies attempt.prompt_version.
Version 1 is retained unchanged (it used default reasoning and predictable PAGE
markers). Version 2 uses explicit low effort and randomised PAGE markers.
Tests pin SHA-256 of each version's UTF-8 text after normalising line endings,
matching the adapter loader. Any wording or fixed execution-setting change must
create the next versioned file and update the loader/profile tests. Do not update
an old digest to make a changed prompt pass.
Package data includes the file so non-editable installations retain the prompt.

The prompt states printed facts only, no arithmetic, all required keys, and
untrusted document text. Field semantics come from the Pydantic schema's existing
descriptions. Page text is sent in one user message, inside a unique BILL marker
chosen not to occur in the source; each numbered PAGE delimiter shares that
random marker, so predictable PAGE text cannot impersonate a real boundary. The
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
Review rechecked the official supported-properties list on 2026-09-29; it lists
both date format and exclusiveMinimum. A schema/parameter rejection now raises
instead of becoming a document attempt. The first owner-authorised live check
must still establish actual model/schema compatibility; no constraints are
silently removed to make a request pass.
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

| Situation | Result |
| --- | --- |
| SDK rate limit (429) | rate_limited |
| SDK client timeout | timeout |
| Refusal content (including on an incomplete response) | refused |
| Other incomplete response | truncated |
| HTTP 401 / 403 / 404 | Raise OpenAIConfigurationError (authentication / permission / model_or_endpoint_not_found) |
| HTTP 400/422, code context_length_exceeded | provider_error |
| HTTP 400/422, code content_policy_violation | refused (no model text) |
| Other HTTP 4xx except 408/409/429 (including schema/parameter rejection) | Raise OpenAIConfigurationError (request_parameters_or_schema) |
| HTTP 408 / 429 | timeout / rate_limited |
| HTTP 409, 5xx, other API/connection errors; non-completed response; missing output | provider_error |
| Completed output rejected by build_attempt | invalid_output |

Explicit refusal/truncation/failure takes precedence over apparently valid JSON.
Partial/refusal text is retained, and usage is recorded if the response includes
it. Unexpected application errors still raise. HTTP error attempts have no raw
text or usage because only the exception diagnostics were returned.

Document-specific 400/422 errors use an explicit code allowlist; type is the
fallback only when code is absent. Messages are never inspected. Unknown 400/422
errors raise conservatively rather than silently persisting a configuration bug.
Authentication/permission/not-found status takes precedence over document codes.
Raised errors contain only a stable local reason, not SDK diagnostics; they are
raised outside the SDK exception handler so neither __context__ nor __cause__
retains the private HTTP body. A rejection stops the manual smoke check rather
than spending credit on further calls with the same bad configuration.

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
not a latest/best-model claim. Retain the original two-model, ten-call scope for
this adapter smoke check: same-family small/mid-tier candidates with the same
explicit low effort and dated pricing. GPT-6 Luna/Sol are valid newer candidates,
but adding another comparison is deferred to M2; this is not a recommendation
to prefer GPT-5.4 on cost or quality. No live baseline has yet been measured.
The script does not constrain OPENAI_MODEL in the standalone config helper.
Extending its candidates requires adding a dated price entry first.

Price snapshot checked **2026-09-29**, standard USD per million text tokens:

| Model | Uncached input | Output |
| --- | ---: | ---: |
| [gpt-5.4-mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) | 0.75 | 4.50 |
| [gpt-5.4](https://developers.openai.com/api/docs/models/gpt-5.4) | 2.50 | 15.00 |

Both linked model pages were rechecked during review; the GPT-5.4 page explicitly
lists $2.50 input and $15.00 output per million tokens, and both pages support low
reasoning effort. Prices still require rechecking before spending credit.

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

Next PR: option A transient-failure recovery and then API wiring, with concurrent
retry tests. Deferred: M2 evaluation/provider comparison, native PDF input, automatic retry/backoff policy,
prompt-injection experiments, pricing history/cached-token accounting and M6
tracking of paid calls discarded by the simultaneous duplicate path (ADR-005).
