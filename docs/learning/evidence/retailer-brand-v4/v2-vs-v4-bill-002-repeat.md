# Compare 20260928T232541Z-2b18b62e60bf -> 20260928T232646Z-90f79aa5b450

Synthetic bills only; descriptive results, not evidence of real-world accuracy or statistical significance.
Dataset names: A=legacy (name not recorded); B=bill_002_only
Dataset: 1 bills; repeats: 20 each.

| Run | Provider | Requested model | Resolved models | Configured prompt | Observed prompts | Effort | Code commit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | openai | gpt-5.4-mini | gpt-5.4-mini-2026-03-17 | extract-v2 | extract-v2 | low | 1ecad8057dd29695d5ceca23722c0b959607dd21 |
| B | openai | gpt-5.4-mini | gpt-5.4-mini-2026-03-17 | extract-v4 | extract-v4 | low | 424c0493740f14d03fd71ec6c8d20e5ce1b5a819 |

Changed dimensions: prompt version, commit.

WARNING: multiple configuration dimensions differ; score changes cannot be attributed to a single variable.

## Per-field correctness

| Field | A | B | Change | Other outcome counts A -> B |
| --- | --- | --- | --- | --- |
| retailer | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| period_start | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| period_end | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| stated_billing_days | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| total_usage_kwh | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| daily_supply_rate | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| current_bill_amount | 20/20 | 18/20 | regressed | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 2/20; no_fields: 0/20 -> 0/20 |

## Per-bill changes

Change describes correctness only; outcome counts can change even when correctness is unchanged.
Counts compare distributions across repeats, not paired attempt transitions.

| Bill | Metric | A | B | Change | Other outcome counts A -> B |
| --- | --- | --- | --- | --- | --- |
| bill_002 | exact_bill_match | 20/20 | 18/20 | regressed | — |
| bill_002 | flags_match | 20/20 | 18/20 | regressed | — |
| bill_002 | status_match | 20/20 | 18/20 | regressed | — |
| bill_002 | retailer | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| bill_002 | period_start | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| bill_002 | period_end | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| bill_002 | stated_billing_days | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| bill_002 | total_usage_kwh | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| bill_002 | daily_supply_rate | 20/20 | 20/20 | unchanged | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 0/20; no_fields: 0/20 -> 0/20 |
| bill_002 | current_bill_amount | 20/20 | 18/20 | regressed | wrong_value: 0/20 -> 0/20; missing: 0/20 -> 0/20; false_extraction: 0/20 -> 2/20; no_fields: 0/20 -> 0/20 |
