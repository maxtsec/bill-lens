# ADR-011: Local bill workbench and independent human reviews

## Decision

Serve a Traditional Chinese workbench from the existing FastAPI app at `/`.
It lists bills with bounded offset pagination, independent extraction-status
and human-review filters, PDF page previews, editable fields and review history.
No frontend build service or external asset host is required.

Human review is an additional decision, not a rewrite of an extraction run.
`bill_reviews` stores full field snapshots, reviewer-supplied names, optional
notes, the source run, increasing per-bill revisions and automatically recomputed
flags. Existing `GET /bills/{id}` and upload responses retain their original
extraction contract. `GET /bills/{id}/detail` adds effective fields and review state.
The existing derived `billing_days` and `daily_supply_rate_aud` still describe
the original extraction; consumers of effective fields must derive from that
snapshot rather than mix the two versions.

`reviewed` means a person acknowledged the PDF and saved a review. It does not
mean every field is present, every warning is resolved, or the result is correct.
Null values, zero usage, signed credits, original decimal precision and unknown
GST basis remain representable. The UI shows original values beside the editor
and keeps the original extraction status visible. No arithmetic repairs are made.

## Concurrency and provenance

Every POST to `/bills/{id}/reviews` requires the displayed `source_run_id` and
`expected_review_id` (explicit null for the first review). After reading and
validating the saved PDF without holding a DB connection, the writer takes the
same Bill row lock used by extraction retries. It checks both tokens, appends
one revision and updates the bill timestamp within one transaction. Stale
clients receive 409 `review_conflict`; their form input is retained for reconciliation.

The action is `confirmed` when the submitted fields match the previous effective
fields, otherwise `corrected`. Records have no update/delete API. The source
run, raw response, extracted fields, flags and status are untouched. Reviewer
names are local labels, not authenticated identities. No account or ownership
system is introduced; the service remains for loopback local development.

When a different extraction run becomes current, the old human review remains
in history but no longer supplies effective fields; the bill returns to pending.
A late failed retry which does not become current does not invalidate its review.
List count/filter/detail queries and detail reads use repeatable-read snapshots
so each response describes a consistent version. Offset pages can shift between
requests when new bills arrive. Pages are bounded to 100; the local workbench
uses 20. History uses the same bounds.

## PDF preview

`GET /bills/{id}/pdf` serves the stored original with an opaque download name.
Resolved paths must remain inside the storage root. Review saves additionally
check the stored file hash before deriving flags. Missing PDFs prevent review.

Some embedded browsers do not display PDF iframes. `/bills/{id}/preview/{page}`
therefore renders a one-based page as PNG with `X-Page-Count`. PDFium calls are
serialized per worker because the native library is not thread-safe. Input size
and page count use the existing acceptance bounds; preview sides are capped at
approximately 1600 pixels. The preview is not OCR and never changes extraction.
These limits do not provide parser CPU/memory isolation. Responses are not cached
by the browser, and raw model output is never sent to the workbench.

## Migration and validation

Migration `0003` adds the review table without backfilling or changing any bill
or extraction record. Downgrading below `0003` drops human review history; back
up that table before any intentional downgrade. Normal startup upgrades only.

Real PostgreSQL tests cover confirmations with unresolved flags, corrections,
decimal preservation, history pagination, stale and cross-bill tokens, simultaneous
reviewers, new-run invalidation, invalid inputs, missing/tampered PDFs, preview
selection, unchanged extraction evidence and schema drift. Browser verification
also exercises the visible confirmation/correction flow on synthetic fixtures.
