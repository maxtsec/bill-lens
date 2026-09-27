# PDF parser failures: a passing suite missed malformed-input crashes

Status: working evidence note, not a completed fuzzing benchmark.

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
The supplied commands are `python fuzz_pdf_boundary.py --seed 1 --cases 3000
--outcomes after_seed1.csv` and the equivalent seed-7 command with 6,000 cases.

The owner described four attachments (`fuzz_pdf_boundary.py`,
`baseline_seed1.csv`, `baseline_seed7.csv`, `escaped_cases.txt`), but the files
are not yet accessible in this task or checked into this repository. The two
CSV files reportedly contain `seed, case, mode, sha256, outcome`. Obtain these
actual files before claiming a comparable post-fix 9,000-case result or zero
crashes; the pasted description is insufficient to regenerate identical inputs.

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

## Next experiment

1. Obtain and check in the supplied fuzz script and baseline CSVs; record corpus
   hashes and verify Python 3.12.14, pdfplumber 0.11.10 and pdfminer.six 20260107.
   Run the script on `b40411d` to reproduce the supplied baseline if needed.
2. Run the same mutations against the fixed revision, counting classified
   failures, successful parses, escaped exceptions and timeouts separately.
   Match each `(seed, case)` and input SHA-256 before comparing outcomes. Check
   both the 59 escaped cases and whether any of the other 8,941 outcomes changed. Use
   isolated workers with time/resource limits for arbitrary corrupt documents.
3. Try a new seed and compare a widened exception list with the narrow broad-catch
   boundary. Whether either approach leaks more failures is a hypothesis to test,
   not an observed result. Zero exceptions in a sample would not prove safety.

Reference: [PR #3](https://github.com/maxtsec/bill-lens/pull/3).
