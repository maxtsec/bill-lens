# Evaluation 20261001T015251Z-6495d365da87

Run: openai / requested gpt-5.4-mini / resolved gpt-5.4-mini-2026-03-17
Prompt: extract-v4; effort: low
Harness/scoring: 1/3; started: 2026-10-01T01:52:51.464849+00:00
Code: ce5ea6cab244a47e80977a7b850f0c49d0861dd7 (dirty=False)
Dataset: role-holdout; 10 synthetic bills @ ce5ea6cab244a47e80977a7b850f0c49d0861dd7; repeats: 3
Completed attempts: 30/30; complete=True; abort=None

Synthetic bills only; descriptive results, not evidence of real-world accuracy or statistical significance.

## Fields

| Field | correct | wrong_value | missing | false_extraction | no_fields |
| --- | --- | --- | --- | --- | --- |
| retailer | 30/30 | 0/30 | 0/30 | 0/30 | 0/30 |
| period_start | 30/30 | 0/30 | 0/30 | 0/30 | 0/30 |
| period_end | 30/30 | 0/30 | 0/30 | 0/30 | 0/30 |
| stated_billing_days | 30/30 | 0/30 | 0/30 | 0/30 | 0/30 |
| total_usage_kwh | 30/30 | 0/30 | 0/30 | 0/30 | 0/30 |
| daily_supply_rate | 30/30 | 0/30 | 0/30 | 0/30 | 0/30 |
| current_bill_amount | 30/30 | 0/30 | 0/30 | 0/30 | 0/30 |

Exact bill match: 30/30
Review decision: flags 12/30; status 12/30
Supply rate_value: 30/30 matched when both rates exist; 0/30 unavailable
Supply gst_basis: 30/30 matched when both rates exist; 0/30 unavailable
Attempt outcomes: none 30/30; rate_limited 0/30; timeout 0/30; refused 0/30; truncated 0/30; invalid_output 0/30; provider_error 0/30

## Per-bill correctness across repeats

Counts below use completed repeats; see planned/completed totals above.

| Bill | Exact | Flags | Status | retailer | period_start | period_end | stated_billing_days | total_usage_kwh | daily_supply_rate | current_bill_amount |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| holdout_r01 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_r02 | 3/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_r03 | 3/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_r04 | 3/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_r05 | 3/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_r06 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_r07 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_r08 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_r09 | 3/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| holdout_r10 | 3/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |

## Usage and latency

input_tokens: total=49088; known subtotal=49088; coverage=30/30
output_tokens: total=5900; known subtotal=5900; coverage=30/30
Latency ms: median=2150.0; max=3200
Estimated cost US$: 0.06336600; known subtotal=0.06336600; coverage=30/30
Prices dated 2026-09-29; uncached standard-price estimate, not actual billing. Fake costs zero; absent usage stays unknown.

## Budget ledger

Cap US$0.30; conservative spent/reserved US$0.06336600; known settled estimate US$0.06336600.
Reservations are persisted before calls; unresolved usage is not refunded or treated as zero.

## Dataset hashes

| Bill | PDF SHA-256 | Label SHA-256 |
| --- | --- | --- |
| holdout_r01 | a567c99fd22d54fb8af390856955b52ffe9c2f50fff51f61358846ff6f07e112 | b638be9df68463b685aecaa0b75cf9cf442bc7273aced64912e7bb7b864442b2 |
| holdout_r02 | f2184cae89245809ee19827816f98b9c5e5bef97bdcd3c9ca159c16acf2a93f7 | c6db8b0dc2ab6201697a948ecb1d613f67f786dbab3e9be568e5f5e0045ae89e |
| holdout_r03 | 968eea267e0126ff338930885fd2024c9e0439afdf97ed400e22ef6d37b818ab | f7aedae34f1d65982303c2276f7fffc8a95f68415dca594b48594647b16b5c65 |
| holdout_r04 | 7f07e5ce41477041aa52c66c083e1da6ba4c0d01153a94286a6f4928364e5e5b | 00a487b1aacd050a6dce1e9dc8dfaed4065f01c9b9440ac5a12b558c6c59fdbd |
| holdout_r05 | 957fde2df284545b2039b2d837732f246b5822cd924f0861de0be2bbc8062084 | 819b326a765a6c77c6194119abbe037901025ad05288f1bf7642971d8ad25a67 |
| holdout_r06 | 39fda04c423104ec0d9e11089683b6301edc5dcb07a175acab63d09baf9d3993 | 9e4cef51c590169881ea3e4b9307ca6c5d7c8d5970aea7f50d81154a05c4f65b |
| holdout_r07 | 5bf1ff28ea5f9acbd3f6aa2898991d86396cf7c82e181a84047478f72868d239 | 9c739703559f152ca56305513f8c1f210cfbedd204308464508e0dcd29ac483f |
| holdout_r08 | 617df9eee77f71a39167e028929cc60676015ee9ce135eaf87670305e1c1206b | 883062f0654c1e498f644cecd41a758b6a0da28744ec19e64e437042dee8ec5d |
| holdout_r09 | b193e96110d02714c348fab407f165a4c93bd5643125fe249c59bd25338ac422 | e00b18656c503264af6349fbc61f8a94cc9221c632c03b223eaa3f4701ba23e4 |
| holdout_r10 | 78cab6090a7f6d6f69e517673b5a9ee6b12236d4b3a518e1ae7d88cc3e08961e | ee7e799343aa81b089861ebfc9bca2d1560de3f0469c0dca2892009915f49acf |
