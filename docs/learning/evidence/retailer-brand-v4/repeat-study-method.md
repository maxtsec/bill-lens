# Repeat-study method and offline audit

These calculations use saved synthetic responses only. They make no API calls.
Run commands from the repository root with the project venv. Original three-run
artifacts remain unchanged; the manifest now covers the repeat-study additions.

## Wilson intervals (standard library)

Compute the two-sided 95% Wilson score interval without continuity correction.
This implementation follows the [NIST formula](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
The explicit endpoint cases avoid floating-point residue such as 1e-17 at zero.

```python
import json
from math import sqrt
from pathlib import Path
from statistics import NormalDist

def wilson(k, n):
    assert n > 0 and 0 <= k <= n
    z = NormalDist().inv_cdf(0.975)
    p = k / n
    denominator = 1 + z*z/n
    centre = (p + z*z/(2*n)) / denominator
    half = z * sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return (0.0 if k == 0 else max(0.0, centre-half),
            1.0 if k == n else min(1.0, centre+half))

root = Path('docs/learning/evidence/retailer-brand-v4')
for version in ('v2', 'v4'):
    rows = [json.loads(line) for line in
            (root / f'{version}-bill-002-repeat/attempts.jsonl').read_text().splitlines()]
    k = sum(r['field_outcomes']['current_bill_amount'] == 'false_extraction' for r in rows)
    lower, upper = wilson(k, len(rows))
    print(version, f'{k}/{len(rows)}', f'{100*lower:.2f}%-{100*upper:.2f}%')
```

Expected output: v2 0/20, 0.00%-16.11%; v4 2/20, 2.79%-30.10%.
These are separate rate intervals, not a confidence interval for their difference.
Repeated calls to one selected bill do not estimate population-wide bill accuracy.

## Budget guard

The ignored local runner imported each checkout's own harness and wrapped its
Responses call. It did not modify either checkout or any request argument.
Its preflight captured one request per version with a local stub that throws
before network access; these were not model calls. It verified the commit,
clean checkout, prompt, bill hash, low effort, model, output cap and zero retries.

The guard applied this policy before **each** network request:

```python
from decimal import Decimal
limit = Decimal('0.20')
reserve = (Decimal('0.75') * 32768 + Decimal('4.50') * 4096) / 1000000
assert reserve == Decimal('0.043008')
# Stop if prior usage is unknown, scope/count is wrong, request exceeds
# 16384 serialized UTF-8 bytes, or settled_spend + reserve > limit.
# Write the reservation to the shared local ledger before sending.
# On known usage, replace the reservation with:
# (Decimal('0.75') * input_tokens + Decimal('4.50') * output_tokens) / 1000000
# Keep an unsettled reservation and prohibit the next call after an exception
# or missing usage. No restart/resume of a partial version run is allowed.
```

The input allowance is conservative accounting, not an exact tokenizer or
provider invoice guarantee. The entire serialized request was 6,311 bytes for
v2 and 7,751 for v4, well below the byte guard; the 32,768 token allowance adds
substantial room for protocol/schema framing. Output is explicitly capped at
4,096. All actual usage counts were known and below these allowances.
The boundary check was verified offline: exactly `limit-reserve` permits a call,
one additional 0.00000001 USD blocks it, and spent=limit blocks it.

The durable ledger contains exactly 20 v2 then 20 v4 settled entries, no keys,
raw requests or machine paths. Token/cost entries match each saved attempt;
every reserved cumulative total is <=0.20. Highest reservation: 0.1301385.
Final settled estimate: 0.0896070. No budget/configuration/usage stop occurred.
Unused budget does not authorise more calls.

## Reproduce the comparison and verify byte identity

```powershell
.\.venv\Scripts\python.exe -m evals.compare docs/learning/evidence/retailer-brand-v4/v2-bill-002-repeat docs/learning/evidence/retailer-brand-v4/v4-bill-002-repeat
```

```python
import hashlib
import json
from pathlib import Path

root = Path('docs/learning/evidence/retailer-brand-v4')
manifest = json.loads((root / 'manifest.json').read_text())
for name, expected in manifest['artifact_hashes'].items():
    data = (root / name).read_bytes()
    assert len(data) == expected['bytes']
    assert hashlib.sha256(data).hexdigest() == expected['sha256'], name
```

Additional offline audit performed: all 40 new raw responses rebuilt with
`build_attempt`, rescored against the manual bill_002 label, and summaries
reproduced with `summarize`. Bill/repeat pairs are exactly 1..20 once per version;
all input hashes match the originals and copied one-bill dataset. Both new runs
resolve to gpt-5.4-mini-2026-03-17, with matching runtime packages. All 45 pinned
requirements match the installed distributions; a freeze without the editable
project path is retained. The v2 worktree was clean and removed after completion.

Targeted offline verification: `python -m pytest tests/test_evals.py -q --tb=short`
passed **56 tests**. No additional live calls were used for verification.
