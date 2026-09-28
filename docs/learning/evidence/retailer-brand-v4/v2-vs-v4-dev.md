# Compare 20260928T212834Z-11548f32c4b3 -> 20260928T224629Z-d833f7fb2248

Synthetic bills only; descriptive results, not evidence of real-world accuracy or statistical significance.
Dataset names: A=legacy (name not recorded); B=dataset
Dataset: 5 bills; repeats: 3 each.

| Run | Provider | Requested model | Resolved models | Configured prompt | Observed prompts | Effort | Code commit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | openai | gpt-5.4-mini | gpt-5.4-mini-2026-03-17 | extract-v2 | extract-v2 | low | 1ecad8057dd29695d5ceca23722c0b959607dd21 |
| B | openai | gpt-5.4-mini | gpt-5.4-mini-2026-03-17 | extract-v4 | extract-v4 | low | b1fdef0009504c44e19b13d9f957e2143d3447b6 |

Changed dimensions: prompt version, commit.

WARNING: multiple configuration dimensions differ; score changes cannot be attributed to a single variable.

## Per-field correctness

| Field | A | B | Change | Other outcome counts A -> B |
| --- | --- | --- | --- | --- |
| retailer | 12/15 | 15/15 | improved | wrong_value: 2/15 -> 0/15; missing: 1/15 -> 0/15; false_extraction: 0/15 -> 0/15; no_fields: 0/15 -> 0/15 |
| period_start | 15/15 | 15/15 | unchanged | wrong_value: 0/15 -> 0/15; missing: 0/15 -> 0/15; false_extraction: 0/15 -> 0/15; no_fields: 0/15 -> 0/15 |
| period_end | 15/15 | 15/15 | unchanged | wrong_value: 0/15 -> 0/15; missing: 0/15 -> 0/15; false_extraction: 0/15 -> 0/15; no_fields: 0/15 -> 0/15 |
| stated_billing_days | 15/15 | 15/15 | unchanged | wrong_value: 0/15 -> 0/15; missing: 0/15 -> 0/15; false_extraction: 0/15 -> 0/15; no_fields: 0/15 -> 0/15 |
| total_usage_kwh | 15/15 | 15/15 | unchanged | wrong_value: 0/15 -> 0/15; missing: 0/15 -> 0/15; false_extraction: 0/15 -> 0/15; no_fields: 0/15 -> 0/15 |
| daily_supply_rate | 15/15 | 15/15 | unchanged | wrong_value: 0/15 -> 0/15; missing: 0/15 -> 0/15; false_extraction: 0/15 -> 0/15; no_fields: 0/15 -> 0/15 |
| current_bill_amount | 15/15 | 14/15 | regressed | wrong_value: 0/15 -> 0/15; missing: 0/15 -> 0/15; false_extraction: 0/15 -> 1/15; no_fields: 0/15 -> 0/15 |

## Per-bill changes

Change describes correctness only; outcome counts can change even when correctness is unchanged.
Counts compare distributions across repeats, not paired attempt transitions.

| Bill | Metric | A | B | Change | Other outcome counts A -> B |
| --- | --- | --- | --- | --- | --- |
| bill_001 | exact_bill_match | 3/3 | 3/3 | unchanged | — |
| bill_001 | flags_match | 3/3 | 3/3 | unchanged | — |
| bill_001 | status_match | 3/3 | 3/3 | unchanged | — |
| bill_001 | retailer | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_001 | period_start | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_001 | period_end | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_001 | stated_billing_days | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_001 | total_usage_kwh | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_001 | daily_supply_rate | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_001 | current_bill_amount | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_002 | exact_bill_match | 2/3 | 2/3 | unchanged | — |
| bill_002 | flags_match | 2/3 | 2/3 | unchanged | — |
| bill_002 | status_match | 3/3 | 2/3 | regressed | — |
| bill_002 | retailer | 2/3 | 3/3 | improved | wrong_value: 0/3 -> 0/3; missing: 1/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_002 | period_start | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_002 | period_end | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_002 | stated_billing_days | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_002 | total_usage_kwh | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_002 | daily_supply_rate | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_002 | current_bill_amount | 3/3 | 2/3 | regressed | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 1/3; no_fields: 0/3 -> 0/3 |
| bill_003 | exact_bill_match | 1/3 | 3/3 | improved | — |
| bill_003 | flags_match | 3/3 | 3/3 | unchanged | — |
| bill_003 | status_match | 3/3 | 3/3 | unchanged | — |
| bill_003 | retailer | 1/3 | 3/3 | improved | wrong_value: 2/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_003 | period_start | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_003 | period_end | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_003 | stated_billing_days | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_003 | total_usage_kwh | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_003 | daily_supply_rate | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_003 | current_bill_amount | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_004 | exact_bill_match | 3/3 | 3/3 | unchanged | — |
| bill_004 | flags_match | 3/3 | 3/3 | unchanged | — |
| bill_004 | status_match | 3/3 | 3/3 | unchanged | — |
| bill_004 | retailer | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_004 | period_start | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_004 | period_end | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_004 | stated_billing_days | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_004 | total_usage_kwh | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_004 | daily_supply_rate | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_004 | current_bill_amount | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_005 | exact_bill_match | 3/3 | 3/3 | unchanged | — |
| bill_005 | flags_match | 3/3 | 3/3 | unchanged | — |
| bill_005 | status_match | 3/3 | 3/3 | unchanged | — |
| bill_005 | retailer | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_005 | period_start | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_005 | period_end | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_005 | stated_billing_days | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_005 | total_usage_kwh | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_005 | daily_supply_rate | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
| bill_005 | current_bill_amount | 3/3 | 3/3 | unchanged | wrong_value: 0/3 -> 0/3; missing: 0/3 -> 0/3; false_extraction: 0/3 -> 0/3; no_fields: 0/3 -> 0/3 |
