# Bill Lens extraction contract (Milestone 0)

This document defines the initial fields extracted from a Victorian household electricity bill. Extracted values must reflect the bill's content. Derived values, unit conversion, and consistency checks belong in deterministic Python code. The contract deliberately does not represent individual tariff lines yet.

## Retailer

`retailer` is the electricity retailer named on the bill, as displayed to the customer. Preserve its displayed name; do not replace it with a parent company, distributor, or a guessed canonical name. A missing or ambiguous retailer is `null` and needs review.

A retailer name must not contain Unicode control characters (category `Cc`,
including NUL, tab, newline, DEL and C1 controls) or surrogate code points
(category `Cs`). Such output fails schema validation and becomes `invalid_output`;
do not strip the characters or change the value to null to manufacture a success.
Ordinary Unicode names, accents, emoji and non-control spaces remain valid.
A literal backslash sequence such as `\\u0000` in a decoded name is distinct from
an actual NUL. The raw model response is retained unchanged as evidence, including
when its characters are unsuitable for PostgreSQL text; see
[ADR-004](adr/004-lossless-raw-response.md).

For evaluation, trim and collapse whitespace and compare without case sensitivity. Do not remove words or legal suffixes: `Example Energy` and `EXAMPLE ENERGY` match, but `Example Energy` and `Example Energy Pty Ltd` do not. A future retailer registry could support alias matching, but the first dataset will not guess aliases.

## Billing period

`period_start` and `period_end` are the first and last calendar dates of the electricity service period shown on the bill. Both dates are **inclusive**. Store them in ISO 8601 date form (`YYYY-MM-DD`), without a time of day or timezone.

Australian-style printed dates such as `05/06/2026` must be interpreted using the bill's stated date format or other unambiguous context, not a default US month/day assumption. If the order cannot be resolved, return `null` for the uncertain date and require review.

`stated_billing_days` is the day count explicitly labelled as applying to the **billing period**, for example `Billing days` or `Days in period` in the account summary. Quantities on charge lines, including the number of days used to calculate a supply charge, are excluded. If no unambiguous period-level count is printed, return `null`, even when a supply line states a number of days. It is an extracted field, not a value calculated by the model; never select a number because it agrees with the dates.

For example, `bill_005` prints `Billing days: 30` in its account summary and `Supply: 31 days at 95¢/day` in the charge details. Extract `stated_billing_days: 30`. The 31 is a charge-line quantity and cannot replace the summary's stated count. Python separately derives 31 from the period dates and emits `stated_days_mismatch`.

Python calculates `billing_days` from the dates:

```python
billing_days = (period_end - period_start).days + 1
```

For example, 1 April through 30 April is 30 days. If `period_end` is before `period_start`, emit `period_end_before_start` and do not calculate or compare billing days. Otherwise, if `stated_billing_days` differs from `billing_days`, retain both values and emit `stated_days_mismatch`; do not silently change either one. The difference could be an extraction error, an unusual billing convention, or a mistake on the source bill.

## Total usage

`total_usage_kwh` is the total **grid electricity imported and consumed** during the billing period, in kilowatt-hours (kWh). It is nonnegative and may be zero. For a time-of-use bill, this is the total across usage tariff categories such as peak and off-peak. Do not subtract solar exports or include exported kWh as consumption.

For this first contract, extract a clearly stated total rather than asking the model to add tariff lines. If no unambiguous import total is printed, return `null` and require review. The five initial synthetic bills will each state an import total. This flattened field cannot explain which tariff category drove a change; a later contract may add `usage_lines` when that analysis is needed.

Represent usage as a decimal string in JSON, such as `"320.5"`, preserving the precision printed on the bill.

## Daily supply rate

`daily_supply_rate` is the unit price of the daily supply charge, **not** the total supply charge for the period. Extract its printed decimal value and unit separately:

```json
{ "value": "110.23", "unit": "cents/day", "gst_basis": "inclusive" }
```

