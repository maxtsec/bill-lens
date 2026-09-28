# Evaluation 20260928T224659Z-206893300747

Run: openai / requested gpt-5.4-mini / resolved gpt-5.4-mini-2026-03-17
Prompt: extract-v4; effort: low
Harness/scoring: 1/1; started: 2026-09-28T22:46:59.849528+00:00
Code: b1fdef0009504c44e19b13d9f957e2143d3447b6 (dirty=False)
Dataset: holdout; 6 synthetic bills @ b1fdef0009504c44e19b13d9f957e2143d3447b6; repeats: 3
Completed attempts: 18/18; complete=True; abort=None

Synthetic bills only; descriptive results, not evidence of real-world accuracy or statistical significance.

## Fields

| Field | correct | wrong_value | missing | false_extraction | no_fields |
| --- | --- | --- | --- | --- | --- |
| retailer | 18/18 | 0/18 | 0/18 | 0/18 | 0/18 |
| period_start | 18/18 | 0/18 | 0/18 | 0/18 | 0/18 |
| period_end | 18/18 | 0/18 | 0/18 | 0/18 | 0/18 |
| stated_billing_days | 18/18 | 0/18 | 0/18 | 0/18 | 0/18 |
| total_usage_kwh | 18/18 | 0/18 | 0/18 | 0/18 | 0/18 |
| daily_supply_rate | 18/18 | 0/18 | 0/18 | 0/18 | 0/18 |
| current_bill_amount | 18/18 | 0/18 | 0/18 | 0/18 | 0/18 |

Exact bill match: 18/18
Review decision: flags 18/18; status 18/18
Supply rate_value: 18/18 matched when both rates exist; 0/18 unavailable
Supply gst_basis: 18/18 matched when both rates exist; 0/18 unavailable
Attempt outcomes: none 18/18; rate_limited 0/18; timeout 0/18; refused 0/18; truncated 0/18; invalid_output 0/18; provider_error 0/18

## Per-bill correctness across repeats

Counts below use completed repeats; see planned/completed totals above.

| Bill | Exact | Flags | Status | retailer | period_start | period_end | stated_billing_days | total_usage_kwh | daily_supply_rate | current_bill_amount |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| holdout_001 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_002 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_003 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_004 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_005 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_006 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |

## Usage and latency

input_tokens: total=29130; known subtotal=29130; coverage=18/18
output_tokens: total=2409; known subtotal=2409; coverage=18/18
Latency ms: median=1707.0; max=2386
Estimated cost US$: 0.03268800; known subtotal=0.03268800; coverage=18/18
Prices dated 2026-09-29; uncached standard-price estimate, not actual billing. Fake costs zero; absent usage stays unknown.

## Dataset hashes

| Bill | PDF SHA-256 | Label SHA-256 |
| --- | --- | --- |
| holdout_001 | ffee69648f2d780ee84bf64980f678e5e183104a10b78b187690ee1ed9dc74ef | 616951ed748b68ba3e9f59eeea8dcbb8d7c948eb1362f1f44d9160bb23c3bec7 |
| holdout_002 | cfb17fe951951e7a7e386209cf161a2242701a93b99ada56fa00bd9b88572e9a | 4925d0bb4433c0a999311b4db0e2078116df44f5e4255ca7700fd545a8b4eac8 |
| holdout_003 | 747c4428e6e739ea4a0778c4cd74e7194d8ee7ca809d03eecf2df0cd7a49159b | 7c57dee26614acb38813f604a8cc31e59002b983f5cb2b2c8ce5fb2b9934f71a |
| holdout_004 | 254131d62e6cca2bf6e39c8b61d05f22b05134a90c07839c0d4de72200e41068 | e55e285136d6654e86a80e453116898d481200b838e04aa53cdf56e84c4d5e32 |
| holdout_005 | 67c4203c18e186cd8148dcbd158a930344b02a7cc7f734ffd7636fac8b6c2f9c | 55e92879d2b6e850040af0c4088f07bd499a5560103cc27553eead199bcbcb1f |
| holdout_006 | 16f1d836c846f611a9ae406fee14613df2501d576a7f36c9b2b84ec3327bb3f8 | 8cbc87c5ca4f495909110bda0e2ee97be8a2a267277c3683072a33136936a56b |
