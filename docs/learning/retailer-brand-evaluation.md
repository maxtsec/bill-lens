# Retailer selection improved; an amount-due trap still escaped

Measured on 2026-09-29 Australia/Sydney (run timestamps use 2026-09-28 UTC).
This is evidence from small synthetic datasets, not a real-bill accuracy claim.

Follow-up: the separately authorised [bill_002 repeat study](#bill_002-repeat-study)
observed false extraction in v2 0/20 and v4 2/20. Both v4 failures suppressed
review, but this small study does not establish a version-level regression rate.

## Question and result

Does extract-v4's brand-first retailer rule handle the original development
failures and six previously unevaluated retailer layouts?

| Metric | v2 dev: 5 bills x 3 | v4 dev: same 5 x 3 | v4 holdout: 6 bills x 3 |
| --- | ---: | ---: | ---: |
| Retailer correct | 12/15 | 15/15 | 18/18 |
| Current bill amount correct | 15/15 | 14/15 | 18/18 |
| Each of the other five fields correct | 15/15 | 15/15 | 18/18 |
| All seven fields correct together | 12/15 | 14/15 | 18/18 |
| Flags match | 14/15 | 14/15 | 18/18 |
| Status matches | 15/15 | 14/15 | 18/18 |
| Provider/validation failures | 0/15 | 0/15 | 0/18 |

The retailer result improved on these observed dev attempts. It is not an
unqualified improvement: one v4 dev attempt falsely extracted an amount and
was incorrectly marked processed. The holdout result supports the narrow
retailer rule across these six layouts; its other fields were deliberately
straightforward and do not independently establish robust amount selection.

## Execution and provenance

The owner explicitly authorised **33 new live calls**: 15 dev, then 18 holdout.
Both completed once, sequentially, with no repair, retry or extra diagnostic
model calls. The existing v2 baseline was copied, not rerun.

A later, separate authorisation added exactly **40 bill_002-only calls** under
a USD 0.20 estimated-cost budget. The evidence now contains **88 attempts**:
15 historical baseline + 33 first-v4 evaluation + 40 repeat-study attempts.
The two newly authorised batches total 73 calls, not one pooled evaluation.

| Run | Saved run ID | Clean evaluated commit |
| --- | --- | --- |
| v2 dev baseline | `20260928T212834Z-11548f32c4b3` | `1ecad8057dd29695d5ceca23722c0b959607dd21` |
| v4 dev | `20260928T224629Z-d833f7fb2248` | `b1fdef0009504c44e19b13d9f957e2143d3447b6` |
| v4 holdout, first live run | `20260928T224659Z-206893300747` | `b1fdef0009504c44e19b13d9f957e2143d3447b6` |

All three runs requested `gpt-5.4-mini` and resolved to
`gpt-5.4-mini-2026-03-17`, with `low` effort, three repeats, a 4096 output-token
cap, 60-second timeout and zero SDK retries. Harness/scoring versions are 1/1.
The runtime matches: Python 3.12.14, Pydantic 2.13.5, pdfplumber 0.11.10,
pdfminer.six 20260107 and OpenAI SDK 3.20.0. Both code and dataset were clean
when each run began. No prompt, schema, PDF, label or scoring change was made
while running or after inspecting these results.

The dev PDF and label hashes match the v2 baseline exactly. The holdout hashes
identify the revised, owner-reverified 001 and 006 PDFs after PR #12 removed
answer hints. All six holdout bills had been owner-verified before this run.

In the first v2 dev run, all planted non-retailer traps were avoided across
15/15 attempts; all three scored errors were in retailer (two `LANTERN`
selections, one null). The logo/full-name discrepancy exposed a **specification
gap**: both names were displayed, and the old wording did not clearly prioritise
the full brand. It is not sufficient evidence of a model violating a clear
brand-first instruction. The null retailer is still an observed extraction
miss; saved output alone cannot establish that its cause was the same gap.
Historical labels and scored errors remain unchanged.

The comparison warns that **both prompt and code commit differ**. Inspection of
the diff finds changed retailer instructions in both the prompt and outbound
schema description, the adapter's prompt selection, and holdout discovery/display
metadata. Scoring, original dev input bytes, model settings and runtime versions
are unchanged. This measures the combined v4 change; it cannot isolate prompt
wording from schema wording or establish causation from three stochastic repeats.

## The failure that the headline score hides

In **v4 dev, bill_002, repeat 3**, `current_bill_amount` was `"162.66"` instead of
`null`. That number is the printed **amount due**, which includes a previous
balance; no current-period total is printed. The model did not return the
reconstructable current amount of 132.66 either. Its returned value matches the
specific amount-due distractor.

Raw response excerpt: `"current_bill_amount":"162.66"`. Observation only:
this failing attempt used **138 output tokens**, versus **205 and 213** for the
two correct bill_002 attempts. Output usage includes reasoning tokens; these
counts do not expose the reasoning or prove shorter output caused the failure.
The repeat study also found a false extraction with 258 output tokens, so a
short-output explanation is not established.

The JSON is well-formed and passes the field schema. Consequently Python sees a
present current amount, emits no flags and derives `processed`. The independent
label expects `current_bill_amount_missing` and `needs_review`. This is one
observed false acceptance, not an API or JSON validation error.

| bill_002 repeat 3 | Expected | Returned/derived |
| --- | --- | --- |
| current_bill_amount | null | 162.66 |
| flags | current_bill_amount_missing | empty |
| status | needs_review | processed |

The other two v4 attempts on bill_002 correctly returned null. v2's bill_002
failure was a missing retailer; v4 fixed retailer across all three attempts but
introduced the amount error in one. bill_002's exact score therefore stays 2/3
while its failure type and status correctness change. bill_003 retailer/exact
improves from 1/3 to 3/3; bill_001, 004 and 005 stay exact 3/3.

**Engineering lesson:** a valid structured response does not prove that a value
came from the right place on the bill. Field-derived review flags cannot detect
this semantic error when the returned value itself looks valid. Aggregate exact
match alone also hides changes in which errors reach users.

## Holdout interpretation and next decision

Each of holdout_001 through holdout_006 scored retailer 3/3 and exact 3/3:
full brand versus logo, abbreviation only, distributor, brand versus legal
entity, legal entity only, and parent/group affiliation. No fields, flags or
status mismatches occurred in this first holdout run.

These are six documents, not 18 independent layouts. They share a synthetic
designer with their labels, are text PDFs, and have simple non-retailer fields.
Owner verification reduces labelling mistakes but does not remove shared-author
bias. Do not pool dev and holdout into a single accuracy claim or interpret the
18/18 result as measured accuracy on real or scanned bills.

The follow-up below investigates the **existing dev bill_002 amount-due
failure** under a separate bounded authorisation. It changes no extraction
behaviour. Do not silently patch labels, repair responses or rerun until green.
Further calls need fresh authorisation. No holdout promotion has
occurred: if a future prompt/rule is tuned using these held-out results, record
promotion to development data and add fresh held-out bills before claiming
generalisation. This set is now evaluated; it is no longer unseen by the team.

It contains **no amount-due trap** and cannot validate a future bill_002 fix.
No prompt change was made from its results. This repeat study calls only the
existing dev bill_002. Open design options, not decisions or demonstrated fixes:

- Grounding/evidence spans checked against PDF text in Python. A matching span
  alone cannot distinguish amount due from current amount; role and surrounding
  context would also need verification.
- Self-consistency: two extractions, disagreement routes to review. This costs
  more calls and cannot catch two agreeing wrong answers.
- A larger model, evaluated separately for accuracy and cost. No such calls
  are authorised or made in this study.

## Usage, latency and estimated cost

| Run | Input tokens | Output tokens | Median / max latency ms | Estimated USD |
| --- | ---: | ---: | ---: | ---: |
| v2 dev (historical) | 19,233 | 2,832 | 1,617 / 2,403 | 0.02716875 |
| v4 dev | 24,179 | 2,384 | 1,819 / 2,812 | 0.02886225 |
| v4 holdout | 29,130 | 2,409 | 1,707 / 2,386 | 0.03268800 |

The **33 new calls** used 53,309 input and 4,793 output tokens, with full usage
coverage and an uncached standard-price estimate of **USD 0.06155025**. The
historical v2 cost is excluded. This is not the provider invoice: caching
discounts, tax and account/regional adjustments are not reflected. Output usage
includes reasoning. Prices were checked on 2026-09-29 against the official
[GPT-5.4 mini model page](https://developers.openai.com/api/docs/models/gpt-5.4-mini):
USD 0.75 input / 4.50 output per million tokens. The pre-run heuristic was
USD 0.66145275, using the full output cap; it was not a spending limit.

Latency describes sequential adapter calls, not HTTP upload or database latency.
These small runs do not establish a stable speed difference.

Input usage rose from 19,233 to 24,179 tokens, about **25.7%**, in the original
matched dev comparison. The longer v4 retailer rule appears in both instructions
and schema, increasing input size. This does not establish why the amount error
occurred.

## Preserved evidence and offline verification

The [artifact manifest](evidence/retailer-brand-v4/manifest.json) hashes each
preserved source file and the generated comparison. Original `attempts.jsonl`,
`summary.json` and `report.md` are copied byte-for-byte for all three runs:

- [v2 dev report](evidence/retailer-brand-v4/v2-dev/report.md)
- [v4 dev report](evidence/retailer-brand-v4/v4-dev/report.md)
- [v4 holdout report](evidence/retailer-brand-v4/v4-holdout/report.md)
- [v2 to v4 dev comparison](evidence/retailer-brand-v4/v2-vs-v4-dev.md)

The original 48 saved attempts include the historical 15 plus the first authorised 33.
Their raw responses contain only synthetic fixture data. No API key, request
headers, `.env` or real customer data is included. The local evidence directory's
`.gitattributes` disables newline conversion so Git preserves artifact bytes.

Offline checks reparsed all 48 raw responses through `build_attempt`, rescored
them against the unchanged manual labels, reproduced every summary, checked
exact bill/repeat coverage and current PDF/label hashes, and verified matching
runtime/model settings. Cross-dataset comparison is still rejected. None of
these checks makes a model call. The targeted offline suite
`python -m pytest tests/test_evals.py tests/test_holdout.py -q --tb=short`
passed **86 tests**; `git diff --check` was clean. To regenerate the dev comparison offline:

```powershell
.\.venv\Scripts\python.exe -m evals.compare docs/learning/evidence/retailer-brand-v4/v2-dev docs/learning/evidence/retailer-brand-v4/v4-dev
```

The original ignored `evals/results/` directories are retained locally. The
preserved baseline is not rewritten to add the newer dataset-name metadata;
comparison displays its documented legacy fallback.

## bill_002 repeat study

On 2026-09-29 Australia/Sydney, the owner authorised exactly 20 calls per version
on **bill_002 only**, with a shared **USD 0.20 hard estimated-cost budget** and
no other live calls. Both runs completed; no requests were retried or added.

| Run | Run ID | Evaluated commit | Execution |
| --- | --- | --- | --- |
| v2 repeat | `20260928T232541Z-2b18b62e60bf` | `1ecad8057dd29695d5ceca23722c0b959607dd21` | detached worktree, that commit's own harness |
| v4 repeat | `20260928T232646Z-90f79aa5b450` | `424c0493740f14d03fd71ec6c8d20e5ce1b5a819` | new branch from up-to-date main, before documentation edits |

Both requested gpt-5.4-mini and resolved to gpt-5.4-mini-2026-03-17, low effort,
4096 output cap, 60-second timeout, no SDK retries. The same project venv served
both checkouts. All 45 entries in requirements-dev.txt match installed versions;
the requirements file is unchanged from v2. The
[pip freeze snapshot](evidence/retailer-brand-v4/repeat-study-pip-freeze.txt)
excludes the editable project path.

The one-bill dataset was a byte-for-byte copy under ignored
`tmp/datasets/bill_002_only/bill_002/`. Both commits' original bill/label bytes
match the copies (hashes in both summaries). The dataset lives beneath the
main checkout, so even the v2 summary records dataset Git revision `424c049`;
its **code** revision is correctly `1ecad80`. Hashes identify actual inputs.
Both checkouts were clean during execution. The clean detached worktree was
removed afterwards; nothing was committed from it.

The [repeat comparison](evidence/retailer-brand-v4/v2-vs-v4-bill-002-repeat.md)
warns that prompt and commit differ. v4's application and harness Python files
are unchanged since the first v4 run. Relative to v2, the model-facing change
is the retailer rule in prompt and schema; harness changes add holdout discovery
and display metadata and do not alter a bill_002 extraction or scoring. Today's
schema with only the v2 prompt would not reproduce v2.

### Amount, flags and status

| Outcome | v2 / 20 | v4 / 20 |
| --- | ---: | ---: |
| current_bill_amount correct (null) | 20 | 18 |
| current_bill_amount false_extraction | 0 | 2 |
| Other amount outcomes / failed attempts | 0 | 0 |
| Correct missing-amount flag + needs_review | 20 | 18 |
| Empty flags + incorrectly processed | 0 | 2 |
| False-extraction rate | 0% | 10% |
| 95% Wilson interval | 0.00%-16.11% | 2.79%-30.10% |

Both versions extracted retailer correctly 20/20. The other fields also remain
correct 20/20; exact bill match is v2 20/20 and v4 18/20.

Distinct wrong v4 amounts were **162.66 once** (repeat 3) and **132.66 once**
(repeat 13); v2 had none. Both responses had empty flags and status processed.

- Repeat 3 raw excerpt: `"current_bill_amount":"162.66"`, 138 output tokens.
  The value matches the printed amount due, reproducing the first-run failure.
- Repeat 13 raw excerpt: `"current_bill_amount":"132.66"`, 258 output tokens.
  It matches the reconstructable current charges including GST, but that total
  is not printed. The contract requires null even when arithmetic could recover
  a total. The response alone cannot prove the model's internal calculation path.

These observations confirm that the v4 failures can recur on this bill; they
do **not** establish that v4 has a higher underlying failure rate than v2.
The intervals are wide and overlap; individual intervals are not a formal test
of the between-version difference. Zero v2 failures is not proof of zero risk.
These are sequential repeats on one selected synthetic bill, v2 first then v4,
not independent documents or a randomised production sample. The earlier 0/3
versus 1/3 observations motivated this study and are not added to these
pre-specified 20-call denominators.

Wilson intervals use the standard-library `statistics.NormalDist` and `math`
formula in the [offline method](evidence/retailer-brand-v4/repeat-study-method.md),
following the [NIST definition](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
They describe uncertainty under a binomial repeated-call model with independent
trials and a stable failure probability; service/model variability and fixed
run order can weaken that assumption. No real-bill rate is inferred.

### Repeat-study cost and guard

| Run | Input tokens | Output tokens | Total / median / max latency ms | Estimated USD |
| --- | ---: | ---: | ---: | ---: |
| v2, 20 calls | 25,852 | 4,759 | 45,562 / 2,218.5 / 3,174 | 0.0408045 |
| v4, 20 calls | 32,448 | 5,437 | 49,008 / 2,484.5 / 3,156 | 0.0488025 |
| Total, 40 calls | 58,300 | 10,196 | 94,570 / not pooled / not pooled | **0.0896070** |

An ignored local wrapper guarded the requests; neither checkout's tracked
extraction/eval code was edited. Before every request it reserved **USD 0.043008**:
32,768 input-token allowance plus all 4,096 output tokens at the dated uncached
standard rates. It checked the serialized request stayed below 16,384 bytes
(actual requests: v2 6,311; v4 7,751), leaving a large input framing allowance.
Reservations were written before network I/O, settled only with known returned
usage, and shared across both runs. The next request would be blocked if
settled spend plus the reservation exceeded USD 0.20, or prior usage was unknown.
Configuration errors stop the original harness. Request settings and max counts
were checked; no repair, retries or other calls were allowed.

The [budget ledger](evidence/retailer-brand-v4/repeat-study-budget.json) records
all 40 settled calls. Its highest cumulative spend plus in-flight reservation
was **USD 0.1301385**, below 0.20; final estimated spend was **USD 0.0896070**.
Returned tokens stayed within the allowance. This enforces the authorised
estimated-cost accounting policy, not a provider-side invoice cap. The CLI's
unchanged planning heuristic prints USD 0.400965 per 20-call run; that
all-calls-at-full-output estimate is not the guard. High usage would have stopped
the study short of 40 calls: budget takes priority over completing the count.

### Added evidence and next step

- [v2 repeat report](evidence/retailer-brand-v4/v2-bill-002-repeat/report.md)
- [v4 repeat report](evidence/retailer-brand-v4/v4-bill-002-repeat/report.md)
- [Outcome counts, intervals and usage](evidence/retailer-brand-v4/repeat-study-statistics.json)
- [Offline method and verification](evidence/retailer-brand-v4/repeat-study-method.md)

The six new source artifacts are copied byte-for-byte; existing PR #13 evidence
is unchanged. New hashes and call provenance extend the same manifest. Raw
responses were revalidated and rescored offline, summaries reproduced, and
ledger usage reconciled to all 40 attempt records. No secrets, environment values
or machine-local paths are preserved. Only documentation and evidence changed,
including the holdout README wording nit; the root README link is retained.

The next decision remains which protection to prototype against the two dev
failure modes (wrong printed total and unprinted reconstructed total). The
options above are open. No prompt fix, new model comparison or further live
evaluation is included or authorised by this completed study.
