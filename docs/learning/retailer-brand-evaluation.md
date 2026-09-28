# Retailer selection improved; an amount-due trap still escaped

Measured on 2026-09-29 Australia/Sydney (run timestamps use 2026-09-28 UTC).
This is evidence from small synthetic datasets, not a real-bill accuracy claim.

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

The next proposed investigation is the **existing dev bill_002 amount-due
failure**, with a separately reviewed change and fresh authorisation for any
new calls. Do not silently patch labels, repair responses or rerun until green.
This evidence PR changes no extraction behaviour. No holdout promotion has
occurred: if a future prompt/rule is tuned using these held-out results, record
promotion to development data and add fresh held-out bills before claiming
generalisation. This set is now evaluated; it is no longer unseen by the team.

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

## Preserved evidence and offline verification

The [artifact manifest](evidence/retailer-brand-v4/manifest.json) hashes each
preserved source file and the generated comparison. Original `attempts.jsonl`,
`summary.json` and `report.md` are copied byte-for-byte for all three runs:

- [v2 dev report](evidence/retailer-brand-v4/v2-dev/report.md)
- [v4 dev report](evidence/retailer-brand-v4/v4-dev/report.md)
- [v4 holdout report](evidence/retailer-brand-v4/v4-holdout/report.md)
- [v2 to v4 dev comparison](evidence/retailer-brand-v4/v2-vs-v4-dev.md)

The 48 saved attempts include the historical 15 plus the newly authorised 33.
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
