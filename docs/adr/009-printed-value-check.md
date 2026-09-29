# ADR-009: Review extracted values not printed in the source text

Status: Accepted

## Context

The contract requires extracting printed values. Previously the prompt was the
only check for that requirement. In the 20-repeat v4 bill_002 study, two valid
JSON responses suppressed review: 162.66 (printed amount due, wrong role) and
132.66 (a reconstructable total not printed anywhere). A schema validates shape
and domain constraints, not source support.

## Decision

Add pure `derive_document_flags(fields, document: PdfText)` and one shared
`derive_review_flags(fields, document)` returning the union of document flags
and existing `derive_flags(fields)`. Any flag yields needs_review. Uploads,
retry attempts, evaluation and the owner-run smoke check use that union.
No new provider call, prompt change, field repair, replacement or nulling occurs.
Keeping the returned value and raw response preserves evidence for human review.

Check non-null current amount, usage, supply-rate value, stated days and retailer.
Null fields add no document flags; existing missing-field rules still apply.
Dates remain out of scope. ExpectedLabel accepts the five new codes through the
shared ReviewFlag type, but its seven-field wire schema and all labels stay unchanged.
The outbound ExtractionFields JSON schema and extract-v4 prompt are unchanged.

### Exact matching rules

- Read the same page text passed to the model, not the PDF generator, labels,
  raw PDF bytes or a second extraction/OCR implementation.
- Extract whole ASCII decimal tokens; no substring inside a larger decimal.
  Compare with Decimal, so 108.07 equals 108.070. Commas are accepted only as
  groups of three digits (1,234.50); malformed grouping is not repaired.
  A trailing full stop or comma is sentence punctuation when not immediately
  followed by a digit: `90.15.` and `90.15, due tomorrow` both support 90.15.
  A dot/comma followed by a digit must belong to the numeric grammar; malformed
  tokens such as `1.2.3` and `1,23.45` cannot supply partial matches.
  Decimal construction and sign changes preserve precision without rounding.
- Currency/unit decorations such as AUD, $, cents symbol, c, c/day, /day and
  kWh sit outside the token. No conversion is done: compare the extracted
  supply rate in its claimed printed unit, never the derived AUD/day value.
  Presence does not verify that the surrounding unit or GST basis is correct.
- A token is negative when ASCII `-` or Unicode `−` is attached directly to
  the digits or their AUD/$ prefix (`-4.00`, `-$4.00`, `−AUD 4.00`); enclosed
  in parentheses with optional AUD/$ before the digits; or adjacent to case-insensitive `CR` or
  `credit`. Prefix credit may have `:` or `=` and optional AUD/$, e.g.
  `credit: AUD 4.00`; suffix credit follows digits, e.g. `4.00 CR`.
  Horizontal spaces/tabs are allowed after a currency prefix, inside parentheses
  and between credit markers and values, but never immediately after a minus.
  A spaced ` - ` or ` − ` is a separator, so `amount - AUD 90.15` supports
  positive 90.15 only. Markers must be on the same line, with no intervening
  words or other number. A distant credit
  heading or a marker on the next line/page does not change a number's sign.
- A negative extracted value requires a matching negative token. A positive
  value does not match a credit-only token. If both signed and unsigned copies
  are printed, each may match independently. Decimal treats signed zero as
  zero. This stops a printed credit silently supporting a positive debit while
  retaining a presence-only check rather than guessing accounting roles.
- Retailer uses Unicode casefold and whitespace collapse on both strings,
  then substring matching. Line breaks/extra spaces in the document are fine.
  No legal-suffix removal, alias expansion or fuzzy repair is performed.

Numeric candidates and local sign context are scanned per line/page; retailer
normalisation uses the joined PdfText. The implementation inspects gaps between
numeric tokens rather than repeatedly copying entire prefixes of a long line.

### Repository integrity without document text

The service is responsible for deriving document flags before persistence.
The repository revalidates fields, recomputes all field-derived flags and
requires every one. Additional codes must be known document flags for non-null
fields. Unearned field-derived flags, unknown codes, document flags on null
fields and inconsistent status remain rejected. Failed attempts still require
empty flags and failed status. Supplied valid document flags are saved, not
dropped while recomputing field rules; the same validation covers create/append.

The repository cannot prove that a caller supplied all and only the correct
document flags without text. It deliberately trusts that part of the application
boundary, rather than weakening field checks or pretending to recompute it.
No database migration is required: review_flags is already a JSON array.

Existing stored runs keep their original decisions; GET and duplicate-upload
reuse do not silently re-extract or rewrite history. New extractions (including
already-supported retries of transient failures) use the new rule. Re-evaluating
existing processed records is future explicit work, not a side effect here.

### Evaluation semantics and evidence

`score_attempt` now requires PdfText, preventing callers from silently falling
back to field-only decisions. SCORING_VERSION becomes **2**; harness version
remains 1 and field correctness rules are unchanged. `evals.compare` rejects
old-vs-new scoring runs. Historical scoring-1 artifacts are not rewritten or
relabelled; use their original checkout for their original comparison commands.

The offline replay script verifies artifact and PDF/label hashes, rebuilds saved
responses through build_attempt, checks their old field-only decision, and
derives the new union. It reports false acceptances, new false reviews and all
flag/status changes in a separate evidence file. Implementation fingerprints
normalise source newlines to LF for portability; source artifact hashes remain
byte-exact. All 88 preserved attempts are included with zero API calls.

## Limits and next candidate

Presence is necessary, not sufficient. 162.66 still passes because it is printed
in the wrong role; 132.66 now routes to review. Common small integers such as
30 may appear in dates, quantities, identifiers or unrelated lines. A retailer
substring may be part of another printed name. A wrong unit can accompany a
matching number. Duplicate numbers cannot be attributed to a particular field.

Dates require separate format-aware matching. This initial grammar does not
handle scientific notation, decimal-comma locales, leading decimal points,
space-grouped thousands or arbitrary punctuation/sign layouts; these can cause
false reviews. Text extraction may split digits, signs, units or words, reorder
columns, or omit a printed value. Credit markers split across lines are a known
conservative false-review risk. Future OCR introduces more such errors. Prompt
injection can also plant values in text; presence checking is not a security
boundary. A match never upgrades a value to verified or fixes its role.

The next candidate is evidence spans **plus label/context verification** for
which printed number represents the current-period amount. Spans alone still
match the amount-due distractor. No such safeguard is implemented by this ADR.