The model maps printed expressions such as `c/day`, `c per day`, and `¢/day` to the `cents/day` enum; `$/day` and `AUD/day` map to `AUD/day` when the bill's currency is clearly Australian dollars. Python validates the enum and converts the extracted value to canonical **AUD/day** with `Decimal`: divide a `cents/day` value by 100; leave an `AUD/day` value unchanged. For example, `110.23 cents/day` becomes `1.1023 AUD/day`. Do not round during conversion.

`gst_basis` is `inclusive`, `exclusive`, or `unknown`, according to what the bill says about the **printed rate**. The model identifies this label from the document; it must not assume `inclusive` when the bill is silent. An `unknown` basis keeps a readable rate while raising the `supply_rate_gst_basis_unknown` review flag. Python's unit conversion does **not** change GST basis. Do not compare rates with different or unknown bases as equivalent; tax-basis normalisation is outside M0.

If a bill has multiple supply rates with no single representative rate, or the printed rate's unit cannot be identified, set `daily_supply_rate` to `null` and require review rather than selecting one arbitrarily. A daily supply rate must be nonnegative.

## Current bill amount

`current_bill_amount` is the net amount charged for **this billing period**, in Australian dollars (AUD). It includes current-period usage and supply charges, applicable current-period fees and adjustments, discounts already applied, solar feed-in credits, and GST. Preserve the sign: a net credit can make the value negative.

It excludes previous balances and payments against the account. It is therefore distinct from `amount due`, which is the account balance requested for payment and may combine the current bill with earlier balances, payments, or credits. Include a discount if the bill has already applied it to the stated current-period total. Exclude a possible future or conditional discount that has not yet been applied. If two alternative totals make that unclear, return `null` and require review.

Extract the current-period amount stated on the bill when it can be identified. Do not ask the model to calculate it from line items. If the bill shows only an amount due and the current-period amount cannot be identified confidently, return `null` for `current_bill_amount` and flag the bill for review rather than copying the amount due.

Represent monetary values as decimal strings in JSON, such as `"105.00"`; parse them with Python `Decimal`, not binary floating point.

When the bill explicitly marks the current-period total as a credit, for example `AUD 4.00 CR`, the extracted signed value is `"-4.00"`. Recognising that `CR` is attached to the current-period total is document interpretation; Python can then validate the signed decimal value. Do not treat an account credit from an earlier period as a negative current bill.

### Worked example

Assume current-period charges including GST are AUD 120.00, the current-period solar feed-in credit is AUD 15.00, a previous balance is AUD 40.00, and a payment of AUD 10.00 has been received. With no other adjustments:

```text
current_bill_amount = 120.00 - 15.00 = AUD 105.00
amount_due          = 105.00 + 40.00 - 10.00 = AUD 135.00
```

`amount_due` is shown here only to make the distinction clear; it is not part of the initial extraction contract.

## JSON shape and review rules

Every extraction attempt returns all seven keys under `fields`. Use `null` for a value that is missing or cannot be identified confidently; do not omit its key or invent a value. `stated_billing_days` is optional by nature. Missing values for the other fields need review. An `expected.json` label also records the expected processing status and warning codes, checked against the synthetic PDF by a human. These label-only keys are not fields returned by the LLM.

```json
{
  "schema_version": 1,
  "fields": {
    "retailer": "Example Energy",
    "period_start": "2026-04-01",
    "period_end": "2026-04-30",
    "stated_billing_days": 30,
    "total_usage_kwh": "250",
    "daily_supply_rate": {
      "value": "110.23",
      "unit": "cents/day",
      "gst_basis": "inclusive"
    },
    "current_bill_amount": "108.07"
  },
  "expected_status": "processed",
  "expected_flags": []
}
```

