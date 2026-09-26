# Milestone 0 golden dataset plan

This is the design for five **synthetic** Victorian household electricity bills. No PDF or `expected.json` is ground truth until the PDF exists and a person has checked every label against it. The five cases are deliberately small; they test distinct interpretation failures rather than trying to represent every retailer or tariff.

Each finished case will have this structure:

```text
dataset/bill_001/bill.pdf
dataset/bill_001/expected.json
```

Repeat through `bill_005`. Use the seven fields and JSON shape in [`docs/extraction-contract.md`](../docs/extraction-contract.md). Do not put a real person's name, address, account number, meter identifier, or contact details in any PDF. Mark each PDF as a synthetic sample that is not payable. Use fictional retailer names and clearly artificial account references such as `TEST-001`.

## Shared conventions

- Dates are inclusive. All five PDFs explicitly state the imported usage total and one daily supply rate, so the initial contract can represent them without asking an LLM to add tariff lines. `bill_003` prints dates as `DD/MM/YYYY`, including `05/06/2026`.
- Clearly label whether each printed rate includes GST. Four cases use GST-inclusive rates; `bill_002` uses GST-exclusive rates. Show the current-period total separately from any account balance or amount due **except** in `bill_002`, where its absence is the test.
- Calculate line charges with decimal arithmetic and round displayed line amounts to cents. Where a current bill amount is displayed, it is the sum of the displayed current-period line amounts. `bill_002` deliberately omits that total. Keep printed rate precision; do not replace `110.23 cents/day` with a rounded AUD figure on the PDF.
- `expected.json` records the value supported by the PDF, plus `expected_status` and `expected_flags`. It must never be populated from an extractor's answer. A source inconsistency remains in the label and has a matching flag.
- Vary column order, typography, headings, and where totals appear. Do not make five copies of one bill template with different numbers.

## Five cases

| Case | Layout and question tested | Period and printed days | Imported usage | Supply rate | Expected current bill amount |
| --- | --- | --- | ---: | ---: | ---: |
| `bill_001` | Simple, one-column single rate; basic extraction and cents/day conversion | 2026-04-01 to 2026-04-30; 30 days | 250 kWh | 110.23 cents/day | AUD 108.07 |
| `bill_002` | Prominent **amount due**, no stated current total, GST-exclusive rate | 2026-05-01 to 2026-05-31; 31 days | 320 kWh | 1.00 AUD/day, ex GST | `null` |
| `bill_003` | Time-of-use table, Australian date format, and distinct current total versus amount due | 2026-06-05 to 2026-07-04; 30 days | 300 kWh | 98 cents/day | AUD 113.40 |
| `bill_004` | Solar/export section; do not net exported kWh against imports or lose a credit amount | 2026-11-01 to 2026-11-30; 30 days | 100 kWh | 1.00 AUD/day | AUD -4.00 |
| `bill_005` | Awkward two-column reading order, zero usage, and a printed day count that disagrees with dates | 2026-08-01 to 2026-08-31; **30 days printed** | 0 kWh | 95 cents/day | AUD 29.45 |

### `bill_001`: straightforward single rate

Retailer: **Example Energy**. Show 250 kWh at AUD 0.30/kWh = AUD 75.00 and 30 days at **110.23 c/day, GST inclusive** = AUD 33.07 after line rounding. Current bill amount and amount due are both AUD 108.07. Put the period, usage total, rate, and current amount near clear headings. The expected rate unit is `cents/day` and basis is `inclusive`; status is `processed` with no flags.

### `bill_002`: account balance trap

