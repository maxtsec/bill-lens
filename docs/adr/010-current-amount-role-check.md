# ADR-010: Check current-amount labels in Python before requesting evidence spans

Status: Proposed

## Context and decision

The scoring-2 presence check catches bill_002's unprinted 132.66 but accepts
162.66, which is printed only as amount due. Two of the 88 preserved responses
contain that error. The owner chose a deterministic Python label heuristic
before changing what the model must return: no extraction-field, prompt or
model JSON schema change, no live cost, and an offline-verifiable result.

For a non-null `current_bill_amount`, add
`current_bill_amount_role_unconfirmed` unless **any** matching signed occurrence
has a current-charges label in its window. Null adds no role flag. Do not repair,
replace or null the value. If the number is unprinted, both the existing
presence flag and the new role flag apply. A match is heuristic support, not
proof that the amount is correct.

## Exact window, vocabulary and tie rules

The role check consumes `printed_number_occurrences` from the presence checker.
There is one numeric tokenizer and one sign policy, including attached minus,
CR/credit, parentheses, thousands grouping and trailing sentence punctuation.
Values compare as Decimal. No numeric grammar is copied into the role checker.

For each equal signed occurrence:

1. Take the entire text prefix **before** its number on the same line. No
   forward scan, distance cap or reconstruction of columns is performed.
2. Casefold and collapse whitespace. For the fallback decision only, remove
   the whole decoration words `aud`, `cr`, `credit`. If any alphabetic character
   remains, the prefix is label-like, including unknown words: use that prefix.
   Otherwise use the immediately previous non-empty line on the **same page**.
   Currency symbols, punctuation and digits alone do not block fallback.
   Do not skip intervening non-empty lines or inherit across a page boundary.
3. Search the selected window for whole phrases below, bounded by non-word
   characters or the start/end of the window. Matching is case-insensitive and
   whitespace-normalised; no stemming, punctuation removal, hyphen expansion,
   fuzzy matching or translation is performed.
4. The label whose **end is nearest the number** wins (largest match end in the
   window; for a previous-line window, nearest its end). Equal ends across
   classes favour the **distractor**. Within a class, prefer the longer phrase.
   Current vocabularies do not overlap across classes; a test forces an overlap
   to preserve this tie policy for future additions.
5. A current winner confirms this occurrence. Any confirmed occurrence passes
   the field, regardless of other distractor occurrences. No recognised label
   in any selected window means a role flag.

The complete code vocabularies are:

| Accept current charges | Never confirm |
| --- | --- |
| current bill amount | amount due |
| current charges | total due |
| this bill | balance |
| total new charges | previous balance |
| new charges | payment |
| total current charges | payments |
| amount of this bill | overdue |
| | carried forward |
| | account balance |

These are general Australian billing terms, not fixture-specific templates:

- [EnergyAustralia's bill guide](https://www.energyaustralia.com.au/home/bills-and-accounts/understand-your-bill/bill-guides)
  distinguishes current charges from opening/carried balances, payments and
  amount due. It grounds the current-charge versus account-balance distinction.
- [Horizon Power's explanation](https://www.horizonpower.com.au/energyhub/understanding-your-energy-bill)
  uses “This bill” for new charges, separately from brought-forward balances and
  overdue amounts. This is a terminology example from WA, not Victorian testing.
- [Ergon's home bill guide](https://www.ergon.com.au/retail/help-and-support/billing-and-payments/understand-your-bill/understand-your-home-bill)
  separates new charges, balances and total amount due. It also shows why a
  label rule is conservative: some amount-due displays include only new charges
  when older debt exists. This QLD guide does not establish universal semantics.

Sources were checked on 2026-09-29. The full list is a deliberately small set of
plain-language variants around those concepts and the owner's proposed terms;
not every phrase is claimed as an exact quotation from those guides. For example,
`total current charges` adds a total qualifier and `amount of this bill` is an
ordinary variant. Unknown wording is not inferred. `Supply charge` is not a
current-total label or a member of the account-balance distractor vocabulary.

## Required layouts and known limits

- bill_001 has 108.07 as both current amount and amount due: any current-labelled
  occurrence passes. bill_003's 113.40 passes; its 163.40 amount due does not.
- bill_002's 162.66 has only an amount-due label and gains the role flag.
- bill_004's `Current bill amount` followed by `AUD 4.00 CR` confirms -4.00:
  AUD alone permits previous-line fallback; the shared tokenizer supplies sign.
- bill_005 extracts `Current bill amount Supply charge: AUD 29.45` followed by
  `AUD 29.45`. The current label is the only recognised label in the first prefix
  and in the second occurrence's previous-line window, so 29.45 passes. **This
  does not reconstruct columns.** If the supply charge on the first line were
  40.00, that wrong-column amount could pass too; a test records this limitation.

Vocabulary coverage, PDF reading order, tables and OCR remain unmeasured on real
bills. Labels after numbers, split across lines, unfamiliar words or intervening
notes may cause false reviews. Repeated amounts, unrelated text on the same
line, prose containing `this bill`, negation, and unknown intervening charge
labels can falsely confirm a value. We do not verify units, subtotals or the
accounting meaning of a whole sentence. Existing synthetic wording overlaps
the vocabulary, so passing this oracle and replay may be optimistic. Neither
this heuristic nor printed presence is a prompt-injection/security boundary.

## Integration and offline evidence

`derive_review_flags` unions field, printed-presence and current-amount-role
flags. Upload, evaluation and the smoke check use that same decision. Repository
integrity accepts the new document-derived flag only for a non-null current
amount, still requires every field-derived flag, and checks status consistency.
As with ADR-009, persistence trusts the service's document checks: it has no PDF
text and cannot independently prove either presence or role. Historical stored
rows are not backfilled. Scoring version is **3**; field-accuracy rules stay fixed.

The oracle produced **zero role flags on all 11 correct labels** (5 dev + 6
holdout), without changing labels or PDFs. The separate
[88-attempt replay](../learning/retailer-brand-evaluation.md#m3-offline-current-amount-role-replay)
changes silent false acceptance **2/88 → 0/88**, with **0 new false reviews**.
Three flag sets and two statuses change. No extracted value becomes correct as
a result; the two printed distractors now reach review and the already-rejected
unprinted amount acquires an additional flag. No live API call was made.

Original responses, manifest and scoring-2 evidence remain byte-unchanged.
`scripts.rescore_printed_values` explicitly retains historical scoring-2
decisions after the production bump. Its current implementation fingerprints
differ from the original artifact; reproduce those original fingerprints from
the original checkout. The new role replay verifies the original hashes and
scoring-2 decisions, then saves scoring-3 results and current source fingerprints
separately in [current-amount-role-check.json](../learning/evidence/current-amount-role-check.json).

## Next decision

PR B should create a **fresh holdout with varied wording and an amount-due
trap**, with owner-verified labels and the role rule fixed before evaluation.
The existing evaluated holdout is not unseen evidence for this check. Measure
missed distractors and newly flagged correct answers before claiming broader
coverage. Request model evidence spans plus context verification only if this
Python-first approach proves insufficient. No new holdout or live evaluation
is part of this PR.
