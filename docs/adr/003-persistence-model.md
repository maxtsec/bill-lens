# ADR-003: Bill identity and historical extraction runs in PostgreSQL

- Status: Accepted for Phase 1 after Claude review of commit b669941 and owner approval
- Scope: Persistence foundation only; no HTTP or upload orchestration

Follow-up: [ADR-007](007-retry-failed-reupload.md) adds the append-run write API
and defines current-run/status consistency under concurrent retries.

## Context

The extraction port now produces recordable successes and failures. M1 needs
atomic storage before adding upload endpoints. The owner chose idempotent
uploads, JSONB fields, real PostgreSQL tests, and no original filenames in storage.

## Decision

### Separate identity from attempts

`bills` identifies one PDF by a unique SHA-256. PostgreSQL generates UUID IDs and
timezone-aware timestamps. `storage_key` is an opaque server-generated relative
`bills/<uuid hex>.pdf` key, not a filename supplied by a client. The helper creates
keys without taking user input; the database also constrains their format and
uniqueness. Neither uploaded filenames nor PDF bytes are stored in PostgreSQL.
Phase 1 creates no files; the caller must supply a generated key and positive size.

`extraction_runs` stores provider/model/prompt provenance, the actual raw response,
validated JSONB fields, schema version, error code, flags, status, token counts
and latency. A bill can have multiple runs when an explicit re-extraction feature
is introduced. A duplicate upload currently returns the existing bill and must
not invoke another extraction; the future service will do its early hash lookup
before model work and also handle the database race.

The first run and `bills.processing_status` are written together. Phase 1 has no
append-run API; when adding one, lock the bill and update its status in the same
transaction. Cross-table latest-run consistency is owned by this write API, not
a CHECK constraint. A database trigger refreshes `bills.updated_at` for every
UPDATE, including direct SQL. Runs have no mutable updated timestamp.

### JSONB and historical decisions

Fields are stored exactly as `ExtractionFields.model_dump(mode="json")`: decimal
money remains a string, dates become ISO strings and nullable keys remain present.
SQL NULL means no validated fields, whereas a JSON null object is rejected.
`JSONB(none_as_null=True)` makes that distinction explicit in SQLAlchemy.
`fields_schema_version=1` accompanies fields and is SQL NULL on failures.
`load_fields` validates JSONB on every read and rejects unknown versions; it does
not trust rows merely because they passed database shape checks.

Flags and status intentionally preserve **what the system decided at that time**.
Future rules may change. Reading old runs does not recompute their flags or status.
The write API verifies the caller's flags/status against today's domain rules and
stores a sorted list. The DB enforces array shape and status/empty-flags consistency;
it does not implement Python's field-specific derivation or validate the seven-field
JSON schema. Detailed validation remains at the application boundary.

### Transaction ownership and idempotency

Use sync SQLAlchemy 2.0 with psycopg 3. The caller owns an explicit transaction:

```python
with Session(engine) as session, session.begin():
    try:
        bill = create_bill_with_run(session, ...)
    except BillAlreadyExists as duplicate:
        bill = get_bill_by_hash(session, duplicate.file_sha256)
    bill_id = bill.id
# Commit succeeded before a future HTTP response is emitted.
```

`create_bill_with_run` requires an active transaction without pending writes. A
SAVEPOINT wraps both inserts: a run failure removes its bill too, and a duplicate
hash rolls back only this operation so a subsequent lookup can use the same
session. It flushes but does not commit. It translates only PostgreSQL SQLSTATE
23505 on `uq_bills_file_sha256` to `BillAlreadyExists`; storage-key collisions and
other errors propagate. This is tested with two independent sessions that both
observe the hash as absent before racing to insert. PostgreSQL's default READ
COMMITTED isolation allows the loser to see the committed winner afterwards.
Higher isolation levels and serialization retries are not part of this API yet.

DB CHECKs enforce exclusive fields/error outcomes, required raw responses,
known error/status values, schema-version presence, nonblank provenance,
nonnegative usage/latency, positive sizes, and valid hash/key formats. NOT NULL,
UNIQUE and FK constraints protect identity and required metadata even if future
code bypasses the repository. The migration is hand-written and self-contained;
it never imports live ORM models.

### Local setup and verification

Compose runs PostgreSQL major 17 on loopback with a named volume and healthcheck.
Credentials are explicitly local-only placeholders in `.env.example`; `.env` is
ignored. Python reads `DATABASE_URL`; tests read `TEST_DATABASE_URL`. No implicit
connection, dotenv loader or fallback to SQLite occurs. psycopg's binary extra
provides Windows-compatible libpq without a compiler; versions are pinned in both
dependency files. Transitive versions are recorded in requirements-dev.txt.

Tests create a randomly named schema, apply Alembic migrations, and remove only
that schema afterwards. Each test cleans its committed rows; real commits are
needed to exercise concurrency. An unset TEST_DATABASE_URL visibly skips DB
tests, while an explicitly configured but unreachable DB fails. Tests exercise
downgrade/upgrade, autogenerate drift, every CHECK/UNIQUE through SQL and ORM,
NOT NULL/FK constraints, JSONB round trips, failed attempts and rollback behavior.
Alembic's ordinary autogenerate comparison does not cover all CHECKs or triggers;
named constraint coverage and timestamp behavior are verified separately.

## Alternatives and trade-offs

- Typed columns for all bill fields would aid SQL aggregation but duplicate the
  evolving extraction schema. JSONB is adequate until queries justify columns.
- Storing only the latest fields on Bill loses failed attempts and model/prompt
  history. Bill and ExtractionRun separate file identity from attempt evidence.
- An application-only duplicate lookup has a race. UNIQUE is the final arbiter.
- SQLite tests would not verify PostgreSQL JSONB, CHECK semantics or concurrent
  unique enforcement. Docker adds startup cost but exercises the actual engine.
- Recomputing flags on read silently rewrites historical decisions. Persisting
  them adds redundancy with a deliberate audit purpose.
- A generic repository framework or async stack adds abstraction without this
  milestone needing it. Plain functions and synchronous sessions fit the port.
- Raw responses can contain personal data or malicious text. They remain internal
  data; production retention/access policies are still needed. SQLAlchemy hides
  bound parameters in its errors, but callers must not log raw DB exceptions.
- The initial schema used PostgreSQL text for raw responses, which could not
  store NUL or malformed Unicode. [ADR-004](004-lossless-raw-response.md) describes
  migration 0002 to lossless BYTEA storage and rejection of control characters
  in extracted retailer names before the upload API is added.

## When we will revisit

Revisit typed columns/indexes when a measured SQL query needs them, schema-version
migrations when extraction shape changes, and async connections when concurrency
requirements justify them. Re-extraction needs atomic latest-run selection and
status updates. File storage/cleanup, upload limits, HTTP mappings and dependency
injection are **Phase 2**, which starts only after this PR is merged. Authentication,
customer isolation, production secrets, retention and backups remain future work.

References: [SQLAlchemy transactions and SAVEPOINTs](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html),
[Alembic autogeneration](https://alembic.sqlalchemy.org/en/latest/api/autogenerate.html),
[psycopg binary installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).
