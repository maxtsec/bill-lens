# Evaluation test-run

Run: fake / requested fake-v1 / resolved fake-v1
Prompt: fixture-v1; effort: None
Harness/scoring: 1/1; started: 2026-09-29T00:00:00+00:00
Code: code-revision (dirty=False)
Dataset: dataset; 1 synthetic bills @ dataset-revision; repeats: 2
Completed attempts: 2/2; complete=True; abort=None

Synthetic bills only; descriptive results, not evidence of real-world accuracy or statistical significance.

## Fields

| Field | correct | wrong_value | missing | false_extraction | no_fields |
| --- | --- | --- | --- | --- | --- |
| retailer | 2/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| period_start | 2/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| period_end | 2/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| stated_billing_days | 2/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| total_usage_kwh | 2/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| daily_supply_rate | 2/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| current_bill_amount | 1/2 | 1/2 | 0/2 | 0/2 | 0/2 |

Exact bill match: 1/2
Review decision: flags 2/2; status 2/2
Supply rate_value: 2/2 matched when both rates exist; 0/2 unavailable
Supply gst_basis: 2/2 matched when both rates exist; 0/2 unavailable
Attempt outcomes: none 2/2; rate_limited 0/2; timeout 0/2; refused 0/2; truncated 0/2; invalid_output 0/2; provider_error 0/2

## Per-bill correctness across repeats

Counts below use completed repeats; see planned/completed totals above.

| Bill | Exact | Flags | Status | retailer | period_start | period_end | stated_billing_days | total_usage_kwh | daily_supply_rate | current_bill_amount |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bill_001 | 1/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 1/2 |

## Usage and latency

input_tokens: total=None; known subtotal=0; coverage=0/2
output_tokens: total=None; known subtotal=0; coverage=0/2
Latency ms: median=0.0; max=0
Estimated cost US$: 0; known subtotal=0; coverage=2/2
Prices dated 2026-09-29; uncached standard-price estimate, not actual billing. Fake costs zero; absent usage stays unknown.

## Dataset hashes

| Bill | PDF SHA-256 | Label SHA-256 |
| --- | --- | --- |
| bill_001 | PDF_SHA256 | LABEL_SHA256 |
