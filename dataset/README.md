# Milestone 0 golden dataset plan

This is the design for five **synthetic** Victorian household electricity bills. No PDF or `expected.json` is ground truth until the PDF exists and a person has checked every label against it. The five cases are deliberately small; they test distinct interpretation failures rather than trying to represent every retailer or tariff.

Each finished case will have this structure:

```text
dataset/bill_001/bill.pdf
dataset/bill_001/expected.json
```

Repeat through `bill_005`. Use the seven fields and JSON shape in [`docs/extraction-contract.md`](../docs/extraction-contract.md). Do not put a real person's name, address, account number, meter identifier, or contact details in any PDF. Mark each PDF as a synthetic sample that is not payable. Use fictional retailer names and clearly artificial account references such as `TEST-001`.

## Shared conventions

- Dates are inclusive. All five PDFs explicitly state the imported usage total and one daily supply rate, so the initial contract can represent them without asking an LLM to add tariff lines.
- Printed unit prices are GST inclusive. Show the current-period total separately from any account balance or amount due.
- Calculate line charges with decimal arithmetic and round displayed line amounts to cents. The displayed current bill amount is the sum of those displayed line amounts. Keep printed rate precision; do not replace `110.23 cents/day` with a rounded AUD figure on the PDF.
- `expected.json` records the value supported by the PDF, including a source inconsistency. It must never be populated from an extractor's answer.
- Vary column order, typography, headings, and where totals appear. Do not make five copies of one bill template with different numbers.

## Five cases

| Case | Layout and question tested | Period and printed days | Imported usage | Supply rate | Current bill amount |
| --- | --- | --- | ---: | ---: | ---: |
| `bill_001` | Simple, one-column single rate; basic extraction and cents/day conversion | 2026-04-01 to 2026-04-30; 30 days | 250 kWh | 110.23 cents/day | AUD 108.07 |
| `bill_002` | Single rate with a prominent **amount due** that differs from current charges | 2026-05-01 to 2026-05-31; 31 days | 320 kWh | 1.05 AUD/day | AUD 122.15 |
| `bill_003` | Time-of-use table; distinguish the printed import total from peak and off-peak rows | 2026-06-01 to 2026-06-30; 30 days | 300 kWh | 98 cents/day | AUD 113.40 |
| `bill_004` | Solar/export section; do not net exported kWh against imports or lose a credit amount | 2026-11-01 to 2026-11-30; 30 days | 100 kWh | 1.00 AUD/day | AUD -4.00 |
| `bill_005` | Awkward two-column reading order, zero usage, and a printed day count that disagrees with dates | 2026-08-01 to 2026-08-31; **30 days printed** | 0 kWh | 95 cents/day | AUD 29.45 |

### `bill_001`: straightforward single rate

Retailer: **Example Energy**. Show 250 kWh at AUD 0.30/kWh = AUD 75.00 and 30 days at 110.23 cents/day = AUD 33.07 after line rounding. Current bill amount and amount due are both AUD 108.07. Put the period, usage total, rate, and current amount near clear headings.

### `bill_002`: account balance trap

Retailer: **Harbour Sample Power**. Show 320 kWh at AUD 0.28/kWh = AUD 89.60 and 31 days at AUD 1.05/day = AUD 32.55. Current bill amount is AUD 122.15. Add a previous balance of AUD 40.00 and an already received payment of AUD 10.00, so the prominently displayed amount due is **AUD 152.15**. The expected `current_bill_amount` remains `"122.15"`.

### `bill_003`: time of use

Retailer: **Lantern Sample Electricity**. Use a table with peak 120 kWh at AUD 0.40/kWh = AUD 48.00 and off-peak 180 kWh at AUD 0.20/kWh = AUD 36.00. Print **total imported usage: 300 kWh** outside or below the table. Supply is 30 days at 98 cents/day = AUD 29.40. Current bill amount is AUD 113.40. The initial contract records only the 300 kWh total, not the tariff rows.

### `bill_004`: solar export and net credit

Retailer: **Mallee Sample Energy**. Show imported usage of 100 kWh at AUD 0.30/kWh = AUD 30.00, supply of 30 days at AUD 1.00/day = AUD 30.00, and **exported** energy of 800 kWh at AUD 0.08/kWh = AUD 64.00 credit. Current bill amount is **AUD -4.00**, which the PDF may display as `AUD 4.00 CR`. Print the imported and exported kWh in separate labelled sections. The expected `total_usage_kwh` is `"100"`, not `"-700"` or `"900"`.

### `bill_005`: awkward layout and source disagreement

Retailer: **Bluegum Sample Electric**. Put the account summary and charge details in separate columns with a reading order that may be awkward for plain text extraction. Show 0 kWh imported, 31 days at 95 cents/day = AUD 29.45, and current bill amount AUD 29.45. Print the period as 1–31 August 2026 but state **30 billing days** elsewhere. The expected `stated_billing_days` is `30`; Python computes `billing_days` as `31` and raises a review warning. Do not silently fix the PDF or the label.

## Labelling and release checks

For each case, manually compare all seven values in `expected.json` with the finished PDF. Parse every JSON file, check required keys and units against the contract, and reconcile the displayed charge lines with the current amount using `Decimal`. Verify that the PDFs contain no genuine personal information. Record any deliberate contradiction, such as the day count in `bill_005`, in this README so later evaluation does not mistake it for a labelling error.

When the PDFs exist, inspect their extracted text with the chosen baseline before calling an LLM. That inspection will show whether the intended layout differences survive PDF text extraction.
