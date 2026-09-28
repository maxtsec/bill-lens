# ADR-004: Lossless raw-response storage before the upload API

- Status: Accepted after Claude review of 8ecba16 and owner approval
- Scope: Contract validation and persistence of special characters; no HTTP
- Supersedes: ADR-003's raw-response `text` limitation

## Context

PR #5 review found that an escaped NUL in a retailer name passed the extraction
schema, then failed during PostgreSQL JSONB insertion. A literal NUL or lone
surrogate in raw text also failed persistence, losing the attempt. Rejecting bad
fields alone does not solve this: failed attempts still retain raw evidence.

## Decision

### Validate extracted names

Reject Unicode categories `Cc` and `Cs` in `retailer`, currently the only free-text
extracted field. Decimal/date/enum strings already have constrained syntax.
The shared extraction gate returns `invalid_output`, no fields, and the exact
raw response. Do not strip, replace, normalize or invent a null retailer. Accept
ordinary Unicode including non-BMP characters and combining marks unchanged.
The generated schema description and extraction-contract document specify this.

M2 evaluation should count how many `invalid_output` results come from whitespace
controls (such as a newline in a multi-line retailer name) before deciding whether
to relax this rule; the current outcome remains a failed attempt with raw evidence.

This tightens validation without changing the seven-field JSON shape or its
version. Previously stored names with other control characters are not rewritten;
they now fail validation on read and need explicit handling if encountered.

### Store the port's raw string losslessly

Migration `0002` changes `extraction_runs.raw_response` from `text` to `bytea`.
The fixed encoding is **UTF-8 with Python's `surrogatepass` error handler** for
both encoding and decoding. `RawResponseText`, a small SQLAlchemy TypeDecorator,
performs this only at the DB boundary. The port and ORM attribute remain
`str | None`; JSONB fields and failure/status CHECKs are unchanged.

- SQL NULL remains None; empty response is an empty byte string, not NULL.
- NUL is preserved as byte 00.
- Lone surrogate code points are preserved, without replacement characters.
- Two adjacent surrogate code points remain distinct from a single non-BMP
  character. They are not silently combined by a JSON round trip.
- Literal escape spellings, whitespace, combining marks and line endings survive.
- Explicit provider failures keep their error code even with unusual raw text.

The schema revision defines this encoding for every row; there is no heuristic
decoder or mixed encoding flag. A future format change requires a migration.
Ordinary Unicode uses normal UTF-8 bytes. Surrogate-containing bytes must be
decoded with surrogatepass, not advertised as standards-compliant UTF-8 text.
Unrelated invalid bytes written by direct SQL raise a decoding error on read;
the adapter never guesses or repairs corrupt storage.

This preserves **the Python string supplied by the extraction port**, not a
provider's original transport bytes (which the port does not receive). This is
raw response evidence, not PDF binary storage. No PDF bytes or filenames are
added to the database. Raw data remains untrusted and must not be logged or
returned by the future public bill response by default.

### Migration and rollback

Upgrade uses `convert_to(raw_response, 'UTF8')`: existing PostgreSQL text is
representable by this codec, so existing strings and NULL migrate losslessly.
The initial migration is unchanged. Alembic tests exercise populated upgrades,
normal-text downgrades and upgrade again, plus base/head and drift checks.

Downgrade uses `convert_from(raw_response, 'UTF8')`. If a row contains NUL or
surrogate bytes, PostgreSQL cannot represent it as text and aborts the
transaction. Tests verify both the revision and raw evidence remain at 0002.
Do not delete, replace or silently discard such rows to make rollback succeed.
Any rollback requiring a different evidence format needs an explicit migration.
Apply migrations with the application stopped; old code expects a text column.

## Alternatives and trade-offs

- Stripping/replacing invalid characters destroys evidence and was rejected.
- A special failure that omits raw text makes the loss visible but still loses
  evidence. BYTEA retains it instead.
- JSON-escaped text is readable but adds quoting and decoding rules; typical
  JSON decoding also combines surrogate pairs. We chose an exact code-point
  encoding without JSON interpretation.
- Base64 could retain encoded bytes in text but adds size and another encoding
  layer. PostgreSQL BYTEA and SQLAlchemy already support binary values.
- Separate text and binary fallback columns create two sources of raw evidence
  plus presence/encoding invariants. One column keeps the existing NULL checks.
- Direct SQL readers now get bytes and must use the documented codec. Arbitrary
  raw bytes are not meaningful queryable text; structured fields remain JSONB.

## Verification and scope limits

Before the fix, four DB regression cases failed: escaped NUL was accepted as
success, while literal NUL and high/low surrogate strings could not be persisted.
After the fix each commits exactly one Bill and one failed ExtractionRun, with
`invalid_output`, SQL NULL fields, and exact raw-text reload in a fresh session.
Tests cover every Cc code point, surrogate range boundaries, known codec bytes,
NULL vs empty, provider failures and populated migration/rollback behavior.

`ExtractionAttempt` limits input/output token counts and latency to `0..2**63-1`,
matching PostgreSQL BIGINT. Optional token counts may still be None. Values at
`2**63` are rejected before persistence; tests verify the maximum can be committed
and reloaded for both successful and failed attempts. These are adapter metadata
errors (ValueError), not model-output `invalid_output` failures. No clamping occurs.

This closes the model-output character and metadata numeric-range gaps. It does
not make storage infallible: outages, disk limits, corrupted DB bytes and invalid
adapter provenance remain errors. The rollback test injects a run-mapping defect
that violates a real DB CHECK after the bill INSERT to verify atomic rollback.
HTTP error policy, quotas, provider wire-byte capture and upload handling are
future work. Phase 2 has not started.

References: [Python codec error handlers](https://docs.python.org/3/library/codecs.html#error-handlers),
[PostgreSQL binary conversion](https://www.postgresql.org/docs/17/functions-binarystring.html),
[SQLAlchemy TypeDecorator](https://docs.sqlalchemy.org/en/20/core/custom_types.html#sqlalchemy.types.TypeDecorator).
