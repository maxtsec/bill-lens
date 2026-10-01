# Evaluation harness (M2)

The [first v4 live evidence](../docs/learning/retailer-brand-evaluation.md)
preserves the v2 dev baseline, v4 dev comparison and first retailer holdout run.
It includes a dev false acceptance despite improved retailer scores. Further
live calls still require explicit authorisation.

Ask whether a prompt/model/extraction change improves measured outcomes on the
same labelled inputs. Scores are deterministic Python comparisons, never an LLM
judge. Results from the five dev or six holdout synthetic bills are descriptive; they do not establish
real-world accuracy or statistical significance.

## Run offline

From the repository root in the existing development environment:

```powershell
.\.venv\Scripts\python.exe -m evals.run --extractor fake --repeats 3
```

The default output is a new, unique `evals/results/<UTC-time>-<random-id>/`
directory. It is git-ignored and excluded from package discovery. `--output`
selects another **new** directory; existing paths are refused, never overwritten.
`--dataset` selects a directory with direct `bill_*/bill.pdf` or
`holdout_*/bill.pdf` and `expected.json` pairs. Discovery is not recursive.
The default is this repository's dataset. All PDF/label bytes are loaded,
validated and hashed before any provider call; duplicate PDF hashes are rejected.

Use `--dataset dataset/holdout` for the separate six-case retailer-brand holdout
(fake or, after authorisation, OpenAI mode). Summary/report headers identify the
directory as `dataset_name`: `dataset` for dev and `holdout` for the new set.
Old artifacts without it display `legacy (name not recorded)`; input hashes still
control comparability. Dev and holdout runs cannot be directly compared.
See [holdout discipline and owner checklist](../dataset/holdout/README.md): labels
must be owner-verified before a live run, and cases used to revise a prompt after
seeing results must become development data and be replaced by fresh holdouts.

The production path is `extract_pdf_text` → `BillExtractor.extract` (the adapter
calls `build_attempt`) → `derive_review_flags(fields, document)`/`derive_status`. Evaluation introduces no
second parser, field validator or flag implementation. The fake reads the frozen
label answers, so its perfect score is a **harness self-test**, not evidence that
a model can extract anything. Its unknown token usage stays unknown; cost is zero.

## Run live only after explicit approval

The CLI supports one requested model per run; use separate directories for model
comparisons. Live mode requires both `BILL_LENS_LIVE=1` and `OPENAI_API_KEY` in the
process environment, plus an explicit `--model`. No key is read from `.env` by
the harness. Keep keys out of commands, reports, commits and chat.

```powershell
# Only after authorising paid evaluation; load OPENAI_API_KEY privately first.
$env:BILL_LENS_LIVE = "1"
try {
    .\.venv\Scripts\python.exe -m evals.run --extractor openai --model gpt-5.4-mini --repeats 3
} finally {
    Remove-Item Env:BILL_LENS_LIVE -ErrorAction SilentlyContinue
}
```

Before client construction the CLI prints bills × repeats × one model (15 calls
for this example), the output directory and a dated estimate from ADR-006's
2026-09-29 price table. Initially supported candidates are gpt-5.4-mini and
gpt-5.4; extending the choices requires a dated price entry. This is not a claim
that they are the best available models.

The **planning heuristic** assumes UTF-8 page-text bytes / 4 plus 2,000 input
tokens per bill for instructions/schema/framing, and the adapter's full 4,096
output-token cap per call. It is not tokenization or a spending ceiling. Prices
are standard uncached USD rates for at most 272k input tokens; they exclude tax,
regional/account adjustments and caching savings. Recheck prices before spending.
Completed attempts use actual returned input/output token counts to estimate
cost. Output tokens already include reasoning. Missing usage or an unpriced
resolved model leaves full cost unknown, with known subtotals and coverage shown.

Calls are sequential, one pass over bills per repeat. There is no repair or retry
loop; the production adapter has SDK retries disabled. Configuration errors stop
the run, close the client and produce a marked partial report (exit code 1).
They do not become document failures or fill in scores for unattempted bills.
Recorded timeouts/refusals/etc. are scored failed attempts and the run continues.
The existing live smoke script remains available but imports this harness's
scoring and price functions, so there is only one comparison implementation.

## Artifacts and provenance