Retailer: **Harbour Sample Power**. Print usage at **AUD 0.28/kWh, ex GST**: 320 kWh = AUD 89.60. Print supply at **$1.00/day, ex GST**: 31 days = AUD 31.00. Print a GST line of AUD 12.06, a previous balance of AUD 40.00, and an already received payment of AUD 10.00. The prominently displayed amount due is **AUD 162.66**. Do **not** print a current-period subtotal or total; the designer can reconcile it as AUD 132.66, but the initial extraction contract does not ask the model to calculate an unstated amount. The expected `current_bill_amount` is `null`, `expected_status` is `needs_review`, and `expected_flags` contains `current_bill_amount_missing`. The expected supply rate is `{"value":"1.00","unit":"AUD/day","gst_basis":"exclusive"}`.

The synthetic GST line is 10% of the AUD 120.60 pre-GST charges, consistent with the [Australian Taxation Office's GST ruling](https://www.ato.gov.au/law/view/document?LocID=%22GST%2FGSTR20018%2FNAT%2FATO%2Fft50%22&PiT=20251112000001). The printed GST line is source data; the LLM must not be asked to calculate it.

### `bill_003`: time of use

Retailer: **Lantern Sample Electricity**. Print the period as `05/06/2026–04/07/2026` with an explicit `DD/MM/YYYY` heading. Use a table with peak 120 kWh at AUD 0.40/kWh = AUD 48.00 and off-peak 180 kWh at AUD 0.20/kWh = AUD 36.00. Print **total imported usage: 300 kWh** outside or below the table. Supply is 30 days at **98 c per day, GST inclusive** = AUD 29.40. Print **current bill amount AUD 113.40** and, separately, a previous unpaid balance of AUD 50.00 and **amount due AUD 163.40**. The expected `current_bill_amount` remains `"113.40"`; choosing amount due would be a field error. The initial contract records only the 300 kWh total, not the tariff rows. Expected status is `processed` with no flags.

### `bill_004`: solar export and net credit

Retailer: **Mallee Sample Energy**. Show imported usage of 100 kWh at AUD 0.30/kWh = AUD 30.00, supply of 30 days at **AUD 1.00/day, GST inclusive** = AUD 30.00, and **exported** energy of 800 kWh at AUD 0.08/kWh = AUD 64.00 credit. Current bill amount is **AUD -4.00**; display it on the PDF as `AUD 4.00 CR`. Print the imported and exported kWh in separate labelled sections. The expected `total_usage_kwh` is `"100"`, not `"-700"` or `"900"`; the expected amount is `"-4.00"`. Expected status is `processed` with no flags.

### `bill_005`: awkward layout and source disagreement

Retailer: **Bluegum Sample Electric**. Put the account summary and charge details in separate columns with a reading order that may be awkward for plain text extraction. Show 0 kWh imported, 31 days at **95¢/day, GST inclusive** = AUD 29.45, and current bill amount AUD 29.45. Print the period as 1–31 August 2026 but state **30 billing days** elsewhere. The expected `stated_billing_days` is `30`; Python computes `billing_days` as `31`. Expected status is `needs_review` with `stated_days_mismatch`. Do not silently fix the PDF or the label.

## Labelling and release checks

For each case, manually compare all seven values in `expected.json` with the finished PDF. Check `gst_basis`, `expected_status`, and `expected_flags` too. Parse every JSON file, check required keys and units against the contract, and reconcile displayed charge lines with `Decimal`; for `bill_002`, reconcile the amount due without copying an unstated current-period subtotal into the label. Verify that the PDFs contain no genuine personal information. Have the project owner independently re-read at least `bill_002` and `bill_005` after another agent creates them, so the PDF author is not the only label checker. Record deliberate contradictions, such as the day count in `bill_005`, here so later evaluation does not mistake them for labelling errors.

When the PDFs and labels exist, automate JSON parsing, schema and flag checks, including sorted, unique flags and `expected_status == derive(expected_flags)`, and decimal reconciliations with pytest. Inspect the PDFs' extracted text with the chosen baseline before calling an LLM. That inspection will show whether the intended layout differences survive PDF text extraction. These five synthetic cases are a starting benchmark, not evidence of real-world accuracy. They do not yet test a bill that leaves the supply rate's GST basis unstated; measure how often that occurs before changing the review policy.
