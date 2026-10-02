# Frozen current-amount role rule on the owner-verified holdout

## Method and provenance

The ten fictional bills in [role-holdout](../../dataset/role-holdout/README.md)
were owner-verified before measurement. ADR-010's rule and vocabularies were
frozen at `940272e`. [Hand predictions](evidence/role-holdout-predictions.json)
for nine printed correct amounts and 40 annotated account-level distractors
were committed **first**, alone, at main commit `bf6f32c` (original PR #21
branch: `9fc8131`). They used ADR-010 and the PDF
text extracted by `extract_pdf_text`. The author states that the role check was
not run before that commit; Git history establishes the commit order, not that
local execution history. The separately recorded r07 prediction covers its
null current amount.

The [offline measurement](evidence/role-holdout-measurement.json) then applied
the frozen production role check to each correct amount and to each signed
distractor substituted for `current_bill_amount`. It also recorded printed
presence, combined flags and status, and every matching occurrence's page,
line number, full line and previous non-empty line. Those locations come from
the shared numeric tokenizer; the measurement script does not reproduce the
role rule's label-window logic. The script refuses changed input hashes and
output overwrite. The evidence includes hashes for each of the 30 PDF/label/
role-annotation files, their manifest hash
`15334a4973dacc340c1bb93f02e04c8f24ec0c678544f8a3257ff7d8f31892e5`,
the preregistered prediction hash, and implementation fingerprints.
The saved evidence reproduced byte for byte at main commit `ef1bbf7` (original
PR #21 branch: `a8f5706`). The current replay
compares every result and provenance field, excluding only the measurement
script's own hash, which is still recorded in each output. Changes to that
runner therefore do not block reproduction, but any changed measurement result
still fails the comparison. Rule, validation, schema, PDF-reader and
role-annotation code fingerprints remain locked: if one changes, replay skips
with a pointer to `ef1bbf7`, and direct measurement refuses execution. The saved
evidence hash, input hashes, prediction hash, totals and PDF provenance are
checked on every run regardless. Reproduce a changed rule from `ef1bbf7` rather
than regenerating this one-time evidence with newer code.

No live API call was made. This is a deterministic counterfactual: distractors
were substituted into otherwise correct fields, not emitted by a model.

### Commit identities after rebase merge

Rebase merge rebuilt commits on main. Each pair below has an identical Git
tree; prediction still precedes measurement in main's ancestry. Use main's
commits for checkout and reproduction. Saved evidence and predictions remain
byte-unchanged historical records, including the original prediction commit ID
in the measurement JSON.

| Purpose | Main commit | Original PR branch commit |
| --- | --- | --- |
| Owner-verified PR #20 version | `529d714` | `8082361` |
| Predictions only | `bf6f32c` | `9fc8131` |
| Original measurement | `ef1bbf7` | `a8f5706` |

## Results by case

`In` means a known current-charge phrase appears in the printed label; `Out`
means none does. `Caught` means the **role flag** was raised for the substituted
distractor. All 40 also produced a review status; silent false acceptances were
**0 / 40**. r07 has no printed correct current amount and is excluded from the
correct-amount denominator. A **false review** means the **combined flags or
status** disagree with the handwritten label, not merely that the role flag
appeared. In these six cases, the role flag was the only difference.

| Case | Shape | Label | Correct amount | Distractors caught / total | Missed values | Prediction mismatches |
| --- | --- | --- | --- | ---: | --- | ---: |
| r01 | A | In | confirmed | 4 / 4 | none | 0 / 5 |
| r02 | B | In | false review | 4 / 4 | none | 0 / 5 |
| r03 | C | In | false review | 4 / 4 | none | 0 / 5 |
| r04 | D | In | false review | 4 / 4 | none | 0 / 5 |
| r05 | E | Out | false review | 4 / 4 | none | 0 / 5 |
| r06 | F | In | confirmed | 4 / 4 | none | 0 / 5 |
| r07 | G | n/a | null; `current_bill_amount_missing` | 4 / 4 | none | 0 / 4 |
| r08 | H | In | confirmed | 4 / 4 | none | 0 / 5 |
| r09 | E | Out | false review | 4 / 4 | none | 0 / 5 |
| r10 | E | Out | false review | 4 / 4 | none | 0 / 5 |

## Results by shape and overall

| Shape | Correct amounts sent to review / total | Distractors caught / total | Prediction mismatches / items |
| --- | ---: | ---: | ---: |
| A | 0 / 1 | 4 / 4 | 0 / 5 |
| B | 1 / 1 | 4 / 4 | 0 / 5 |
| C | 1 / 1 | 4 / 4 | 0 / 5 |
| D | 1 / 1 | 4 / 4 | 0 / 5 |
| E | 3 / 3 | 12 / 12 | 0 / 15 |
| F | 0 / 1 | 4 / 4 | 0 / 5 |
| G | 0 / 0 | 4 / 4 | 0 / 4 |
| H | 0 / 1 | 4 / 4 | 0 / 5 |
| **All** | **6 / 9** | **40 / 40** | **0 / 49** |

Among the six layout traps A, B, C, D, F and H, false reviews were **3 / 6**.
Among the three ordinary-layout vocabulary cases E, they were **3 / 3**.
Missed distractors were **0 / 40**. For r07, the combined decision was exactly
`[current_bill_amount_missing]` and `needs_review`, matching the handwritten
label. Predictions disagreed with measurements on **0 / 49** measured values;
the separate r07 null prediction also matched. No rule or label was changed in
response to these results.

## Interpretation and limits

The zero prediction mismatches show that ADR-010's written first-number,
previous-line and distractor-veto behaviour matched this PDF text and the
implementation. It is expected for a deterministic rule; it is not a surprise
success. B's shared table header, C's caption-below boxes and D's numeric GST
qualifier account for the three layout false reviews. Each unfamiliar E label
accounts for a vocabulary false review. The rule caught each selected printed
non-current value, but these values and trap types were chosen by the same
author who knew the rule. Independent owner verification checked labels, not
sampling representativeness.

The set is synthetic and has a selected shape mix. There is only one example
with a current total outside the main account summary (r08, on page 2), and
most shapes have one template. The counterfactual uses **only each annotated
signed value**. A model might output a credit's unsigned magnitude instead;
printed-presence checking would then make a different decision. No live model
was run, so this does not measure extraction choices or a real-bill error rate.
There are no percentages or confidence intervals because the bills were not
sampled from a population.

The set has now been measured for this frozen rule. If the owner chooses to
adjust wording coverage, windows or evidence spans in response, this set must
be treated as development data, and a new holdout is needed for the revised
rule. A live v4 run on these bills requires separate authorisation and budget.

## Live v4 model run (2026-10-01)

### Pre-registration and execution

The [D1 plan](role-holdout-live-plan.md) and
[analysis script](../../scripts/analyse_role_holdout_live.py) were reviewed and
merged before testing in [PR #24](https://github.com/maxtsec/bill-lens/pull/24).
The run used clean main **`ce5ea6cab244a47e80977a7b850f0c49d0861dd7`**,
run ID **`20261001T015251Z-6495d365da87`**, starting at
**2026-10-01 01:52:51 UTC** (11:52:51 in Sydney). Requested model
`gpt-5.4-mini` resolved to **`gpt-5.4-mini-2026-03-17`**; prompt **extract-v4**,
reasoning effort **low**, output cap **4096**, SDK retries **0**, harness **1**,
scoring **3**. One sequential run completed **30/30** calls, ten bills with
three repeats each, without retry or additional evaluation.

After merge, the owner explicitly delegated execution to Codex and entered
the key in a local masked input dialog. The helper passed the key only to the
evaluation process; no key was saved in these artifacts or printed to tool
output. An initial input helper stalled before starting a run and was stopped;
no run was claimed and no API call was made by that helper. The replacement
used the same approved CLI, with an exclusive one-run claim and no automatic
rerun. The helper ended after execution and credential cleanup. This execution
handoff differs from D1's original owner-pastes-commands instructions; the
model, prompt, inputs, settings, scope and budget are unchanged.

Before testing, Claude's
[approval comment](https://github.com/maxtsec/bill-lens/pull/24#issuecomment-5922987192)
disclosed a known counterexample: r04 returning **10.00** would be processed,
because the unsigned credit magnitude also occurs as `10%` in the current
label. This was a stub probe, not a live answer. The live model returned
**95.60**, the correct amount, in all three r04 attempts.

### Preserved artifacts and frozen analysis

The five raw files are copied **byte for byte**, including original newline
bytes: [summary](evidence/role-holdout-live-v4/summary.json),
[attempts](evidence/role-holdout-live-v4/attempts.jsonl),
[evaluation report](evidence/role-holdout-live-v4/report.md),
[budget ledger](evidence/role-holdout-live-v4/budget.json), and
[package versions](evidence/role-holdout-live-v4/pip-freeze.txt).
The directory's `.gitattributes` disables newline conversion for these files.
The [manifest](evidence/role-holdout-live-v4/manifest.json) records SHA-256 and
byte lengths, run provenance, authorisation, and the pre-run plan/script hashes.
Original PR C evidence and all PDF/label/role-case inputs remain unchanged.

The already-merged analysis script was run unchanged and saved its
[derived JSON](evidence/role-holdout-live-v4/analysis/analysis.json) and
[derived report](evidence/role-holdout-live-v4/analysis/report.md) separately.
It verified all 30 input-file hashes against PR C, frozen rule/schema/reader
fingerprints, v4 prompt, coverage, ledger and scoring reconstructed from each
raw response. Preservation and analysis made **zero additional API calls**.

Reproduce offline from this checkout into a new directory:

```powershell
.\.venv\Scripts\python.exe -m scripts.analyse_role_holdout_live docs/learning/evidence/role-holdout-live-v4 --output tmp/role-live-replay
```

If a later rule or analysis change blocks reproduction, use **`ce5ea6c`**;
do not overwrite this saved run or regenerate its evidence using a new method.
The replay test fails explicitly when a frozen source file changes or disappears;
it never silently skips. Before changing those files, migrate the historical
replay check to the pinned implementation deliberately, retaining the saved
artifact hashes and result comparison.

### Outcomes by case and shape

False review follows the pre-registered live definition: a **correct non-null
current amount plus the role flag**. r07's expected null is separate. Here all
other fields are correct, and the role flag is the only source of false review.

| Case | Shape | Current amount correct | Wrong numeric value | Caught | Silent false acceptance | Role false review |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| r01 | A: same-line activity | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| r02 | B: table header/value row | 3/3 | 0/3 | 0/3 | 0/3 | 3/3 |
| r03 | C: value above caption | 3/3 | 0/3 | 0/3 | 0/3 | 3/3 |
| r04 | D: GST number in label | 3/3 | 0/3 | 0/3 | 0/3 | 3/3 |
| r05 | E: unfamiliar label | 3/3 | 0/3 | 0/3 | 0/3 | 3/3 |
| r06 | F: credit carried forward | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| r07 | G: no current total | 3/3 null | 0/3 | 0/3 | 0/3 | 0/3 |
| r08 | H: two pages | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| r09 | E: unfamiliar label | 3/3 | 0/3 | 0/3 | 0/3 | 3/3 |
| r10 | E: unfamiliar label | 3/3 | 0/3 | 0/3 | 0/3 | 3/3 |

| Group | Correct | Wrong numeric value | Caught | Silent false acceptance | Role false review |
| --- | ---: | ---: | ---: | ---: | ---: |
| Nine printed-current bills | **27/27** | **0/27** | **0/27** | **0/27** | **18/27** |
| r07 separately | **3/3 null** | **0/3** | **0/3** | **0/3** | **0/3** |
| All ten bills | **30/30** | **0/30** | **0/30** | **0/30** | **18/30** |
| Layout shapes A, B, C, D, F, H | 18/18 | 0/18 | 0/18 | 0/18 | **9/18** |
| Vocabulary shape E (three bills) | 9/9 | 0/9 | 0/9 | 0/9 | **9/9** |

Each non-E shape has one bill and three repeats; E has three bills and nine
attempts. The per-case rows therefore also supply each shape's counts, with
the E aggregate shown separately. There are **no wrong numeric values to list**
with label/page/line or caught status. The derived JSON still records printed
locations for every returned numeric value and all 30 final flags/statuses.
Zero wrong choices means there were **zero opportunities to observe a catch**;
it does not demonstrate that every possible distractor would be caught.

R07 returned **null 3/3**, copied amount due **112.20 in 0/3**, reconstructed
the unprinted **87.20 in 0/3**, and returned another non-null amount in **0/3**.
All three retain `current_bill_amount_missing` and `needs_review`, matching
the handwritten answer. The six other fields each match in **30/30** attempts.
All seven fields together match in **30/30**; combined flags/status match the
manual labels in **12/30**, because the role check adds the 18 false reviews.
There were **0/30** failed or schema-invalid attempts.

### Cost and limits

All 30 calls returned usage: **49,088 input tokens** and **5,900 output tokens**,
including reasoning. The ledger settles to **US$0.06336600**, below the
**US$0.30** approved cap, with **zero unresolved reservations**. Each call
reserved **US$0.043008** before extraction, then released the difference using
returned usage. The final conservative spent figure equals the settled estimate.
This uses the recorded uncached standard prices (dated 2026-09-29 and checked
again before execution), not an account invoice. Cached savings are excluded;
there is no account-wide billing claim.

These are ten selected **synthetic text PDFs**, one model/prompt and three
repeats per bill. Repeats expose variation, not independent documents; most
shapes have just one template. All-current-correct outcomes on this selected
set cannot establish real-bill accuracy, make the known r04 counterexample
safe, or invalidate the historical two catches in the 88-attempt replay.
The offline signed-distractor substitutions and these live extraction choices
answer different questions. No percentages or population-error estimates are
reported. The set is now seen by the frozen rule and this model/prompt; any
result-driven tuning requires promotion to development data and a fresh holdout.

### Recommendation for the owner

**Recommendation: keep the current production rule while reviewing a separate
evidence-span plus label/context prototype against a fresh holdout.** On this
run the rule caught no actual model error and imposed **18/27** false reviews;
broadening a label list alone would address the three E bills but not all table,
caption or GST-number cases. A returned matching span alone would still not
prove that a number has the current-charge role. A reviewed prototype should
test that context explicitly, including amount-due traps and the known r04
unsigned-credit/10% collision, before replacing the existing safeguard.

This is a proposed next decision, not an implemented change or permission for
more paid calls. The owner chooses whether to keep the rule, revise it with a
fresh holdout, or investigate evidence spans. D2 changes no production rule,
prompt, contract, schema or analysis method.
