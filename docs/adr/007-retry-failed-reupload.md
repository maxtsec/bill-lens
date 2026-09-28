# ADR-007: Retry failed uploads while preserving extraction history

Status: Accepted (owner selected option A and requested acceptance after PR #9 review)

## Context

PR #8 review demonstrated that caching a rate-limited attempt by file hash made
an outage permanent for that PDF. The owner selected option A in a separate PR:
retry transient failures on re-upload, keep old runs, then enable OpenAI in the
upload API. This supersedes ADR-005's unconditional reuse of failed results and
fulfils ADR-006's API-wiring prerequisite. This is unrelated to the option A/B/C
advisory-lock choices in ADR-005; no advisory lock is reintroduced.

## Decision

### Retry policy and HTTP semantics

| Current result | Re-upload |
| --- | --- |
| processed or needs_review | Return current result, no extraction |
| failed: rate_limited, timeout, provider_error | Extract once and append a run |
| failed: refused, truncated, invalid_output | Return current result, no extraction |

Re-upload is the explicit retry action. There is no automatic/background retry,
backoff loop or new endpoint. Non-retryable outcomes concern the document or
model output rather than a temporary outage; repeating them by default could
spend credit without fixing the cause. M2 evidence may change this classification.
The existing adapter also maps context_length_exceeded to provider_error, so it
is retryable under this coarse policy; finer error reasons are future work.

An existing bill always returns **200**, whether reused or retried; its ID,
created_at, hash and storage key remain unchanged. A new bill still returns
**201**, including a recorded failure. Both return Location. Every retry whose
extractor returns an ExtractionAttempt appends it without changing prior runs.
Exceptions raised by configuration/programming failures are not attempts: the
HTTP boundary returns safe 500 internal_error and leaves history unchanged.
Storage/DB failure can prevent persistence; no exactly-once delivery is claimed.

### One definition of current run

Select the latest run with validated fields (processed **or needs_review**) if
one exists; otherwise select the latest failed run. Within each group, order by
created_at descending, then UUID descending as a deterministic historical tie
breaker. A needs_review result is a completed extraction and prevents retries,
even if an older run was processed. This policy prefers the latest validated
result, not the result with the fewest flags.

`current_run_statement` implements this rule for both status updates and HTTP
reads. Bill.processing_status mirrors its selected run. POST/GET returns that
run's fields, flags and metadata, which may differ from the attempt just made
if a concurrent retry already succeeded. The response joins Bill and the chosen
run in one SELECT snapshot, refreshing any Bill cached by an earlier lookup.
Raw response stays deferred and is never included in HTTP output.

This avoids a migration/current_run_id pointer and its cross-table integrity
requirements. It uses the existing bill_id index; a history-specific index can
follow if measured run counts justify it. Direct SQL or future writers must use
the same write protocol to preserve cross-table status consistency.

### Concurrency, history and timestamps

1. Validate the PDF and read current result in a short session.
2. Release all DB connections/transactions before calling the extractor. A
   request which observed a retryable failure may continue even if another retry
   completes meanwhile.
3. After extraction, open a short transaction and lock the existing Bill with
   SELECT FOR UPDATE. Append this attempt, recompute current run and update
   processing_status atomically. Return only after commit.
4. Keep the existing PDF; retry never writes, renames or deletes a stored file.

Concurrent retries **both persist**, including a late failure after a success.
The late failure cannot make the current result failed. Two validated concurrent
results are ordered by their append transaction, not request arrival or model
completion time. Each response represents the current run at its transaction;
a later successful commit can legitimately change a later GET.

The row lock also protects the interval between selecting current run and
updating Bill status. Without it, a failed append could select failed, pause,
then overwrite status after a successful append commits. The regression test
pauses precisely before the failed UPDATE, observes the successful backend
waiting on it via pg_blocking_pids(), and verifies both final statuses are
processed. Mutation verification removed with_for_update(): the successful
append finished while failure was paused, leaving Bill status failed but current
run processed, and the regression test failed. Restoring the lock passes.

PostgreSQL now() records transaction start time, so it is unsuitable for ordering
writers that waited for a row lock. Under the lock, a new run receives the greater
of clock_timestamp() and the latest existing timestamp plus one microsecond.
This keeps append order strict even at timestamp ties or after a backwards clock
adjustment. created_at describes persistence order, not provider request start.
Bill is explicitly updated even when status is unchanged; the existing trigger
advances updated_at for appended history. No timestamp/ID of an old run changes.

The append helper uses a SAVEPOINT and caller-owned outer transaction, matching
the existing create helper. Run insert and Bill update roll back together. A
lost commit acknowledgement may mean the append committed even when HTTP returns
500: the next re-upload reuses a committed success, or can add another attempt if
the committed current result is still retryable. No file cleanup runs for retries.

### Difference from the first-upload race

For a previously absent hash, ADR-005's UNIQUE race is unchanged: concurrent model
calls can occur, but only one bill/run/file is kept. The loser deletes only its
own file and returns the winner. For an **existing bill**, all completed retry
attempts are retained because its row can arbitrate short append transactions.
Provider-call counts and run counts can therefore still differ on first upload,
as well as crashes/DB failures. M6 cost tracking must account for this difference.
Claim-then-work and abandoned-claim recovery remain M6 work. No DB connection is
held during provider latency, including with a pool smaller than request count.

### OpenAI configuration and ownership

create_app now uses configured_extractor(): BILL_EXTRACTOR defaults to fake;
openai requires OPENAI_MODEL and OPENAI_API_KEY. Local configuration errors fail
at construction, without a provider call. The app closes OpenAI clients it owns
at shutdown, and disposes an owned engine even if client cleanup fails. Injected
extractors/engines remain caller-owned. Failure constructing the extractor also
disposes an engine the factory created.

OpenAI uploads send PDF-extracted text and spend credit. BILL_LENS_LIVE guards
only the standalone smoke script, not the HTTP API. The API stays local-only and
unauthenticated; this change does not deploy or launch it. Defaults and the test
suite remain fake/offline. No new live provider calls are part of this PR.

## Verification

Real PostgreSQL tests cover all retryable/non-retryable codes, recovery to both
processed and needs_review, repeated failure, immutable historical evidence,
single-file reuse, concurrent success/failure in both completion orders and two
concurrent successes. Each committed response is checked against GET and Bill
status. A future-timestamp case tests strict append ordering.

Three distinct retries block in extraction with pool_size=2, max_overflow=0 and
pool_timeout=1; zero connections are checked out and GET still progresses. Existing
first-upload concurrency and small-pool tests remain. Rollback and lost-commit-ack
tests verify history/file preservation. Configured OpenAI + actual SDK MockTransport
exercises HTTP upload, a 429 then recovery, and authentication failure without
persisting a fabricated attempt. Credentials and real transports remain disabled
by the default test fixture. These tests establish workflow, not model accuracy.
