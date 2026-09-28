# ADR-005: Synchronous upload API and local PDF storage

Status: Accepted (owner selected option B after PR #7 review)

## Context

Persistence and lossless raw-response storage are merged. The next slice connects
PDF validation, the extraction port and PostgreSQL through HTTP. This remains a
local development API using fixture answers; no model extraction accuracy is claimed.

## Decision

Use FastAPI with synchronous POST/GET handlers, sync SQLAlchemy and the existing
sync `BillExtractor`. A service function owns orchestration; routes handle only
multipart reading, dependency injection and HTTP status/headers. `create_app`
accepts an engine, storage root and extractor for integration tests. The default
extractor reads the five golden fixtures; FastAPI's `get_extractor` dependency
can be overridden. No module import opens a database connection.

### Response contract

- `POST /bills`: multipart field `file`; 201 for a new bill **including a recorded
  failed extraction**, 200 for an existing hash. Both include `Location: /bills/{id}`.
- `GET /bills/{id}`: 200 with the same representation, 404 `bill_not_found` for
  an unknown UUID. A malformed UUID or missing file is 422 `invalid_request`.
- Response includes id, SHA-256, stored status/flags, validated fields, timestamps,
  and run id/provider/model/prompt/schema version/error code/token counts/latency.
  Raw response, storage key and original filename are excluded. Raw BYTEA is
  deferred with `raiseload` even on reads; it is not decoded to build a response.
- `billing_days` and `daily_supply_rate_aud` are strings or null. Monetary field
  strings remain exact; unit conversion uses `Decimal`. Supply GST basis remains
  in `fields.daily_supply_rate.gst_basis`; conversion **does not normalise GST**.
  Flags/status are historical stored decisions, not recalculated on GET. Derived
  display values use current code; versioning these calculations is future work.

PDF errors precede an extraction attempt and create no stored PDF, bill or run:

| Error | HTTP | Reason |
| --- | --- | --- |
| `file_too_large` | 413 | File or total request exceeds an acceptance limit |
| `invalid_pdf_signature` | 415 | Bytes do not identify a supported PDF |
| Other `PdfTextError` codes | 422 | PDF cannot satisfy our extraction requirements |
| `unsupported_fixture` | 422 | Valid PDF has no answer in the development fake |

All error responses have a fixed `{"error": code}` shape. Framework validation
errors never echo input or filenames. Unhandled infrastructure/programming errors
return 500 `internal_error`; they are not fabricated extraction attempts.
`UnknownFixture` subclasses the fake's existing `KeyError` behavior, giving HTTP
a precise exception to translate without swallowing unrelated programming errors.

### Two byte limits

Pure ASGI middleware checks Content-Length and counts **actual** body bytes on
every receive, before forwarding to multipart parsing. Missing or falsely small
Content-Length cannot bypass the limit. The envelope cap is 10 MiB + 64 KiB,
including multipart headers, boundaries and any extra form parts. Oversized
declared lengths reject before reading. Invalid/duplicate lengths return 400.

The selected UploadFile is read in chunks of at most 64 KiB with a 10 MiB + 1-byte
sentinel. This independently enforces the 10 MiB PDF limit. Exact boundaries pass.
File extension and the file part's media type do not determine acceptance;
`extract_pdf_text` checks the bytes. A multipart Content-Type/boundary is still
needed for the HTTP envelope.

FastAPI parses multipart **before** invoking the synchronous endpoint. Starlette
spools uploaded files to temporary storage (1 MiB threshold in the pinned version).
This is bounded ingestion, not end-to-end streaming extraction: the endpoint
still builds the accepted PDF bytes in memory for pdfplumber. Server receive
chunks, parser allocations, concurrent requests and PDF CPU/memory are not
bounded by the per-request cap. Starlette 1.7.0 is pinned because its multipart
parser closes temporary files on stream failure; HTTP tests exercise this on a
mid-upload limit exception. Uvicorn/proxy timeouts, aggregate resource limits,
authentication and public deployment are outside this local slice.

### Idempotency and transaction scope

1. Validate PDF and compute SHA-256; query an existing bill in a short session.
2. Close that session and return its connection to the pool. For a new hash,
   call the extractor with **no held DB connection or open transaction**.
3. Derive flags/status; write the PDF to a temporary file under the configured
   storage root, flush/fsync, close, and atomically rename on the same filesystem
   to a server-generated `bills/{uuid}.pdf` key.
4. In one transaction, write Bill and ExtractionRun and build a validated response.
   Return 201 only after commit. The full SHA-256 UNIQUE constraint arbitrates
   simultaneous identical uploads. On `BillAlreadyExists`, roll back the losing
   transaction, remove only its file, and return the committed winning bill (200).

The owner chose **option B: remove the advisory lock** in response to
[Claude's PR #7 review](https://github.com/maxtsec/bill-lens/pull/7#issuecomment-5861692033).
The original session advisory lock held one pooled connection while `_existing`
and the insert needed a second. With enough concurrent distinct uploads, each
request held a connection and waited for another until pool timeout. Avoiding an
idle transaction was insufficient: the checked-out connection still consumed a
bounded resource during a slow model call.

Option B keeps connection ownership confined to short lookups and persistence.
The pre-extraction lookup still avoids another model call for a committed hash.
For the rare simultaneous identical upload, both requests may call the model:
this costs an extra call, and only the winner's attempt is stored. UNIQUE and
the atomic Bill/ExtractionRun transaction still guarantee data integrity: one
bill, one run, and one retained PDF. The loser returns the winner's result even
if the two model outputs differ. There is no 409 `upload_in_progress` response or
`Retry-After` header. Removing the lock also removes its unlock path, so unlock
failure cannot mask an original exception (review should-consider 2).

Committed failed attempts are also idempotent; retrying a provider/prompt is a
separate future operation. Validation/parsing itself may repeat. Writers outside
the HTTP API are subject to the same UNIQUE constraint and loser cleanup path.

### Files and database cannot commit atomically

Write failures remove temporary files. Insert/flush failures roll back rows and
remove this request's PDF. A commit exception is ambiguous: it might have committed
before a lost acknowledgement. Re-query before deleting the PDF; keep it if the
committed bill references it. If verification cannot reach the database, retain
the file. A retry can recover a committed result by hash.

A process crash between rename and commit, unavailable verification, failed
unlink, or host power loss can leave orphan files. There is no distributed
transaction or automatic reconciliation job in M1. Operational cleanup must
compare server keys with committed bills; it must not delete files just because
the uploading request returned 500. The storage root is server-owned and must
not be writable by untrusted users. Local storage also means workers need the
same filesystem; object storage is deferred.

## Alternatives and revisit triggers

- Option A (reuse the advisory-lock connection for lookups/inserts) avoids nested
  checkout but still pins a connection throughout extraction and can starve GET.
  A transaction lock would additionally hold an idle transaction. Neither was chosen.
- Option B (chosen) accepts a possible duplicate model call for simultaneous
  identical uploads in exchange for releasing all DB resources during extraction.
- Option C, **claim-then-work**, is deferred to **M6**: commit a `processing`
  claim, release the connection, extract, then complete the claim. It needs a
  migration, processing status, ownership and recovery of abandoned claims.
  Revisit duplicate-call cost and recording every concurrent attempt there.
- In-memory locks would work for one worker only.
- Object storage plus a reconciliation worker is appropriate when deployment,
  asynchronous jobs or multi-host operation is required.
- The default fake accepts only known fixture hashes. It never invents a default
  answer for an unfamiliar document; real adapters belong to the next slice.

## Verification

TestClient tests run over migrated real PostgreSQL: five golden PDFs, duplicate
and concurrent uploads, all PDF error codes, all extraction error codes, unknown
fixtures, 404, JSONB read validation, lossless NUL/surrogate failure persistence,
file/DB failure cleanup, an external writer race, and lost commit acknowledgement.
Concurrent identical requests are held at extraction until both pass the initial
lookup; they return one 201 and one 200 with identical results and no loser file.
Small-pool tests use `pool_size=2, max_overflow=0, pool_timeout=1` with two and three
distinct uploads. While all extractors block, zero connections are checked out
and GET still completes. Releasing them yields one bill/run/file per upload,
all 201 responses and no pool timeout.
Separate ASGI tests exercise absent/false/oversized lengths and prove multipart
temporary files close when a later chunk crosses the limit. No accuracy claim is
derived from fixture-backed responses.

The pinned Starlette TestClient still supports httpx 0.28.1 but emits a
deprecation warning recommending httpx2. The warning is visible, not suppressed;
migrating the test transport can be handled separately from the application API.

References: [FastAPI UploadFile](https://fastapi.tiangolo.com/tutorial/request-files/),
[Starlette ASGI middleware](https://www.starlette.io/middleware/),
[PostgreSQL session advisory locks](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS).
