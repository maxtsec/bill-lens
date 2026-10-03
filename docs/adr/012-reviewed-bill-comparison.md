# ADR-012: Compare two reviewed bill snapshots

## Decision

The English workbench offers a read-only comparison of two different bills.
Users select a baseline (A) and comparison bill (B), and acknowledge that both
are for the same home. The current contract has no meter or premises identifier;
the app cannot infer household identity from a retailer name. This acknowledgement
is required for each newly selected pair and is not stored as a verified identity.

`GET /comparisons?baseline_id=...&comparison_id=...&same_household=true`
reads both bills and their latest applicable human reviews inside one PostgreSQL
repeatable-read transaction. A missing review returns 409, including when a new
successful extraction invalidated a review since the selection list loaded.
The response includes both review snapshots and their revision/source identities.
Failed extraction bills with an applicable manual review remain eligible.
No comparison, review or extraction record is written by this endpoint.

## Calculations and limits

- Current-period charges and total usage use the latest reviewed fields, not
  original extraction values or the original response's derived fields.
- Average daily usage divides total imported kWh by inclusive reviewed start/end
  dates. Missing/reversed dates, or a conflict with stated billing days, make the
  daily figure unavailable. Valid dates suffice when stated days are absent.
- Daily supply rates are converted from cents to AUD exactly. Their difference
  is available only when both GST bases are known and equal. No GST rate or tax
  adjustment is assumed; the individual rates and bases remain visible.
- Absolute change is B minus A. Percentage change is `(B - A) / A * 100` only
  when A is positive. Zero/credit baselines keep their absolute change but have
  no percentage. Missing values remain missing, never zero.
- Python Decimal arithmetic calculates changes before display rounding, with
  precision sized for the input strings. Display uses half-up rounding: two
  places for charges/usage, four for supply rates, one for percentages. Tiny
  nonzero changes render with a less-than threshold rather than implying equality.

The UI highlights average daily usage for unequal period lengths. It also shows
warnings for overlapping periods, reverse chronology, manual entry after failed
extraction, and unresolved automated flags. Human review is not proof of accuracy;
remaining flags do not automatically suppress a known value. Source links allow
the user to inspect or revise each bill. Changing a selection hides the previous
result and cancels stale UI responses. Comparison always reloads current reviews.

These are descriptive differences, not a tariff comparison, savings forecast or
explanation of causation. Seasons, occupancy, tariff changes and credits can affect
the figures. No household history, meter matching, charting service or model call
is introduced. The existing local-only access model remains unchanged.

## Validation

Unit cases cover unequal periods, inclusive leap-day boundaries, missing values,
date/day conflicts, zero and credit baselines, GST incompatibility, exact cents
conversion, long decimals and unrounded differences. PostgreSQL tests cover
review eligibility, latest corrections, read-only behavior, new-run invalidation,
and a concurrent review commit between reading the two bills. Frontend tests
exercise household acknowledgement, stale responses, paged options and formatting.
