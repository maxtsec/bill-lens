# PDF parser failures: a passing suite missed malformed-input crashes

Status: deterministic 9,000-case replay completed on 2026-09-27; working evidence note, not a security benchmark.

## Question

Where should the boundary between invalid document input and an application bug
sit when a third-party parser can raise ordinary Python exceptions?

## Reviewer-reported evidence

On 2026-09-27 the owner supplied Claude's review of PR #3 at `b40411d`.
The original suite passed all 115 tests. Claude reported mutating PDFs through
random byte edits, truncations and inserted fragments, with these 9,000 outcomes:

| Outcome | Count reported by Claude |
| --- | ---: |
| `unreadable_pdf` | 6,794 |
| Success | 1,214 |
| `page_without_text` | 497 |
| `no_pages` | 436 |
| Escaped `TypeError` | 58 |
| Escaped `IndexError` | 1 |

That is 59 escaped exceptions (about 0.66%). These are supplied review results,
not a run reproduced by Codex. The follow-up supplied by the owner identifies
seed 1 (3,000 cases: 19 escaped TypeErrors) and seed 7 (6,000 cases: 39 escaped
TypeErrors and one IndexError). The reviewer reports that a parameterized script
preserves the original random-call order and reproduces both runs on `b40411d`.
The owner subsequently supplied the script and both full baseline CSVs through
`tmp/fuzz/`, plus `escaped_cases.csv` (59 data rows). The escaped-case file was
checked against the two baseline files. These artifacts are now preserved below.
The original baseline has not been independently rerun locally; the post-fix
replay and input identity comparison have.

## Post-fix replay results

Codex ran the supplied script on `4296867` using Python 3.12.14,
pdfplumber 0.11.10 and pdfminer.six 20260107. The five source PDFs and pinned
requirements are unchanged from `b40411d`. Every `(seed, case)`, mutation mode
and SHA-256 matched the baseline; duplicate or missing cases were checked.

| Outcome | Before (reviewer) | After (local replay) |
| --- | ---: | ---: |
| `unreadable_pdf` | 6,794 | 6,853 |
| Success | 1,214 | 1,214 |
| `page_without_text` | 497 | 497 |
| `no_pages` | 436 | 436 |
| Escaped `TypeError` | 58 | 0 |
| Escaped `IndexError` | 1 | 0 |
| Total | 9,000 | 9,000 |

All 59 escaped cases became `unreadable_pdf`. The other **8,941 outcomes were
unchanged**. Seed 1 completed 3,000 cases with zero escapes; seed 7 completed
6,000 with zero escapes. No parser timeout or memory measurement was added to
this replay. Both runs finished, but a future fuzz campaign still needs isolated
workers and resource limits. Zero escapes in this finite sample does not prove
all malformed PDFs are handled, that successful parses preserve all content,
or that the parser is safe for public uploads.

### Preserved artifacts

- [Original fuzz script](../../scripts/fuzz_pdf_boundary.py): generation logic and
  RNG call order unchanged; only line endings normalized to LF.
- [Manifest](evidence/pdf-boundary-fuzzing/manifest.json): code revisions, runtime
  versions, source-PDF hashes, script hash, and decompressed CSV hashes.
- [Summary](evidence/pdf-boundary-fuzzing/summary.json): outcome counts and transitions.
- Baseline CSVs: [seed 1](evidence/pdf-boundary-fuzzing/baseline_seed1.csv.gz),
  [seed 7](evidence/pdf-boundary-fuzzing/baseline_seed7.csv.gz).
- Post-fix CSVs: [seed 1](evidence/pdf-boundary-fuzzing/after_seed1.csv.gz),
  [seed 7](evidence/pdf-boundary-fuzzing/after_seed7.csv.gz).
- [59 originally escaped cases](evidence/pdf-boundary-fuzzing/escaped_cases.csv).

The four large CSVs are losslessly gzip-compressed to retain every row without
adding 18,000 generated data rows to the text diff. They contain synthetic input
hashes and classifications, not customer data. Corrupted PDFs are regenerated
from the script rather than committed. `--dump-escaped` writes only cases that
escape in the revision being tested; it will write none for these fixed runs.

### Reproduce from the repository root

Use the pinned development environment described in the README:

