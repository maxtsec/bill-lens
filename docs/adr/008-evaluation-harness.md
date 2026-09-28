# ADR-008: Deterministic, file-based extraction evaluation

Status: Proposed (awaiting Claude review)

## Context

M1's production PDF boundary, extraction port, validation and retryable upload
flow exist. M2 must distinguish measurable improvements from attractive-looking
responses. The current dataset is five owner-reviewed synthetic text PDFs; no
claim about real-world accuracy or significance follows from this sample.

## Decision

### Production extraction, deterministic scoring

`python -m evals.run --extractor fake|openai` loads PDFs through extract_pdf_text,
calls the existing BillExtractor (which uses build_attempt), and derives review
decisions through production functions. Expected flags/status come from the
manual labels, never from running the validator on the answer. Evaluation does
not reproduce parsing, schema validation or domain-flag logic.

One scorer follows the named sections of the extraction contract: normalized
retailer whitespace/case with suffixes intact, exact dates/days, Decimal amounts
and usage, and unit-converted supply value plus exact GST label. The original
live smoke script imports this scorer and the shared dated price table. It remains
available for a quick two-model check but is not a second implementation of rules.

Each field receives exactly one of correct, wrong_value, missing,
false_extraction or no_fields. Missing expected values make false extraction
visible (bill_002); a whole failed attempt contributes no_fields to all seven
denominators. No-field attempts cannot earn flag matches by comparing two empty
lists. We separately report flags, status, exact seven-field match and the full
error distribution, including zero counts. Supply value/GST components are scored
when both objects exist, with unavailable counts so that subset scores cannot
masquerade as full coverage.

No LLM judge is used: these outputs have an explicit contract and manually
verified answers. A judge would add cost and nondeterminism without defining a
more defensible comparison. Normalization is scoring only; saved predictions and
raw output are not changed.

### Files, provenance and interruption

Write attempts.jsonl, summary.json and report.md under an ignored, unique
evals/results directory or a user-selected new directory. Never overwrite an
existing run. JSON escaping preserves NUL and lone surrogates. Files are simpler
to inspect/diff than another DB model and isolate evaluation from application
Bill identity/retry/current-run semantics. No DB or HTTP changes are needed.

Raw output, predictions and labels are deliberately retained because this
dataset is synthetic. Using real customer bills requires a new privacy/retention
decision. Custom output paths might not be ignored. No run is automatically
committed; the owner chooses evidence worth retaining.

Record versions, code/dataset Git revisions and dirty flags, exact PDF/label
hashes, runtime library versions, provider, requested/resolved model, prompt
versions, effort, repeats and timestamps. Load/hash bytes before any call and
build fake fixtures from those frozen labels. Git revision can be unavailable;
hashes remain authoritative for dataset bytes. Dirty development runs are allowed
with explicit provenance caveats; use clean commits for retained experiments.

Every completed attempt is flushed to JSONL. Configuration failures stop live
runs rather than becoming misleading provider-error samples. Partial reports
show planned/completed counts and an abort reason; unmade calls are not scored.
Usage/cost full totals remain unknown for aborted runs. Unexpected exceptions
also preserve partial results then propagate. Crash-damaged/incomplete output
is not accepted for comparison.

### Repeats and comparison

Run sequentially, cycling bills once per repeat; use one model per run. Display
counts with denominators, not standalone percentages. Per-bill/field correctness
across repeats exposes nondeterministic correctness (2/3), not pairwise agreement
of all predicted values. JSONL preserves the information for later analyses.

Compare per-field/per-bill correct fractions and field-outcome counts. Refuse
different input/label hashes, repeat counts, harness/scoring versions, incomplete
runs and invalid field denominators. Different model/prompt/code commits are
intentional experimental changes. Warn on dirty/unavailable code provenance.
Harness/scoring semantic changes require version bumps in evals/__init__.py.
Comparison is descriptive; repeated calls on the same five documents are not
independent new bills and do not establish significance.

### Cost controls

OpenAI requires both BILL_LENS_LIVE=1 and OPENAI_API_KEY, and an explicit model
from the dated ADR-006 price table. Print bills × repeats × one model and the
planning estimate **before constructing a client**. There are no automatic
retries/repairs beyond the adapter, whose SDK retries are zero. Keep clients
caller-owned and close them in finally.

The pre-call input estimate is text UTF-8 bytes/4 plus 2,000 tokens for
instructions/schema/framing; output assumes the full adapter cap. This is an
explicit heuristic, not tokenization or a spending cap. Completed cost estimates
use returned usage and dated uncached standard prices. Unknown usage/resolved
model does not become zero cost; subtotals and coverage remain visible. Fake
does not spend credit and has zero cost despite unknown usage.

## Deliberate limits

- No new bills, prompt changes, native PDF input, DB/HTTP changes or judge model.
- No real-world accuracy estimate, confidence interval or significance claim.
- No privacy-safe real-bill evaluation or signed/tamper-proof artifact store.
- No cost budget enforcement, tokenization dependency, cached-token accounting
  or pricing history beyond the dated source table.
- No concurrent model calls, automatic retry, resuming partial runs, baseline
  promotion or provider/model recommendation from this five-bill sample.
- The fake's perfect score tests plumbing and scoring; its answers are labels.
- Row counts, latency and cost coverage describe recorded attempts, not all
  possible provider activity when a call ends without a returned attempt.

## Verification

Hand-built oracles cover every taxonomy outcome and contract trap; scripted fake
failures contribute seven no_fields outcomes. Repeated fake runs, a hand-authored
Markdown snapshot, count partitions and input-hash comparisons protect reporting.
Live-gate tests prevent client construction without both variables. A stubbed
configuration rejection stops subsequent calls and leaves a marked partial run.
The retained smoke check shares scoring; its existing normalization/cost tests
continue to run. All tests are offline; live evaluation requires separate owner
approval and is not part of this implementation.
