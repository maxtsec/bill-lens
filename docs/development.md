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
- [Offline presence and role replays](#m3-presence-and-current-amount-safeguards)
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

The [text baseline inspection](../dataset/text-baseline.md) records the observed reading order. The owner has verified all five PDFs against their labels. In the re-review supplied by the owner on 2026-09-27, Claude approved main commit `0bc489a` (original PR #2 branch: `f4e5cd1`), confirming both must-fix issues were resolved and all 91 tests passed through three pytest entry points. The owner completed verification of `bill_001`, `bill_003`, and `bill_004` on 2026-09-27 and authorized rebase merge. [PR #2](https://github.com/maxtsec/bill-lens/pull/2) records that historical dataset milestone; the upload-to-JSON API is now implemented as described below.

## PR workflow and commit references

Start each scoped change from up-to-date main on a new branch, include relevant
tests, and open a draft PR for review. Resolve review findings before the owner
authorises rebase merge and branch deletion. Rebase merge changes commit IDs:
after merge, documentation and new evidence should cite commits reachable from
main or the PR URL. Preserved evidence already recording a branch ID stays
unchanged; document its main counterpart alongside it, as in the
[fuzzing commit mapping](learning/pdf-boundary-fuzzing.md#commit-identities-after-rebase-merge).

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

See the [bill workbench](#bill-workbench-and-human-review) for the local review UI.

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

## M3 presence and current-amount safeguards

New extractions combine field, presence and current-amount-label checks on the
same PdfText supplied to the model. All 11 manual labels produce zero role
flags. Presence reduced silent false acceptance **3/88 → 2/88**; the role check
then reduces **2/88 → 0/88**, with **0 new false reviews** in either replay.
Both printed 162.66 distractors now reach review, without repairing values.
See the [evidence and limits](learning/retailer-brand-evaluation.md#m3-offline-current-amount-role-replay).
Vocabulary and column ambiguity remain; dates and OCR are not checked. Saved
runs keep their original decisions; stored uploads are not silently re-evaluated.

Scoring version is now **3**; comparisons reject scoring-1 and scoring-2 results.
The original artifacts remain unchanged. Reproduce the derived evidence
without an API key or model call (choose a new output filename):

```powershell
.\.venv\Scripts\python.exe -m scripts.rescore_printed_values --output tmp/m3-replay.json
.\.venv\Scripts\python.exe -m scripts.rescore_current_amount_roles --output tmp/m3-role-replay.json
```

The first command explicitly reproduces historical scoring-2 decisions. The
second verifies that baseline and compares scoring 2 to 3; neither calls a model.

## Check documentation links

The offline [link test](../tests/test_docs_links.py) checks root Markdown files
and all Markdown under `docs/`, `dataset/` and `evals/`. It excludes `.venv/`,
`tmp/`, `var/` and `evals/results/`, checks relative targets and Markdown heading
anchors, and ignores fenced examples. Negative fixtures cover missing targets
and anchors, duplicate headings, inline code and the external-link allowlist.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_docs_links.py -q
.\.venv\Scripts\pytest.exe tests/test_docs_links.py -q
```

External links are never fetched by the test. Official documentation hosts are
listed explicitly; GitHub links are limited to this project and pdfplumber's
official documentation repository. New destinations require a deliberate
allowlist change. Check external availability separately when editing sources.
The former copy-and-run checker is now replaced by this single implementation.

## Bill workbench and human review

After installing requirements, importing local configuration, starting PostgreSQL
and running `python -m alembic upgrade head`, start the API as above and open
`http://127.0.0.1:8000/`. The English workbench runs in the same process.
Use the five synthetic `dataset/bill_*/bill.pdf` fixtures with the default fake.
Arbitrary real bills are not supported by the fake extractor.

The list shows effective values from the latest applicable human review, falling
back to the current extraction. Filter automatic status and human-review status
independently. Open a bill, inspect its page preview or original PDF, edit any
fields, enter a reviewer name and explicitly acknowledge the PDF before saving.
Blank values are stored as null. Use "Show originally extracted values" to compare
the editable fields with the source extraction. Each saved version appears in the
expandable history. Remaining warnings stay visible. History uses revision cursors
so new reviews submitted while paging do not duplicate older entries.

A 409 conflict means another review or current extraction changed since loading.
The editor retains your input; note any intended changes, reload the latest version,
and reconcile before submitting again. A failed extraction can also be manually
reviewed; its original failed status stays unchanged.
Further failed retries preserve that review, even if the bill has never had a
successful extraction. A new successful extraction returns it to pending.

New endpoints:

| Endpoint | Result |
| --- | --- |
| `GET /bills` | Paginated bill details and global review counts; `limit`, `offset`, `status`, `review_state` filters |
| `GET /bills/{id}/detail` | Original extraction plus applicable review/effective fields |
| `GET /bills/{id}/pdf` | Original PDF with opaque filename |
| `GET /bills/{id}/preview/{page}` | One-based PNG page and `X-Page-Count` header |
| `GET /bills/{id}/reviews` | Newest-first history; pass `next_before_revision` as `before_revision` for the next page |
| `POST /bills/{id}/reviews` | Append confirmation/correction with both version tokens |

The existing GET-by-id and upload response formats stay unchanged. Reviewer names
are self-reported local labels. There is no authentication; keep the server on
loopback. See [ADR-011](adr/011-human-review-workbench.md) for concurrency,
state semantics, preview limits and migration rollback implications.

Run the frontend regression tests with Node.js (no npm dependencies):

```powershell
node --test tests/js/workbench.test.cjs
```

These cover safe transport errors, single-request list refreshes, empty failed-bill
confirmation text, and cursor-based history loading, including overlapping requests.

## Compare reviewed bills

Open **Compare** in the workbench and select two reviewed bills for the same home.
Confirm the household checkbox, then select **Compare bills**. Review at least two
bills first if the picker is empty. The results compare current-period charges,
total usage, average daily usage and daily supply rates; each source links back to
its review page. Use **Swap bills** to reverse the baseline, then compare again.

The read-only API is `GET /comparisons` with `baseline_id`, `comparison_id` and
`same_household=true`. No migration or paid extraction is required. The response
contains review provenance, decimal-string metrics and explanations for unavailable
differences. See [ADR-012](adr/012-reviewed-bill-comparison.md) for calculation rules,
rounding, GST constraints and concurrent-review behavior.
