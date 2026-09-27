# Bill Lens

Bill Lens is a portfolio project for turning Victorian household electricity bill PDFs into structured, explainable, and verifiable data. The engineering rule is to use an LLM where a document is ambiguous and deterministic Python code for calculations, units, and validation.

**Milestone 0 is complete; Milestone 1 is in progress.** Five PDFs and owner-verified labels exist, together with Pydantic schemas and deterministic Python checks. M1 starts with a reusable PDF text boundary and schema descriptions. The upload-to-JSON application and measured LLM extraction accuracy are still pending.

- [Initial extraction contract](docs/extraction-contract.md)
- [Five-bill synthetic dataset and review checklist](dataset/README.md)
- [ADR-001: PDF extraction strategy](docs/adr/001-pdf-extraction-strategy.md)
- [M1 PDF text boundary and failure policy](docs/pdf-text-boundary.md)

## Run locally

Requires Python 3.12 or newer. From the repository root, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/inspect_dataset.py
```

On macOS/Linux, use `.venv/bin/python` instead. The pinned `requirements-dev.txt` records the tested dependency versions; `pyproject.toml` declares supported ranges. Use the pinned versions when reproducing PDF bytes. Tests require no API keys or network calls.

Rebuild the synthetic PDFs with `python scripts/generate_dataset.py` using that environment. The builder only writes PDFs: it never reads or generates `expected.json`. Extracted text goes to the ignored `tmp/extracted/` directory. The committed PDFs can be opened without running the builder.

## What the checks establish

- Pydantic rejects malformed dates, numbers, unknown units, extra keys and omitted nullable keys.
- Python calculates inclusive billing days and exact supply-rate unit conversion, then derives review flags and status.
- Tests compare derived flags against independently authored labels, check label status consistency, and reconcile quantities, rates and charge amounts read from the actual PDFs using `Decimal`.
- Regression cases cover missing fields, unknown GST basis, reverse dates, leap days, zero usage and credit amounts. Passing these tests establishes deterministic behavior; it does not measure an LLM's ability to read a bill.

The [text baseline inspection](dataset/text-baseline.md) records the observed reading order. The owner has verified all five PDFs against their labels. In the re-review supplied by the owner on 2026-09-27, Claude approved commit `f4e5cd1`, confirming both must-fix issues were resolved and all 91 tests passed through three pytest entry points. The owner completed verification of `bill_001`, `bill_003`, and `bill_004` on 2026-09-27 and authorized rebase merge. Next, the first application slice will upload a PDF, extract and validate fields, persist the result, and return structured JSON.

## M1 progress and next steps

- Added contract-aligned Pydantic descriptions to all seven extraction fields and the supply-rate components, preserving required nullable keys.
- Added `extract_pdf_text(bytes)` with page provenance, a file hash, acceptance limits and explicit failures. The inspection script now uses it.
- Next: choose the LLM provider/model and connect structured extraction with a versioned prompt; then add the upload, persistence and JSON response path in reviewable changes.
