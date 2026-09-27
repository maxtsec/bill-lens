# Bill Lens

Bill Lens is a portfolio project for turning Victorian household electricity bill PDFs into structured, explainable, and verifiable data. The engineering rule is to use an LLM where a document is ambiguous and deterministic Python code for calculations, units, and validation.

**Milestone 0 is complete; Milestone 1 is in progress.** Five PDFs and owner-verified labels exist, together with Pydantic schemas and deterministic Python checks. M1 starts with a reusable PDF text boundary and schema descriptions. The upload-to-JSON application and measured LLM extraction accuracy are still pending.

- [Initial extraction contract](docs/extraction-contract.md)
- [Five-bill synthetic dataset and review checklist](dataset/README.md)
- [ADR-001: PDF extraction strategy](docs/adr/001-pdf-extraction-strategy.md)
- [M1 PDF text boundary and failure policy](docs/pdf-text-boundary.md)
- [ADR-002: Extraction port and deterministic fake](docs/adr/002-extraction-port.md)
- [ADR-003: PostgreSQL persistence model](docs/adr/003-persistence-model.md)

## Run locally

Requires Python 3.12 or newer. From the repository root, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/inspect_dataset.py
```

On macOS/Linux, use `.venv/bin/python` instead. The pinned `requirements-dev.txt` records the tested dependency versions; `pyproject.toml` declares supported ranges for existing dependencies and exact pins for the database stack. Use the pinned versions when reproducing PDF bytes. Tests require no API keys or external services; DB tests use local PostgreSQL and visibly skip when `TEST_DATABASE_URL` is unset.

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
- Added the provider-independent `BillExtractor` port, recordable `ExtractionAttempt`, one shared raw-response validation helper, and a deterministic `FakeExtractor`. All five PDFs now exercise the pipeline through domain flags without a model or API key. This tests plumbing, not extraction accuracy.
- Added Phase 1 persistence: PostgreSQL, Alembic, atomic Bill/ExtractionRun writes, database-enforced hash uniqueness and real database tests.
- Next, **after Phase 1 is reviewed and merged**: Phase 2 upload and JSON response path using the fake. Real adapters, prompts and retries are deferred.

### Exercise the extraction port locally

From the repository root in the installed development environment:

```python
from pathlib import Path
from bill_lens.extraction import FakeExtractor
from bill_lens.pdf_text import extract_pdf_text
from bill_lens.validation import derive_flags, derive_status

document = extract_pdf_text(Path("dataset/bill_002/bill.pdf").read_bytes())
attempt = FakeExtractor.from_dataset(Path("dataset")).extract(document)
if attempt.error_code is not None:
    print(attempt.error_code)  # Later: persist failed attempts too.
else:
    flags = derive_flags(attempt.fields)
    print(derive_status(flags), sorted(flags))
# needs_review ['current_bill_amount_missing']
```

To script an expected provider failure, construct a mapping entry such as
`ScriptedResponse(raw_response=None, error_code="timeout", latency_ms=1000)`
under the document's `file_sha256` and pass the mapping to `FakeExtractor`.
Unknown hashes raise `KeyError` as missing fixture setup; other scripted outcomes
and invariants are documented in ADR-002. No real model is called.

### PostgreSQL and migrations (Windows / PowerShell)

Install Docker Desktop with its Linux engine running. From the repo root, create
the local configuration once (keep an existing `.env` if already configured):

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Import only the simple KEY=value entries in this project's local file.
Get-Content .env | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
docker compose up -d --wait
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q
```

Compose reads `.env` itself; Python/Alembic read process environment variables.
Example credentials are for local development only. Port 55432 binds to loopback;
change `POSTGRES_PORT` and both URLs together if it is occupied. The image pins
PostgreSQL major 17; patch releases within that major can change on image pulls.
Data remains in the named volume across `docker compose stop` / `up`.

`DATABASE_URL` is used by the app engine and Alembic. `TEST_DATABASE_URL` is used
only by tests. Both require `postgresql+psycopg://...`. The example points them at
the same local database, but tests use their own random schema and never migrate,
delete or truncate the app's public tables. Use a local test-capable account with
CREATE SCHEMA permission; do not point these tests at a production database.

```powershell
# DB-only: migrations, constraints, all five golden bills and duplicate race.
.\.venv\Scripts\pytest.exe -m db -q
# Offline suite; DB tests are deselected here.
.\.venv\Scripts\python.exe -m pytest -m "not db" -q
# To verify explicit skip reporting, unset the test URL then run all tests.
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest -q
```

An unset test URL produces `SKIPPED: TEST_DATABASE_URL is not set...`. A set URL
whose database cannot be reached produces failures, not skips. DB tests run
`downgrade base` then `upgrade head` **inside their disposable schema** and check
ORM/migration drift. No test uses `metadata.create_all`.

The persistence helper flushes within a SAVEPOINT and the caller commits the
outer transaction. See ADR-003 for the transaction pattern and duplicate outcome.
No upload endpoint, file writing or HTTP application is included in Phase 1.
