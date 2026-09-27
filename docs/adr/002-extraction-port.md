# ADR-002: A bill extraction port with recordable attempts

- Status: Accepted for M1 after Claude re-review of commit 06c4d82
- Scope: Provider-independent extraction and a deterministic local fake

## Context

M1 needs one upload-to-JSON path, but HTTP and persistence should be testable
before choosing or paying for a model. The existing `PdfText` boundary preserves
page text and input identity. The extraction contract defines schema-valid bill
fields; Python domain checks then decide whether those fields need review.

Model calls can fail, refuse or truncate. If only successful fields survive,
later `ExtractionRun` records cannot explain what happened or compare attempts.
Provider structured-output guarantees also cannot replace our own validation.

## Decision

Expose a synchronous structural `BillExtractor` protocol:

```text
extract(document: PdfText) -> ExtractionAttempt
```

The protocol speaks about bills rather than chat messages or provider SDK types.
An adapter instance owns its model and prompt labels; each attempt records its
provider, model, prompt version, raw response, validated fields or error code,
optional input/output token counts, and nonnegative integer latency in ms.
No `PromptSpec` or real prompt is introduced yet.

`build_attempt` requires an explicit `latency_ms` argument. Real adapters must
provide their measured latency rather than silently recording a default zero;
the fake explicitly supplies its configured synthetic latency (zero by default).

### Returned failures and raised mistakes

Expected provider/model failures return an attempt with `fields=None` and one
of `rate_limited`, `timeout`, `refused`, `truncated`, `invalid_output`, or
`provider_error`. This lets persistence handle success and failure through the
same record path. Raw response text is retained whenever it exists, even for
refusals, truncation and invalid output. Missing usage counts are `None`, not
fabricated zeros. Only actual response text belongs in `raw_response`; adapters
must never copy provider exception messages there.

Wrong input types, inconsistent metadata and programming errors still raise.
PDF failures remain `PdfTextError`: the PDF stage has not made an extraction
attempt to record. A schema-valid attempt can still have domain review flags:
`bill_002` succeeds with `current_bill_amount=None`, then Python emits
`current_bill_amount_missing`. Attempt success is not the final bill status.

### One validation gate

Every adapter uses `build_attempt(...)`. When there is no explicit provider
error, it validates the raw JSON object directly with `ExtractionFields` and
returns success or `invalid_output`. The object contains the seven extraction
keys directly; it is not an `expected.json` label or a `{"fields": ...}` wrapper.
Before schema validation, a standard-library JSON pass inspects object pairs
and rejects duplicate keys at any nesting level, including repeated identical
values and escaped spellings of the same key. Otherwise JSON parsers can discard
earlier values and silently choose the last one. The original raw response is
preserved even when rejected. This preflight never supplies decoded values to
Pydantic: malformed JSON, integer-limit `ValueError` and depth `RecursionError`
fall through to validation of the original text. Only duplicate detection adds
a rejection rule; the existing Pydantic JSON behavior remains the final schema gate.

The helper neither repairs JSON nor strips response text, calculates totals,
or runs domain checks. Schema validation catches Pydantic `ValidationError`;
programming errors propagate.

An explicit failure takes precedence over any apparently valid JSON in its raw
response. A truncated or refused reply must not become a success just because
its text passes schema validation. The helper accepts stable error codes, not
provider exception objects or messages.

`ExtractionAttempt.__post_init__` enforces success/failure exclusivity, valid
error codes, typed fields/raw text, nonblank labels, and nonnegative integer
counts/latency (booleans are rejected). Both success and `invalid_output` require
raw response text. The successful-raw requirement is slightly stronger than the
minimum task invariants and follows from retaining the text that was validated.

### Deterministic fake

`FakeExtractor` snapshots a mapping from `PdfText.file_sha256` to frozen
`ScriptedResponse` values. Each call for the same hash returns the same outcome;
there is no queue, clock, randomness, retry or network operation. The adapter
uses fixed labels `fake`, `fake-v1`, and `fixture-v1`. Latency defaults to zero;
token counts default to unknown. Scripts can provide fixed values for all three.
Invalid scripted metadata raises when exercised through the shared helper.

`FakeExtractor.from_dataset(root)` takes the **dataset directory**, not the repo
root. It reads `bill_*/bill.pdf` hashes and validates the adjacent `expected.json`
labels, serializes only `label.fields` as raw JSON, and sends that text through
the same helper on every extraction. It does not copy expected flags or statuses
into an attempt. Missing or malformed fixtures and duplicate PDF hashes raise
setup errors. Unknown hashes raise `KeyError`: a missing local fixture is a
configuration mistake, not a simulated provider outage. Use an explicit
`ScriptedResponse(error_code="provider_error", raw_response=None)` to simulate
an outage.

## Alternatives

| Alternative | Reason not chosen now |
| --- | --- |
| Generic LLM client (`chat(messages) -> str`) | Exposes transport/prompt concepts where callers need bill extraction; still needs a domain adapter and schema gate. |
| LangChain | Adds dependencies and abstractions without a current need; a small protocol and helper cover this use case. |
| Raise exceptions for provider failures | Encourages callers to record only successes or build separate persistence paths; expected failures are useful attempt data. |
| Fake returns label models directly | Bypasses raw JSON validation and cannot exercise malformed response handling. |
| Unknown hash returns `provider_error` | Hides a missing fixture as a provider incident; explicit scripted failures are clearer for local testing. |

## Trade-offs

- The fake looks up answers by PDF hash. It exercises PDF ingestion, the port,
  schema validation and domain checks together; it does not interpret page text
  or establish extraction accuracy, prompt quality, provider compatibility,
  real latency, token consumption or cost. Its pipeline test intentionally uses
  the labels as fake answers and is not a model evaluation.
- Real adapters must use the helper by convention and review. A Python protocol
  does not enforce that at runtime. Direct record construction checks invariants
  but does not prove the fields came from a particular raw response.
- The record is frozen, while the existing nested `ExtractionFields` model is
  mutable. Treat attempts as read-only snapshots. The fake validates afresh on
  each call so mutations of one result do not affect later results.
- Raw responses may contain customer data or malicious instructions. They are
  untrusted data, not safe log messages; persistence and logging policies remain
  necessary before real customer use.
- Real adapters, prompts, retries, HTTP and persistence are deliberately deferred.
  The dataset loader is a development facility, not a production provider.

## When we will revisit

Revisit the synchronous port when the first real adapter or HTTP endpoint needs
async behavior. Choose provider-specific failure mapping and raw-response
capture when that adapter is implemented. Revisit immutable nested models and
attempt serialization when persistence is added. Extend metadata only when
evaluation or operational evidence needs it; schema-valid outputs will still
require accuracy evaluation against independent human labels.

Add static type checking when adapters are introduced: the current test's
`BillExtractor` annotation is not an automated compatibility check. A runtime
protocol check alone would not verify method signatures or return types. Before
exposing the fake through HTTP, decide how dev mode reports an unknown fixture
hash so an expected unsupported upload does not become an unexplained HTTP 500.
The contract currently gives `stated_billing_days` a positive lower bound only.
Revisit a realistic upper bound with billing-period evidence before changing the
contract; an arbitrary 366-day cap could reject legitimate longer adjustments.
Regression tests cover the current JSON integer-parser boundary at 4300/4301
digits so changes in Python or Pydantic parsing limits require investigation.
