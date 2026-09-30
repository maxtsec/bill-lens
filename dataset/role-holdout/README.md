# Current-amount role holdout (PR B)

Ten fictional, digitally generated electricity bills in `holdout_r01` through
`holdout_r10`. Every PDF says `SYNTHETIC SAMPLE - NOT PAYABLE`; organisations and
figures are invented. **Owner verification is pending.** This PR constructs
inputs only. No current-amount role result or accuracy number is reported here.

## Holdout discipline

- The production rule and both label vocabularies are frozen at commit
  `940272e`. They must not change in response to this set. If a later change
  uses these results, reclassify this set as development data and obtain another
  fresh holdout before making a generalisation claim.
- **Do not run the role check or `derive_review_flags` on these PDFs in PR B.**
  Do not tune the layouts by trial against that rule. The tests use field-derived
  and printed-presence checks only. `evals.run`, including fake mode, would call
  the role check and is deliberately excluded.
- `expected.json` and `role_cases.json` were handwritten separately from the
  PDF generator. The owner must independently verify each PDF against both
  files **before** any offline role measurement or live run.
- This is a purpose-built synthetic set: its author knows the rule and selected
  the mix of shapes. Shared-author bias remains after owner verification. PR C
  must report by shape with denominators, never a real-world error rate.

`load_cases(dataset)` and `load_cases(dataset/holdout)` do not discover this
directory. Directly loading `dataset/role-holdout` is allowed for field-only
integrity checks. The existing loader hashes only `bill.pdf` and `expected.json`;
PR C must also hash `role_cases.json` before measuring role decisions.

## Case shapes and wording

`In` means the current label contains a complete, word-bounded phrase in the
frozen `CURRENT_LABELS` tuple after case/whitespace normalisation. `Out` means
no current-label vocabulary phrase occurs in that label. The six layout traps
(A, B, C, D, F, H) are In; the three ordinary-layout vocabulary cases (E) are
Out; G has no printed current total. The first draft mixed these dimensions;
Claude caught this during review, before any role measurement or owner
verification. Two E cases were added so all six layout traps could retain
their own known-label controls. Each row lists every printed account-level
non-current amount; charge-line amounts are excluded from `role_cases.json`.

| Case | Shape | Current-total label and source | Vocab | Non-current account labels and sources | Distractors |
| --- | --- | --- | --- | --- | ---: |
| holdout_r01 | A: same-line account activity | `Current charges` (EA) | In | `Opening balance` (EA); `Payments received` (EA); `Account credit` (AGL-WA); `Amount due` (EA) | 4 |
| holdout_r02 | B: label-header/value-row table | `Current charges` (EA) | In | `Previous balance` (AGL-VIC); `Payment` (AGL-VIC); `Account credit` (AGL-WA); `Amount Due` (AGL-VIC) | 4 |
| holdout_r03 | C: value-above-caption boxes | `Total current charges` (EA-PDF) | In | `Previous balance` (AGL-VIC); `Payment` (AGL-VIC); `Account credit` (AGL-WA); `Total amount due` (EA-PDF) | 4 |
| holdout_r04 | D: GST number inside total label | `Current charges (incl. 10% GST)` (EA and AGL-VIC, adapted) | In | `Previous balance` (AGL-VIC); `Payment` (AGL-VIC); `Account credit` (AGL-WA); `Amount Due` (AGL-VIC) | 4 |
| holdout_r05 | E: current label outside vocabulary | `Electricity charges` (AGL-VIC) | Out | `Previous balance` (AGL-VIC); `Payment` (AGL-VIC); `Account credit` (AGL-WA); `Amount due` (AGL-VIC) | 4 |
| holdout_r06 | F: credit carried forward | `Current charges` (EA) | In | `Previous balance` (AGL-VIC); `Payment` (AGL-VIC); `Balance carried forward` (EA); `Amount due` (EA) | 4 |
| holdout_r07 | G: no printed current total | none | n/a | `Opening balance` (EA); `Payments received` (EA); `Account credit` (AGL-WA); `Total amount due` (EA-PDF) | 4 |
| holdout_r08 | H: due on page 1, current on page 2 | `Current charges` (EA) | In | `Previous balance` (AGL-VIC); `Payment` (AGL-VIC); `Account credit` (AGL-WA); `Amount due` (AGL-VIC) | 4 |
| holdout_r09 | E: ordinary summary | `Total charges` (AGL-VIC) | Out | `Previous balance` (AGL-VIC); `Payment` (AGL-VIC); `Account credit` (AGL-WA); `Amount due` (AGL-VIC) | 4 |
| holdout_r10 | E: ordinary summary | `Total electricity charges` (ORG) | Out | `Previous balance` (AGL-VIC); `Payment` (AGL-VIC); `Account credit` (AGL-WA); `Amount due` (AGL-VIC) | 4 |

### Wording sources