**Synthetic dataset only.** `attempts.jsonl` deliberately includes exact raw
model output, predicted fields and label answers. Do not point this harness at
real bills without revisiting privacy, consent, redaction and retention. The
default result directory is ignored, but a custom output directory might not be.
No results are automatically committed; the owner chooses evidence to publish.

| File | Contents |
| --- | --- |
| attempts.jsonl | One completed attempt per bill/repeat, raw response, predicted/expected fields, outcomes, supply components, predicted/expected flags/status, exact match, requested/resolved model, provider, prompt version, effort, tokens, latency, cost, timestamp and input hashes |
| summary.json | Counts and denominators, per-bill metrics, usage/cost coverage, runtime versions, Git/dataset revisions, hashes, repeats, planned/completed counts and completion/abort state |
| report.md | Readable field outcome table, per-bill correctness across repeats, review decisions, errors, usage/latency/cost and dataset hashes |

JSON strings escape NUL and lone surrogates losslessly; they are not discarded or
repaired. The report does not echo raw output. Attempt lines are flushed after
each completed record. On a caught exception, partial summaries are written and
the error is re-raised (configuration errors get a safe CLI message). A process
crash may leave only JSONL; such a directory is not a comparable completed run.

Each run identifies harness/scoring versions, code Git commit/dirty state,
dataset Git commit/dirty state, **PDF and label SHA-256 per bill**, provider,
requested/resolved model, configured/observed prompt version, effort, repeat
count and start time. File hashes identify the actual evaluated bytes, including
uncommitted label changes. If Git is unavailable its revision is null. A dirty
checkout is allowed for development, but commit IDs alone cannot reproduce it;
use clean commits for retained evaluation evidence. Record library/Python versions
because PDF text extraction can change across environments. An API-returned alias
cannot be promoted to a snapshot ID the provider did not return.

## Metric definitions

The rules come from [the extraction contract](../docs/extraction-contract.md):
Retailer, Billing period, Total usage, Daily supply rate, Current bill amount,
and JSON shape and review rules (including its final evaluation paragraph).

Every completed attempt contributes exactly once to **each of seven fields**:

| Outcome | Meaning |
| --- | --- |
| correct | Both null, or equal under the field rule |
| wrong_value | Both non-null but differ |
| missing | Expected non-null, predicted null |
| false_extraction | Expected null, predicted non-null |
| no_fields | Whole attempt failed; no validated fields exist |

- Retailer: trim, collapse whitespace and casefold. Do not remove legal suffixes
  or map aliases.
- Dates: exact validated ISO dates. Stated days: exact integer.
- Usage/current amount: Decimal equality, preserving sign; `108.07` equals
  `108.070`, but `-4.00` does not equal `4.00`.
- Supply: production conversion to AUD/day without rounding, plus equal GST
  basis. Value and basis matches are also reported independently **when both rate
  objects exist**. Otherwise component scores are unavailable, not successful;
  component coverage is shown beside the eligible denominator. Matching an
  expected `unknown` GST label measures extraction, not financial comparability.

Exact bill match requires all seven outcomes to be correct. Review flags compare
the production-derived set to the **manual label**; status compares the derived
status to expected_status. Label flags are never regenerated by the harness.
These scores are reported separately from field accuracy but are not statistically
independent of it. A failed attempt has flags=null and status=failed: empty
expected flags do not accidentally award it a flag match.

Scoring version **3** combines field, printed-presence and current-amount-role
flags from the same PdfText used for extraction. `score_attempt` requires that document;
the missing-value oracle is still manually labelled. No fields are repaired.
For example, an unprinted amount now routes to review while retaining its
incorrect value, so status can improve without a field or exact-flag match.

Attempt outcomes show successes (`none`) plus every error code, including zero
counts. All field and decision metrics show `count/total`; failures stay in the
denominator. Partial runs show both planned and completed attempt counts, with
scores over completed attempts only. No unmade request is scored. Totals for an
aborted run remain unknown even when every saved attempt has usage; subtotals
cover recorded attempts only, not a call that raised without a returned attempt.

The per-bill table shows correctness across repeats, e.g. 2/3 for a field. It
reveals changing correctness; it is not pairwise value agreement (three different
wrong values and one repeated wrong value can both score 0/3). Inspect JSONL for
the exact values. Median/max latency describe completed extraction attempts, not
PDF parsing, startup or HTTP/database latency. Sequential ordering and warm
connections can affect timing; the tiny dataset cannot establish stable latency.

