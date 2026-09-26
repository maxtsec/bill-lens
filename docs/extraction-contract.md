# Bill Lens extraction contract (Milestone 0)

This document defines the initial fields extracted from a Victorian household electricity bill. Extracted values must reflect the bill's content. Derived values, unit conversion, and consistency checks belong in deterministic Python code. The contract deliberately does not represent individual tariff lines yet.

## Retailer

`retailer` is the electricity retailer named on the bill, as displayed to the customer. Preserve its displayed name; do not replace it with a parent company, distributor, or a guessed canonical name. A missing or ambiguous retailer is `null` and needs review.

## Billing period

`period_start` and `period_end` are the first and last calendar dates of the electricity service period shown on the bill. Both dates are **inclusive**. Store them in ISO 8601 date form (`YYYY-MM-DD`), without a time of day or timezone.

`stated_billing_days` is the number of billing days explicitly printed on the bill. It is `null` when the bill does not state a number. It is an extracted field, not a value calculated by the model.

Python calculates `billing_days` from the dates:

```python
billing_days = (period_end - period_start).days + 1
```

For example, 1 April through 30 April is 30 days. If `period_end` is before `period_start`, the period needs review. If `stated_billing_days` differs from `billing_days`, retain both values and raise a review warning; do not silently change either one. The difference could be an extraction error, an unusual billing convention, or a mistake on the source bill.

## Total usage

`total_usage_kwh` is the total **grid electricity imported and consumed** during the billing period, in kilowatt-hours (kWh). It is nonnegative and may be zero. For a time-of-use bill, this is the total across usage tariff categories such as peak and off-peak. Do not subtract solar exports or include exported kWh as consumption.

For this first contract, extract a clearly stated total rather than asking the model to add tariff lines. If no unambiguous import total is printed, return `null` and require review. The five initial synthetic bills will each state an import total. This flattened field cannot explain which tariff category drove a change; a later contract may add `usage_lines` when that analysis is needed.

Represent usage as a decimal string in JSON, such as `"320.5"`, preserving the precision printed on the bill.

## Daily supply rate

`daily_supply_rate` is the unit price of the daily supply charge, **not** the total supply charge for the period. Extract its printed decimal value and unit separately:

```json
{ "value": "110.23", "unit": "cents/day" }
```

The initial recognised units are `cents/day` and `AUD/day`. Python converts the extracted value to canonical **AUD/day** with `Decimal`: divide a `cents/day` value by 100; leave an `AUD/day` value unchanged. For example, `110.23 cents/day` becomes `1.1023 AUD/day`. Do not round during conversion.

The first dataset will label rates as GST inclusive. The contract does not yet normalise GST basis across bills. If a bill has multiple supply rates, an unclear unit, or an unclear GST basis, return `null` and require review rather than selecting one arbitrarily. A daily supply rate must be nonnegative.

## Current bill amount

`current_bill_amount` is the net amount charged for **this billing period**, in Australian dollars (AUD). It includes current-period usage and supply charges, applicable current-period fees and adjustments, discounts already applied, solar feed-in credits, and GST. Preserve the sign: a net credit can make the value negative.

It excludes previous balances and payments against the account. It is therefore distinct from `amount due`, which is the account balance requested for payment and may combine the current bill with earlier balances, payments, or credits. A conditional discount that has not yet been applied is not part of `current_bill_amount`.

Extract the current-period amount stated on the bill when it can be identified. Do not ask the model to calculate it from line items. If the bill shows only an amount due and the current-period amount cannot be identified confidently, return `null` for `current_bill_amount` and flag the bill for review rather than copying the amount due.

Represent monetary values as decimal strings in JSON, such as `"105.00"`; parse them with Python `Decimal`, not binary floating point.

### Worked example

Assume current-period charges including GST are AUD 120.00, the current-period solar feed-in credit is AUD 15.00, a previous balance is AUD 40.00, and a payment of AUD 10.00 has been received. With no other adjustments:

```text
current_bill_amount = 120.00 - 15.00 = AUD 105.00
amount_due          = 105.00 + 40.00 - 10.00 = AUD 135.00
```

`amount_due` is shown here only to make the distinction clear; it is not part of the initial extraction contract.

## JSON shape and review rules

Every extraction attempt returns all seven keys under `fields`. Use `null` for a value that is missing or cannot be identified confidently; do not omit its key or invent a value. `stated_billing_days` is optional by nature. Missing values for the other fields need review. The example below also shows the shape of a manually labelled `expected.json`; labels must be checked against the synthetic PDF by a human.

```json
{
  "schema_version": 1,
  "fields": {
    "retailer": "Example Energy",
    "period_start": "2026-04-01",
    "period_end": "2026-04-30",
    "stated_billing_days": 30,
    "total_usage_kwh": "320.5",
    "daily_supply_rate": {
      "value": "110.23",
      "unit": "cents/day"
    },
    "current_bill_amount": "105.00"
  }
}
```

`schema_version` versions the dataset format; it is not an extracted bill field. `billing_days` and the normalised supply rate are derived values, so they do not appear under `fields`.
