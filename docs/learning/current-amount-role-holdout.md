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
