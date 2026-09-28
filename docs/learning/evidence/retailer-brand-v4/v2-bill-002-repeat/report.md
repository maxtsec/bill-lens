# Evaluation 20260928T232541Z-2b18b62e60bf

Run: openai / requested gpt-5.4-mini / resolved gpt-5.4-mini-2026-03-17
Prompt: extract-v2; effort: low
Harness/scoring: 1/1; started: 2026-09-28T23:25:41.607236+00:00
Code: 1ecad8057dd29695d5ceca23722c0b959607dd21 (dirty=False)
Dataset: 1 synthetic bills @ 424c0493740f14d03fd71ec6c8d20e5ce1b5a819; repeats: 20
Completed attempts: 20/20; complete=True; abort=None

Synthetic bills only; descriptive results, not evidence of real-world accuracy or statistical significance.

## Fields

| Field | correct | wrong_value | missing | false_extraction | no_fields |
| --- | --- | --- | --- | --- | --- |
| retailer | 20/20 | 0/20 | 0/20 | 0/20 | 0/20 |
| period_start | 20/20 | 0/20 | 0/20 | 0/20 | 0/20 |
| period_end | 20/20 | 0/20 | 0/20 | 0/20 | 0/20 |
| stated_billing_days | 20/20 | 0/20 | 0/20 | 0/20 | 0/20 |
| total_usage_kwh | 20/20 | 0/20 | 0/20 | 0/20 | 0/20 |
| daily_supply_rate | 20/20 | 0/20 | 0/20 | 0/20 | 0/20 |
| current_bill_amount | 20/20 | 0/20 | 0/20 | 0/20 | 0/20 |

Exact bill match: 20/20
Review decision: flags 20/20; status 20/20
Supply rate_value: 20/20 matched when both rates exist; 0/20 unavailable
Supply gst_basis: 20/20 matched when both rates exist; 0/20 unavailable
Attempt outcomes: none 20/20; rate_limited 0/20; timeout 0/20; refused 0/20; truncated 0/20; invalid_output 0/20; provider_error 0/20

## Per-bill correctness across repeats

Counts below use completed repeats; see planned/completed totals above.

| Bill | Exact | Flags | Status | retailer | period_start | period_end | stated_billing_days | total_usage_kwh | daily_supply_rate | current_bill_amount |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bill_002 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |

## Usage and latency

input_tokens: total=25852; known subtotal=25852; coverage=20/20
output_tokens: total=4759; known subtotal=4759; coverage=20/20
Latency ms: median=2218.5; max=3174
Estimated cost US$: 0.0408045; known subtotal=0.0408045; coverage=20/20
Prices dated 2026-09-29; uncached standard-price estimate, not actual billing. Fake costs zero; absent usage stays unknown.

## Dataset hashes

| Bill | PDF SHA-256 | Label SHA-256 |
| --- | --- | --- |
| bill_002 | 0f4454f45e4b5af36322714f600dad12e2f500c4800c4e1601f888c1647b5d54 | d9025f5d87088545ba4cfb2476de917d2b7965066ff047476b04371109b3c63d |
