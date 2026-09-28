# ADR-005: Synchronous upload API and local PDF storage

Status: Proposed (Phase 2; awaiting review)

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
| `upload_in_progress` | 409 + Retry-After: 1 | Same hash is being processed; retry later |

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
2. For a new hash, acquire a **session-level PostgreSQL advisory lock** using a
   dedicated AUTOCOMMIT connection; recheck the full hash after locking.
3. Call the extractor with **no open database transaction**. The lock connection
   stays checked out, so this costs a connection per in-flight extraction.
4. Derive flags/status; write the PDF to a temporary file under the configured
   storage root, flush/fsync, close, and atomically rename on the same filesystem
   to a server-generated `bills/{uuid}.pdf` key.
5. In one transaction, write Bill and ExtractionRun and build a validated response.
   Return 201 only after commit. Release the advisory lock on all exit paths.

Concurrent requests for an uncommitted hash receive 409, then a retry returns the
existing bill without another extraction. This avoids waiting indefinitely and
works across local API workers. A 64-bit prefix is used for the advisory key;
prefix collisions can cause temporary 409s only. Lookups and database uniqueness
always use the complete SHA-256. Failed attempts are also idempotent; retrying a
provider/prompt is a separate future operation. Validation/parsing itself may repeat.

The hash UNIQUE constraint remains the final defence for writers outside this
API's locking protocol. If such a writer wins, remove only this request's file
and return the winning bill. Lock release failure invalidates the connection so
it cannot re-enter the pool holding a lock. Session pooling/proxies that don't
preserve PostgreSQL sessions are incompatible with this design.

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

- UNIQUE alone prevents duplicate rows but cannot prevent duplicate extractor
  calls. A transaction lock around extraction would hold an idle transaction.
- In-memory locks would work for one worker only. A durable job/reservation table
  would support queued requests and crash recovery but expands this milestone.
- Object storage plus a reconciliation worker is appropriate when deployment,
  asynchronous jobs or multi-host operation is required.
- The default fake accepts only known fixture hashes. It never invents a default
  answer for an unfamiliar document; real adapters belong to the next slice.

## Verification

TestClient tests run over migrated real PostgreSQL: five golden PDFs, duplicate
and concurrent uploads, all PDF error codes, all extraction error codes, unknown
fixtures, 404, JSONB read validation, lossless NUL/surrogate failure persistence,
file/DB failure cleanup, an external writer race, and lost commit acknowledgement.
Separate ASGI tests exercise absent/false/oversized lengths and prove multipart
temporary files close when a later chunk crosses the limit. No accuracy claim is
derived from fixture-backed responses.

The pinned Starlette TestClient still supports httpx 0.28.1 but emits a
deprecation warning recommending httpx2. The warning is visible, not suppressed;
migrating the test transport can be handled separately from the application API.

References: [FastAPI UploadFile](https://fastapi.tiangolo.com/tutorial/request-files/),
[Starlette ASGI middleware](https://www.starlette.io/middleware/),
[PostgreSQL session advisory locks](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS).