- **EA:** [EnergyAustralia electricity bill guide](https://www.energyaustralia.com.au/home/bills-and-accounts/understand-your-bill/bill-guides)
  distinguishes opening balance, payments received, balance carried forward,
  current charges and amount due.
- **EA-PDF:** [EnergyAustralia electricity bill explainer](https://www.energyaustralia.com.au/sites/default/files/2019-08/300719_PDF_Website_Bill_Explainer_ELEC_FINAL.pdf)
  shows “Total Current Charges” and “Total amount due”. The synthetic box drops
  the source's GST/“see over” qualifier from the first label.
- **AGL-VIC:** [AGL Victorian electricity bill explainer](https://www.agl.com.au/content/dam/digital/agl/documents/help-and-support/agl-bill-explainer-vic.pdf)
  shows previous balance, payment, total charges, amount due and the “new charges
  and credits” section. Its prose uses “electricity charges”. R04 combines EA's
  “Current charges” wording with AGL's GST-inclusive explanation and an explicit
  `10%` qualifier; this whole string is a realistic adaptation, not a quotation.
- **AGL-WA:** [AGL WA gas bill explainer](https://www.agl.com.au/content/dam/digital/agl/documents/help-and-support/agl-bill-explainer-wa.pdf)
  shows “Account credit”. It supplies terminology only; these ten documents
  are synthetic electricity bills.
- **ORG:** [Origin Energy unmetered supply bill explainer](https://www.originenergy.com.au/billing-payments/read-your-ums-bill)
  uses “Total electricity charges”. It supplies terminology, not a sampled
  household bill or a claim of representative frequency.

All source links are official retailer materials. The PDFs use selected terms
and layouts, not copies of those retailers' bills. R01 puts ordinary payment
prose immediately below amount due; R08 also includes nearby prose about “this
period's total”. R07's account summary uses different wording from dev bill_002.
Wording and layout selection were made before any role check.

## Handwritten label semantics

Each `expected.json` uses the existing seven-field `ExpectedLabel` format.
`expected_flags` and `expected_status` are **ground truth for field-derived
and printed-presence rules only**. They never include
`current_bill_amount_role_unconfirmed`: that is the measured heuristic outcome.
An incorrectly flagged correct amount should therefore count as a false review
in PR C. This differs from the dev/retailer-holdout oracle, where labels and
production review flags are checked as one combined decision.

`role_cases.json` separately records the correct amount (null for R07), its
printed label (null for R07), shape A-H, and every account-level distractor.
Each distractor has a signed numeric `value`, exact `printed_label`, and role.
The R06 `45.00 CR` credit is recorded as `"-45.00"`. A same-line `Account
credit: AUD 5.00` is also `"-5.00"` under the shared numeric tokenizer's
credit-prefix rule; the value-only table row in R02 stays `"5.00"` because its
label is on another line. Both are credits and their positive magnitudes are
subtracted in account arithmetic. No distractor here equals its bill's correct
current amount; if such a duplicate is added, exclude it from role cases and
explain the exclusion here. All 40 listed account-level distractors are
nonzero, so zero balances cannot dilute the later missed-distractor count.

All other fields are deliberately straightforward: ISO service dates, a
period-level day count, printed import usage, one AUD/day supply rate and an
explicit GST-inclusive basis. Displayed charge lines sum to the current total;
amount due equals previous balance minus payments and credits plus current
charges. R07 prints its line items and amount due but **no current total**, so
its field is null with `current_bill_amount_missing`.

## Regenerate and inspect offline

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_role_holdout
.\.venv\Scripts\python.exe -m pytest tests/test_role_holdout.py -q
```

The generator accepts `--output <directory>` for byte-for-byte regeneration
tests. It reads no label file. Visual review should inspect all ten PDFs,
including both pages of R08, as well as text extraction order. These commands
perform no model call or role measurement.

## Owner verification: merge blocker

For **each** case, compare the PDF visually with both JSON files: all seven
fields, flags, status, the shape, and every distractor amount and label. A
passing test is not independent human ground truth. Mark a box only after the
owner checks that case; later edits to its PDF or labels reset the box.

- [ ] Owner verifies holdout_r01.
- [ ] Owner verifies holdout_r02.
- [ ] Owner verifies holdout_r03.
- [ ] Owner verifies holdout_r04.
- [ ] Owner verifies holdout_r05.
- [ ] Owner verifies holdout_r06.
- [ ] Owner verifies holdout_r07.
- [ ] Owner verifies holdout_r08 (both pages).
- [ ] Owner verifies holdout_r09.
- [ ] Owner verifies holdout_r10.

## After merge

PR C will measure the **frozen** role rule offline on correct amounts and every
listed distractor, reporting confirmed/false-review and caught/missed counts
**per shape with denominators**. It must preserve PDF, `expected.json` and
`role_cases.json` hashes and avoid rule changes. An optional live v4 run needs
new explicit owner authorisation and a budget; this PR authorises none.
