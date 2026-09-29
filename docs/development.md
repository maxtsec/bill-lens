# Development guide

[Back to the portfolio overview](../README.md).

Run all commands from the repository root. The default fake and ordinary tests
need no model API key; paid OpenAI steps are explicitly marked below. This guide
retains the setup, inspection, database, API, evaluation and live-check instructions
previously in the root README. Use synthetic bills only.

- [Install and inspect the dataset](#run-locally)
- [Local extraction example](#exercise-the-extraction-port-locally)
- [PostgreSQL and migrations](#postgresql-and-migrations-windows--powershell)
- [Upload API](#upload-api-local-fake-by-default)
- [Paid OpenAI API mode](#openai-upload-api-opt-in-spends-credit)
- [Paid smoke check](#manual-live-smoke-check-spends-credit)
- [Offline evaluation](#m2-evaluation-offline-first)
- [Offline printed-value replay](#m3-printed-value-safeguard)
- [Documentation link check](#check-documentation-links)

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
- Non-null amounts, usage, supply rates, day counts and retailer names absent from the extracted PDF text add review flags. Values are preserved for review; printed numbers in the wrong role can still pass.
- Tests compare derived flags against independently authored labels, check label status consistency, and reconcile quantities, rates and charge amounts read from the actual PDFs using `Decimal`.
- Regression cases cover missing fields, unknown GST basis, reverse dates, leap days, zero usage and credit amounts. Passing these tests establishes deterministic behavior; it does not measure an LLM's ability to read a bill.

The [text baseline inspection](../dataset/text-baseline.md) records the observed reading order. The owner has verified all five PDFs against their labels. In the re-review supplied by the owner on 2026-09-27, Claude approved commit `f4e5cd1`, confirming both must-fix issues were resolved and all 91 tests passed through three pytest entry points. The owner completed verification of `bill_001`, `bill_003`, and `bill_004` on 2026-09-27 and authorized rebase merge. [PR #2](https://github.com/maxtsec/bill-lens/pull/2) records that historical dataset milestone; the upload-to-JSON API is now implemented as described below.

## Implementation history

- Added contract-aligned Pydantic descriptions to all seven extraction fields and the supply-rate components, preserving required nullable keys.
- Added `extract_pdf_text(bytes)` with page provenance, a file hash, acceptance limits and explicit failures. The inspection script now uses it.
- Added the provider-independent `BillExtractor` port, recordable `ExtractionAttempt`, one shared raw-response validation helper, and a deterministic `FakeExtractor`. All five PDFs now exercise the pipeline through domain flags without a model or API key. This tests plumbing, not extraction accuracy.
- Added Phase 1 persistence: PostgreSQL, Alembic, atomic Bill/ExtractionRun writes, database-enforced hash uniqueness and real database tests.
- Added a pre-API fix for special-character responses: invalid retailer controls become `invalid_output`, while BYTEA storage preserves the exact raw string, including NUL and surrogates.
- Added Phase 2: local `POST /bills` / `GET /bills/{id}`, bounded uploads, opaque PDF storage, duplicate protection, and saved success/failure results using the fake.
- Added the OpenAI Responses adapter and versioned prompt, opt-in API configuration, and user-driven retries for transient failures. Every completed retry is retained; concurrent late failures cannot downgrade a validated result. The M2 harness and first v4 live evidence are now available below.

### Exercise the extraction port locally

From the repository root in the installed development environment:

```python
from pathlib import Path
from bill_lens.extraction import FakeExtractor
from bill_lens.pdf_text import extract_pdf_text
from bill_lens.validation import derive_review_flags, derive_status

document = extract_pdf_text(Path("dataset/bill_002/bill.pdf").read_bytes())
attempt = FakeExtractor.from_dataset(Path("dataset")).extract(document)
if attempt.error_code is not None:
    print(attempt.error_code)  # Simulated failure; no real provider call.
else:
    flags = derive_review_flags(attempt.fields, document)
    print(derive_status(flags), sorted(flags))
# needs_review ['current_bill_amount_missing']
```

To script an expected provider failure, construct a mapping entry such as
`ScriptedResponse(raw_response=None, error_code="timeout", latency_ms=1000)`
under the document's `file_sha256` and pass the mapping to `FakeExtractor`.
Unknown hashes raise `KeyError` as missing fixture setup; other scripted outcomes
and invariants are documented in [ADR-002](adr/002-extraction-port.md). No real model is called.

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
outer transaction. See [ADR-003](adr/003-persistence-model.md) for the transaction pattern and duplicate outcome.
Phase 2 connects that helper to HTTP and local PDF storage as described below.

Migration `0002` converts raw responses from text to BYTEA (UTF-8 with
`surrogatepass`); ORM callers still read/write `str | None`. Stop application
processes before applying it. Existing text and NULL values are preserved.
A downgrade to `0001` aborts without deleting evidence if NUL/surrogate data
cannot fit the old text column. See [ADR-004](adr/004-lossless-raw-response.md) for decoding and rollback details.

### Upload API (local, fake by default)

Install the updated requirements, import `.env` as above, start PostgreSQL and
run `alembic upgrade head` before starting the app. From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn bill_lens.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open the interactive API docs at `http://127.0.0.1:8000/docs` and upload a golden PDF,
or in a second PowerShell terminal:

```powershell
curl.exe -i -F "file=@dataset/bill_001/bill.pdf" http://127.0.0.1:8000/bills
# Use the id returned above:
curl.exe http://127.0.0.1:8000/bills/<bill-id>
```

A new upload returns **201**; the same PDF returns **200** with the existing bill
identity. Successful/needs_review results and non-retryable failures are reused.
For a current failure with `rate_limited`, `timeout` or `provider_error`, re-upload
calls the extractor once and appends a new run, preserving history and the PDF.
`refused`, `truncated` and `invalid_output` are not retried automatically by
re-upload. There is no background retry or automatic backoff.

Simultaneous **first** uploads of the same PDF may both call the extractor, but
the database UNIQUE constraint keeps one bill/run: the winner returns **201**,
the loser removes its own file and returns **200** with the winner's result.
No DB connection is held during extraction. Concurrent retries of an existing
bill retain both attempts. The current result is the latest validated run
(processed or needs_review), if any, otherwise the latest failed run. A late
failure never replaces a validated result. GET and POST use that same selection;
POST may return another concurrent attempt's successful result. See [ADR-007](adr/007-retry-failed-reupload.md).
PDF validation errors create no records or stored PDFs.

The default fake only recognises the five exact dataset PDFs. Another valid PDF
returns **422 unsupported_fixture**. This tests the application flow, not model
accuracy. No API key is needed. Responses include fields, flags, derived values
and run metadata; raw model text and local storage keys are not exposed.

`BILL_STORAGE_ROOT` defaults to ignored `var/uploads`; `BILL_DATASET_ROOT` defaults
to `dataset`. Both resolve from the working directory. Filenames are generated
by the server; the original upload filename is never stored. Keep the storage
directory with the database when preserving local results.

Files are limited to **10 MiB** and the whole multipart request to **10 MiB +
64 KiB**. Actual bytes are counted even without Content-Length. Multipart parsing
uses temporary files before the sync endpoint runs; accepted PDF bytes are then
loaded for parsing. See [ADR-005](adr/005-upload-api.md) for resource limits, the possible duplicate model
call cost, and the crash window between file rename and DB commit.

```powershell
# API integration tests use the same isolated PostgreSQL schema fixture.
.\.venv\Scripts\python.exe -m pytest tests/db/test_upload_api.py -q
```

### OpenAI upload API (opt-in, spends credit)

Install the updated requirements first. To enable the adapter, set these values
in your ignored `.env`, import them into the server's PowerShell process using
the earlier snippet, and start/restart the Uvicorn factory command above:

```text
BILL_EXTRACTOR=openai
OPENAI_MODEL=<chosen-model-id>
OPENAI_API_KEY=<your-secret-key>
```

Do not paste the key into chat, commit it, or include it in terminal output.
App construction checks local configuration and sends no request. Uploading a
new PDF or re-uploading a retryable failure makes a paid call. BILL_LENS_LIVE
only guards the separate smoke script; it is not required for OpenAI HTTP mode.
The app closes its client on shutdown. Standalone configured_extractor() callers
must call close() themselves.
The adapter sends extracted page text, not the original PDF. SDK retries are zero,
HTTP timeout is 60 seconds, reasoning effort is explicitly `low`, and the output
cap is 4096 tokens including reasoning. `extract-v4` retains these execution
settings and defines [retailer as the customer-facing brand](extraction-contract.md#retailer):
prefer the most complete printed brand over its logo abbreviation; a legal entity
is used only when no brand is printed. A sole unambiguous abbreviation is kept.
Never substitute a distributor, network operator, parent or group. Existing dev
labels and scoring rules are unchanged. The [first v4 evaluation](learning/retailer-brand-evaluation.md)
measured retailer 15/15 on dev and 18/18 on holdout, but one dev amount-due
false extraction was incorrectly marked processed. Real-bill accuracy remains unmeasured.
Authentication, permission, missing model and schema/parameter rejections raise a
safe `OpenAIConfigurationError`; document-specific context/content rejections
remain failed attempts. HTTP maps raised errors to safe 500 internal_error,
without creating a run or changing earlier results. See [ADR-006](adr/006-first-provider.md) for the mapping.

Switching provider/model does not re-extract a successful or non-retryable bill.
Re-upload retries only the three transient codes, once per request; persistent
outages can therefore incur repeated costs if you keep re-uploading.
The standalone smoke script below bypasses persistence and checks all five PDFs
independently; API integration is not needed to run it.

### Manual live smoke check (spends credit)

Only run after explicitly deciding to spend API credit. Set OPENAI_API_KEY
privately first. The command runs **both** a small and mid-tier baseline over all
five golden PDFs (10 calls, no retries). It requires both environment gates:

```powershell
$env:BILL_LENS_LIVE = "1"
try {
    .\.venv\Scripts\python.exe -m scripts.live_openai_check --models gpt-5.4-mini gpt-5.4
} finally {
    Remove-Item Env:BILL_LENS_LIVE -ErrorAction SilentlyContinue
}
```

It prints per-bill status/error/flags, field-match booleans, model names, explicit reasoning effort, token
usage and latency, followed by known token totals and estimated USD cost using
the dated [ADR-006 price table](adr/006-first-provider.md). Cached savings
are excluded; missing usage makes the full estimate unknown. It prints no raw
response or document text and saves nothing automatically. These five synthetic
bills provide a smoke check, not a reliable accuracy benchmark.

**No live API call was made in CI/tests.** The default suite clears API credentials
and live flags and blocks real HTTP transports, even if your shell has a key:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\pytest.exe -q
```

OpenAI was selected because the owner has API credit; no measured provider
comparison over real bills has been performed. Live checks remain explicitly
authorised owner-run steps; ordinary tests do not spend credit.

## M2 evaluation (offline first)

The five original bills are development data. A separate
[six-bill retailer-brand holdout](../dataset/holdout/README.md) covers logo/brand,
abbreviation-only, distributor, legal-entity and parent/group distinctions.
Owner verification of every new PDF/label is required before merge or live use.

```powershell
.\.venv\Scripts\python.exe -m evals.run --extractor fake --repeats 3
.\.venv\Scripts\python.exe -m evals.run --extractor fake --dataset dataset/holdout --repeats 3
.\.venv\Scripts\python.exe -m evals.compare evals/results/<run-a> evals/results/<run-b>
```

The harness records attempts, summaries and reports with per-field outcome counts,
review decisions, per-bill correctness across repeats, input hashes and provenance.
Fake answers come from labels: a perfect fake score is a harness sanity check,
not model accuracy. The existing live smoke script now shares the same scoring.
Results are git-ignored and include raw model output for this synthetic dataset;
do not use real bills without revisiting privacy and retention. See the
[evaluation guide](../evals/README.md) for opt-in live gates, cost assumptions,
comparability rules and the limits of these small synthetic sets. No live evaluation
is part of ordinary tests or this implementation.

## M3 printed-value safeguard

New extractions combine field-derived flags with presence checks on the same
PdfText supplied to the model. All 11 manual labels produce zero new document
flags. Offline replay of 88 preserved attempts reduces silent false acceptance
from **3 to 2**, with **0 new false reviews**: the unprinted 132.66 now routes to
review, while printed amount-due 162.66 remains a known gap. See the
[evidence and limits](learning/retailer-brand-evaluation.md#m3-offline-printed-value-replay).
Dates, roles/context and OCR remain future work. Saved runs keep their original
decisions; existing processed uploads are not silently re-evaluated.

Scoring version is now **2**; the comparison tool rejects scoring-1 results.
The original artifacts remain unchanged. Reproduce the new derived evidence
without an API key or model call (choose a new output filename):

```powershell
.\.venv\Scripts\python.exe -m scripts.rescore_printed_values --output tmp/m3-replay.json
```

## Check documentation links

This offline check covers every inline Markdown link in `README.md` and this
guide, including fragments on linked Markdown files. Both documents use inline
links, not reference-style links. It ignores fenced examples, rejects missing
files/heading anchors and paths outside the checkout, and allows only GitHub PR
URLs as external links (the owner's explicit exception). PR availability is
verified separately with GitHub; this check makes no network or model call.

Save the following as ignored `tmp/check_documentation_links.py`, then run
`.\.venv\Scripts\python.exe tmp/check_documentation_links.py` from the repo root.
On macOS/Linux, use `.venv/bin/python`.

```python
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

root = Path.cwd().resolve()
sources = [root / "README.md", root / "docs/development.md"]

def prose(path):
    text = path.read_text(encoding="utf-8")
    return re.sub(r"(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*$", "", text)

def anchors(path):
    # GitHub heading slugs for the plain-text ATX headings used in these docs.
    used = set()
    for title in re.findall(r"(?m)^#{1,6}[ \t]+(.+?)\s*$", prose(path)):
        title = re.sub(r"[ \t]+#+$", "", title)
        base = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        slug, suffix = base, 0
        while slug in used:
            suffix += 1
            slug = f"{base}-{suffix}"
        used.add(slug)
    return used

local_count = pr_count = 0
for source in sources:
    for target in re.findall(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", prose(source)):
        url = urlsplit(target)
        if url.scheme or url.netloc:
            assert re.fullmatch(
                r"https://github\.com/maxtsec/bill-lens/pull/\d+(?:#issuecomment-\d+)?",
                target,
            ), f"Unexpected external link: {target}"
            pr_count += 1
            continue
        assert not url.query and not url.path.startswith("/"), target
        path = (source.parent / unquote(url.path)).resolve() if url.path else source
        assert path.is_relative_to(root) and path.is_file(), f"Missing file: {source}: {target}"
        if url.fragment:
            assert path.suffix == ".md", f"Unsupported fragment: {target}"
            assert unquote(url.fragment) in anchors(path), f"Missing anchor: {source}: {target}"
        local_count += 1
print(f"Checked {local_count} file/anchor links; {pr_count} allowed PR links (syntax only).")
```