## Compare

```powershell
.\.venv\Scripts\python.exe -m evals.compare evals/results/<run-a> evals/results/<run-b>
```

Directories or summary.json paths are accepted. Comparison prints per-field
correctness and other outcome changes, then each bill's exact/review/field
changes. Improved/regressed/unchanged describes correct-count fractions, not
statistical significance. Cost or latency is not used to claim extraction quality.

The header shows A and B's provider, requested/resolved models,
configured/observed prompt versions, reasoning effort and code commit. It lists
changed dimensions and warns when more than one differs, because the score
change cannot be attributed to a single variable. Requested/resolved model are
one dimension; configured/observed prompt versions are one dimension.

Per-bill field rows also show every incorrect outcome's count A -> B. For
example, `missing: 3/3 -> 0/3; no_fields: 0/3 -> 3/3` remains visible even though
correctness stays 0/3. These are distributions across repeats, not paired
attempt transitions; `unchanged` refers only to correctness.

Comparison refuses incomplete runs, unequal PDF/label manifests, unequal repeat
counts, and different/unsupported harness or scoring versions. It validates field
denominators and the outcome partition. Different model, prompt and code commits
are intentional comparison dimensions; dirty/missing code provenance produces a
loud warning. Inputs are local run summaries, not signed evidence: do not edit
artifacts and then treat them as original measurements.

The `extract-v4` brand-first clarification changes the prompt and retailer schema
description, but keeps existing dev dataset bytes and scoring semantics unchanged. Preserve
the original v2 run; compare a separately authorised v4 dev run with the same model,
effort and repeats. The header will warn about both prompt and code changing:
review that code diff when interpreting results. Do not claim that offline
request tests prove improved extraction accuracy. To reproduce v2, use its
original code/schema commit; loading only the old prompt with today's schema
would not recreate the original model input.

M3 presence introduced scoring **2**; the current-amount label check uses **3**.
Current `evals.compare` refuses historical scoring-1 and scoring-2 artifacts, including
old-vs-new comparisons. The earlier v2/v4 comparisons above describe scoring 1;
reproduce them with their original checkout. Do not edit their version numbers
or overwrite original results. A separate offline replay verifies recorded
PDF/label hashes and reuses saved responses to report decision changes. The
first command retains historical scoring-2 decisions; the second compares 2 to 3:

```powershell
.\.venv\Scripts\python.exe -m scripts.rescore_printed_values --output tmp/m3-replay.json
.\.venv\Scripts\python.exe -m scripts.rescore_current_amount_roles --output tmp/m3-role-replay.json
```

This is derived evidence, not a new live run or a directly comparable run summary.
See [ADR-009](../docs/adr/009-printed-value-check.md) and
[ADR-010](../docs/adr/010-current-amount-role-check.md). Neither replay makes a
model call or changes the preserved source artifacts.

## Opt-in budget ceiling and pre-registered role-holdout run

`--budget-usd <positive USD amount>` enables a sequential reservation ledger
in `budget.json`. Budgeted OpenAI runs require a clean recorded Git commit.
The guard reserves before each call, settles from known token usage, and stops
before a reservation would exceed the cap. Unknown usage/model or an exceeded
token allowance stops with the reservation retained, never a fabricated zero.
Aborts keep attempts, ledger, summary and report as a clearly marked partial
run; `evals.compare` refuses it. Existing runs without this option are uncapped.

For the owner-only 30-call v4 role-holdout run, the exact US$0.30 profile,
allowance assumptions, key-entry/cleanup commands and frozen analysis method
are in the [pre-registered plan](../docs/learning/role-holdout-live-plan.md).
No live call is part of preparation/tests. Do not automatically resume or rerun.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_evals.py tests/test_openai_smoke_helpers.py -q
```

Tests cover all outcomes, the five dataset traps, supply components, repeated
fake runs, scripted failures, JSON round trips, a hand-authored report snapshot,
comparability, live gates and early termination using a stub. The default suite
clears credentials and blocks real HTTP transports. **No live API call was made
in CI/tests.** Further live evaluations remain separately authorised steps.
