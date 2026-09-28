# Evaluation 20260928T212834Z-11548f32c4b3

Run: openai / requested gpt-5.4-mini / resolved gpt-5.4-mini-2026-03-17
Prompt: extract-v2; effort: low
Harness/scoring: 1/1; started: 2026-09-28T21:28:34.651939+00:00
Code: 1ecad8057dd29695d5ceca23722c0b959607dd21 (dirty=False)
Dataset: 5 synthetic bills @ 1ecad8057dd29695d5ceca23722c0b959607dd21; repeats: 3
Completed attempts: 15/15; complete=True; abort=None

Synthetic bills only; descriptive results, not evidence of real-world accuracy or statistical significance.

## Fields

| Field | correct | wrong_value | missing | false_extraction | no_fields |
| --- | --- | --- | --- | --- | --- |
| retailer | 12/15 | 2/15 | 1/15 | 0/15 | 0/15 |
| period_start | 15/15 | 0/15 | 0/15 | 0/15 | 0/15 |
| period_end | 15/15 | 0/15 | 0/15 | 0/15 | 0/15 |
| stated_billing_days | 15/15 | 0/15 | 0/15 | 0/15 | 0/15 |
| total_usage_kwh | 15/15 | 0/15 | 0/15 | 0/15 | 0/15 |
| daily_supply_rate | 15/15 | 0/15 | 0/15 | 0/15 | 0/15 |
| current_bill_amount | 15/15 | 0/15 | 0/15 | 0/15 | 0/15 |

Exact bill match: 12/15
Review decision: flags 14/15; status 15/15
Supply rate_value: 15/15 matched when both rates exist; 0/15 unavailable
Supply gst_basis: 15/15 matched when both rates exist; 0/15 unavailable
Attempt outcomes: none 15/15; rate_limited 0/15; timeout 0/15; refused 0/15; truncated 0/15; invalid_output 0/15; provider_error 0/15

## Per-bill correctness across repeats

Counts below use completed repeats; see planned/completed totals above.

| Bill | Exact | Flags | Status | retailer | period_start | period_end | stated_billing_days | total_usage_kwh | daily_supply_rate | current_bill_amount |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bill_001 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| bill_002 | 2/3 | 2/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| bill_003 | 1/3 | 3/3 | 3/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| bill_004 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| bill_005 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |

## Usage and latency

input_tokens: total=19233; known subtotal=19233; coverage=15/15
output_tokens: total=2832; known subtotal=2832; coverage=15/15
Latency ms: median=1617; max=2403
Estimated cost US$: 0.02716875; known subtotal=0.02716875; coverage=15/15
Prices dated 2026-09-29; uncached standard-price estimate, not actual billing. Fake costs zero; absent usage stays unknown.

## Dataset hashes

| Bill | PDF SHA-256 | Label SHA-256 |
| --- | --- | --- |
| bill_001 | af2f18acbbabf86d86e82b86a87c166c83c6c0211e6b3ad70bf7328f72c5b31d | 7b19b0d9fcbe3322d520516eb3ecfb3f129deb37a6b3764701bc696d34101651 |
| bill_002 | 0f4454f45e4b5af36322714f600dad12e2f500c4800c4e1601f888c1647b5d54 | d9025f5d87088545ba4cfb2476de917d2b7965066ff047476b04371109b3c63d |
| bill_003 | f3ec62b4bab93009c064e47afc7459976d59af85e14baecd6bade30b68163400 | 58c2b0eba2244461697d079f47b13ec5fe35e468016a8e96a7bec29559da19f4 |
| bill_004 | b863a7a1a95f1f69db2bdacf3aba71b68ab4ad94088925b91c70ae3755517147 | 7152044c87b166443b416eea46dd71fc640548e4bdb4f305f8617be0b4357801 |
| bill_005 | defab59e9dfcc21b2b4fc1fa8c2ae030124796dce33deaf0a47a8d6f1d365d06 | 5a52fc755b42499f251db3f65c1b7995152e385e057aaec34296e9dc899b7b07 |