`schema_version` versions the dataset format; it is not an extracted bill field. `billing_days` and the normalised supply rate are derived values, so they do not appear under `fields`. For M0, `expected_status` is `processed` when there are no review flags and `needs_review` when there is at least one. It is derived from `expected_flags`, so a label check must reject a contradictory status. Operational failures such as unreadable PDFs will use `failed` in a later milestone.

The human labeler records `expected_flags` from the PDF and these contract rules **independently of the application validator**. A later test must check `derive_flags(label.fields) == set(label.expected_flags)` and `label.expected_status == derive_status(label.expected_flags)`. Do not generate the label's expected flags by calling the same `derive_flags` implementation under test: that would let a flag-logic bug write its own expected answer.

For `bill_002`, the same shape has `"current_bill_amount": null`, `"expected_status": "needs_review"`, and `"expected_flags": ["current_bill_amount_missing"]`. The PDFs and candidate labels now exist; owner verification is recorded separately in the dataset README.

### Implemented schema boundary

`bill_lens/contract.py` validates the wire format with Pydantic. Decimal strings must be plain decimal notation (optional leading minus, digits, optional fractional digits); JSON numbers, currency symbols, whitespace, exponents, NaN and Infinity are rejected. Zero usage and negative current amounts remain valid. Dates must be exact `YYYY-MM-DD` strings representing real calendar dates. A stated day count must be a positive integer, or null. Blank retailer strings are rejected in favor of explicit null. Unknown keys and omitted keys are rejected, including in the supply-rate object; printed unit aliases must already have been mapped to the contract enums.

Schema errors raise `ValidationError`. Valid-shaped fields then enter `bill_lens/validation.py`, which retains source disagreements and returns review flags. Operational handling of malformed model responses belongs to M1. The normalized supply-rate function converts units only; callers must retain and compare the source `gst_basis` separately.

All seven extraction fields and all three supply-rate components include descriptions in the generated Pydantic JSON schema. Keep those descriptions consistent with this contract when changing field semantics: future structured model requests will use them as instructions. Their presence does not establish model accuracy or provider compatibility. The [M1 PDF text boundary](pdf-text-boundary.md) defines failures before a model is called.

The current `ISODate` input validator accepts wire-format strings only, including when called from Python; it rejects a preconstructed `date` object. Before M1 constructs these models from database or internal Python values, revisit this boundary or add an explicit conversion. The M0 JSON-label path does not require that change.

The initial fixed `expected_flags` codes are determined from the extracted fields, not from a hidden explanation of why the model returned `null`:

| Code | Condition |
| --- | --- |
| `current_bill_amount_missing` | `current_bill_amount` is `null`. |
| `daily_supply_rate_missing` | `daily_supply_rate` is `null`, whatever the source reason. |
| `period_end_before_start` | Both dates are known but in reverse order. |
| `period_end_missing` | `period_end` is `null`. |
| `period_start_missing` | `period_start` is `null`. |
| `retailer_missing` | `retailer` is `null`. |
| `stated_days_mismatch` | Both dates form a valid period and the printed day count differs from inclusive date calculation. |
| `supply_rate_gst_basis_unknown` | Rate and unit are known, but `gst_basis` is `unknown`. |
| `total_usage_kwh_missing` | `total_usage_kwh` is `null`. |

In particular, `daily_supply_rate_missing` does not say whether the bill omitted the rate, showed several rates, or used an unreadable unit. That reason is not available from the seven fields; do not infer it in Python. Extend the contract deliberately if that distinction later proves useful. `expected_flags` is a set of reason codes, written as a sorted array with no duplicates in JSON for stable diffs. A stated day count of `null` by itself does not produce a flag.

Evaluation should compare numeric fields as `Decimal`, not text strings. Compare supply rates after unit conversion to AUD/day **and** compare `gst_basis` separately; different GST bases are not equivalent. Report flag and status accuracy separately because they represent the review decision seen by a user, while recognising that those values are derived from extracted fields and their errors are therefore related. These rules define the intended checks; the evaluation harness is a later milestone.