```powershell
New-Item -ItemType Directory -Force tmp/fuzz | Out-Null
.\.venv\Scripts\python.exe scripts/fuzz_pdf_boundary.py --seed 1 --cases 3000 --outcomes tmp/fuzz/after_seed1.csv
.\.venv\Scripts\python.exe scripts/fuzz_pdf_boundary.py --seed 7 --cases 6000 --outcomes tmp/fuzz/after_seed7.csv
```

Run the following Python comparison after the commands above. It rejects missing
or duplicate cases and changed input hashes/modes before comparing results:

```python
import csv
import gzip
from collections import Counter
from pathlib import Path

EVIDENCE = Path("docs/learning/evidence/pdf-boundary-fuzzing")

def load(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {(int(r["seed"]), int(r["case"])): r for r in rows}
    assert len(result) == len(rows), f"Duplicate cases: {path}"
    return result

before = load(EVIDENCE / "baseline_seed1.csv.gz") | load(EVIDENCE / "baseline_seed7.csv.gz")
after = load(Path("tmp/fuzz/after_seed1.csv")) | load(Path("tmp/fuzz/after_seed7.csv"))
expected = {(1, i) for i in range(3000)} | {(7, i) for i in range(6000)}
assert before.keys() == after.keys() == expected, "Case coverage differs"
assert all(
    (before[k]["sha256"], before[k]["mode"]) == (after[k]["sha256"], after[k]["mode"])
    for k in before
), "Inputs differ"
changes = Counter((before[k]["outcome"], after[k]["outcome"]) for k in before
                  if before[k]["outcome"] != after[k]["outcome"])
for (old, new), count in sorted(changes.items()):
    print(count, old, "->", new)
print("Escaped after:", sum(r["outcome"].startswith("ESCAPED") for r in after.values()))
print("Previously classified cases changed:", sum(
    before[k]["outcome"] != after[k]["outcome"] for k in before
    if not before[k]["outcome"].startswith("ESCAPED")
))
```

Expected output: 58 TypeErrors and one IndexError become `unreadable_pdf`,
zero escaped cases after, and zero previously classified outcomes changed.

## Locally reproduced evidence

Before the fix, replacing `/MediaBox` with `/MediaBoz` in `bill_001/bill.pdf`
raised `TypeError: 'NoneType' object is not iterable`. Both names have the same
byte length, preserving offsets while removing a page attribute the parser uses.
The committed PDFs were not edited.

Reproduce with the installed development environment:

```python
from pathlib import Path
from bill_lens.pdf_text import extract_pdf_text

data = Path("dataset/bill_001/bill.pdf").read_bytes()
extract_pdf_text(data.replace(b"/MediaBox", b"/MediaBoz"))
```

After the fix, all five golden PDFs under this mutation raise `PdfTextError`
with `code="unreadable_pdf"`, `parser_error="TypeError"`, and no original parser
exception in `__context__` or `__cause__`. This is covered by the parametrized
`test_missing_media_box_is_classified` regression. The revised suite passes
130 tests with both `python -m pytest -q` and direct `pytest -q`.

## Decision and trade-off

The original implementation caught a list of known parser exception types
around the whole extraction block. Ordinary Python exceptions from the parser
could escape, while some application errors within that block could be hidden.

The fix guards individual parser calls with `except Exception`, records only
the class name, and raises a new error after leaving the handler. Application
checks and result construction are outside those guards. A regression now
injects an application error into `PageText` construction and confirms it escapes;
mocking `pdfplumber.open` had actually tested the library boundary.

Cleanup also belongs to the library boundary. A failure closing a successfully
parsed document becomes `unreadable_pdf`; a cleanup failure during an existing
failure cannot replace the primary error. Process-control exceptions are allowed
to propagate. This approach cannot distinguish a library defect from a bad
document, and does not enforce parser time or memory limits.

Raising with `from None` only hides traceback chaining; it does not remove the
original exception from `__context__`. Raising after the handler avoids attaching
that parser exception. Traceback locals can still contain document data, and
library logging is separate: error tracking must not capture those indiscriminately.

## Possible follow-up experiment

Try a new seed and compare a widened exception list with the narrow broad-catch
boundary. Whether either approach leaks more failures is a hypothesis to test,
not an observed result. Run new arbitrary mutations in isolated workers with
time and memory limits; the current script does not supply those protections.

Reference: [PR #3](https://github.com/maxtsec/bill-lens/pull/3).
