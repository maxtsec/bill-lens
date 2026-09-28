# Retailer-brand holdout set

Six synthetic, digitally generated electricity bills, separate from the five
development bills in `dataset/bill_001..005`. All organisations are invented;
there are no customer or contact details. Every PDF is marked
`SYNTHETIC SAMPLE - NOT PAYABLE`. The all-zero ABNs are deliberately invalid
placeholders, not real identifiers. A small explicit real-name deny-list is a
regression guard, not a comprehensive registry of all organisations.

**Status: owner verified holdout_001; holdout_002-006 remain pending.
No live evaluation has been run on this set. Do not merge or run it live until
the owner has checked every PDF against all seven fields, flags and status.**

## Holdout discipline

- These bills are not used to develop prompts or rules. The owner fixed the
  brand-first rule in the task brief; v4's rule text was written before these
  bills and labels. Offline checks verify file integrity, not model behaviour.
- Labels are written separately from the PDF generator and must be
  owner-verified **before any live run**. Never derive labels from model output.
- If any prompt/rule changes after looking at held-out model results, record
  the run, date and affected cases here, reclassify them as development data,
  and add fresh held-out bills before claiming generalisation.
- This is a purpose-built synthetic set sharing an author with its labels,
  not a blind real-world sample. Owner verification reduces shared-author bias;
  fake accuracy and six synthetic bills cannot establish real-world accuracy.
- Promotion record: **none**. First live run: **not performed**. Store future
  run IDs and any reclassification decisions here when separately authorised.

## Cases and retailer answers

| Case | Layout and source-selection situation | Expected retailer |
| --- | --- | --- |
| holdout_001 | Account details first; full brand in a lower contact panel; `QSP` footer logo, unlike dev bill_003's logo/name header | Quillstone Sample Power |
| holdout_002 | Centred `QVX` heading; amount before charges; no expanded brand printed | QVX |
| holdout_003 | Brand heading; separate service panel says `Your distributor: Glass Orchard Sample Networks` | Vellum Kite Sample Energy |
| holdout_004 | Prominent coloured brand banner; fine print says `Issued by Mosaic Finch Sample Retail Pty Ltd` with `ABN 00 000 000 000` | Mosaic Finch Sample Power |
| holdout_005 | Serif invoice; only `Issued by Parchment Vale Sample Retail Pty Ltd`, followed by placeholder ABN; no separate brand | Parchment Vale Sample Retail Pty Ltd |
| holdout_006 | Brand heading, charges before period, group affiliation at bottom: `Cobalt Loom Sample Group` | Copper Wren Sample Electricity |

ABN labels/numbers are metadata, not part of the legal-entity name. A longer
network/group/legal name must not replace a printed retailer brand. No name
from this set is included in the prompt or outbound schema.

## Seven-field labels and arithmetic

Each case has `bill.pdf` and a separately authored `expected.json`. Dates are
inclusive and explicitly printed as ISO dates. All rates/charges are GST
inclusive, and every supply rate is printed in AUD/day. Each has a printed
usage total, billing-day count and current bill amount. Amount due equals the
current bill amount; there are no credits, balances, ambiguous dates or new
non-retailer traps. All six expect `processed` and an empty flag list.

| Case | Start | End | Days | Usage kWh | Supply AUD/day | Current AUD | Printed charge reconciliation |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| holdout_001 | 2026-01-01 | 2026-01-31 | 31 | 180 | 1.05 | 90.15 | 180 x 0.32 = 57.60; 31 x 1.05 = 32.55 |
| holdout_002 | 2026-02-01 | 2026-02-28 | 28 | 210 | 0.96 | 87.78 | 210 x 0.29 = 60.90; 28 x 0.96 = 26.88 |
| holdout_003 | 2026-03-01 | 2026-03-31 | 31 | 275 | 1.10 | 119.35 | 275 x 0.31 = 85.25; 31 x 1.10 = 34.10 |
| holdout_004 | 2026-04-01 | 2026-04-30 | 30 | 160 | 1.02 | 86.60 | 160 x 0.35 = 56.00; 30 x 1.02 = 30.60 |
| holdout_005 | 2026-05-01 | 2026-05-31 | 31 | 240 | 0.99 | 97.89 | 240 x 0.28 = 67.20; 31 x 0.99 = 30.69 |
| holdout_006 | 2026-06-01 | 2026-06-30 | 30 | 195 | 1.08 | 96.75 | 195 x 0.33 = 64.35; 30 x 1.08 = 32.40 |

Displayed line charges use Decimal, rounded to cents with ROUND_HALF_UP. Tests
read quantities, rates, charges, dates and totals from actual PDF text, not
generator inputs. Flags/status are independently written answers, checked with
production derivation functions. The generator never reads or writes labels.

## Rebuild and check offline

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_holdout
.\.venv\Scripts\python.exe -m pytest tests/test_holdout.py -q
.\.venv\Scripts\python.exe -m evals.run --extractor fake --dataset dataset/holdout --repeats 3
```

The generator also accepts `--output <directory>` for regeneration checks.
The default eval dataset remains the five dev cases: discovery is not recursive.
Both extractor modes use the same loader; OpenAI mode still requires explicit
owner authorisation and the two live environment gates. Dataset names appear in
summary/report headers; input hashes remain the authoritative identity.
Comparing a dev run with a holdout run is rejected because their manifests differ.

## Owner verification (merge blocker)

Check the PDF visually against all seven labelled fields, supply unit/GST basis,
expected flags and status. Do not approve on passing tests alone. Record reviewer
and date after verification; later PDF/label edits invalidate the affected review.

- [x] Owner (maxtsec), 2026-09-29: holdout_001 all seven fields, supply unit/GST basis, flags and status match the PDF.
- [ ] Owner verifies holdout_002: all fields, flags and status.
- [ ] Owner verifies holdout_003: all fields, flags and status.
- [ ] Owner verifies holdout_004: all fields, flags and status.
- [ ] Owner verifies holdout_005: all fields, flags and status.
- [ ] Owner verifies holdout_006: all fields, flags and status.
