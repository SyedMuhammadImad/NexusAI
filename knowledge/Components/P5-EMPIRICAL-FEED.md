# Empirical HistData Feed Calendar

Authority: ADR-016, explicit owner empirical-inference approval, 2026-09-15.
Model version: `HISTDATA_FEED_CALENDAR_2021_V1`.
Derivation: `weekly-minute-UTC-annual-and-quarter-v2`.
Aggregation: `all-expected-M1-present-empirical-v1`.

## Inference, Not Exchange Hours

Each instrument is independently derived from its immutable complete 2021 M1
source snapshot. Weekly slots use Monday 00:00 UTC as origin, preserving HistData
source fixed UTC-05 provenance. No local timezone, exchange calendar or inferred
DST dates are consulted. Whole-year source/quarter statistics are persisted.

The initial annual-only profile found 2880 never-observed weekly slots in each
instrument. This is insufficient for seasonal breaks. The final model compares
both the whole year and fixed calendar quarters: at least 48 complete observed
weeks/year, at least 12 per quarter, and 100% absence within the relevant period.
Any observation in a candidate slot vetoes closure for that period. All 51 complete
2021 weeks and partial boundary weeks contribute observations; partial weeks cannot
inflate the complete-week confidence denominator. An isolated missing occurrence
does not become a closure. Confidence counts, policy, source hash and dates are
part of the calendar ID. This is a conservative threshold, not an unknown-gap budget.

Actual zero-observation weekly-slot counts by quarter (out of 10080 slots):

| Feed | Q1 | Q2 | Q3 | Q4 |
|---|---:|---:|---:|---:|
| XAUUSD | 2880 | 3180 | 3180 | 2880 |
| XAGUSD | 2880 | 3180 | 3180 | 2896 |
| WTIUSD | 2881 | 3180 | 3180 | 2887 |

Each quarterly count includes the 2880 whole-year always-absent slots. Minute
identities and observed-count arrays, not just these totals, are persisted. Q1/Q4
mixed-season daily intervals that fail this test remain UNKNOWN; they are not
relabelled solely because a seasonal transition would be convenient.

Full UTC dates absent across all three feeds, but containing expected minutes,
can be labelled EMPIRICALLY_OBSERVED_HOLIDAY_OR_SPECIAL_CLOSURE. Each exception
references all three source IDs, and rebuild rechecks their absence in storage.
The label is descriptive: shared outage and holiday are not distinguished.
Partial-day and other irregular gaps remain UNKNOWN. These are same-provider,
cross-instrument observations, not three independent providers.

## Aggregation and Persistence

Every expected minute in a UTC-anchored 1H/4H bin must be present (100%). Expected
closed minutes need not be supplied. Fully closed bins produce no candle. Partial
closure bins use the first/last actual expected observations for open/close and
their real highs/lows. Volume/spread remain unavailable, not fabricated. Any
missing expected minute prevents that entire aggregate from being emitted.

Source content hashes and model regeneration are checked before rebuilding.
Observed prices inside inferred closures reject. Raw archives/provenance remain
attached. New dataset manifests bind `calendar_id`, `source_dataset_id` and the
new resampling rule; unchanged legacy calls retain their previous identity format.
`source_time` on derived candles pins source/calendar IDs and endpoint source times.
Expected/actual/missing constituent counts are deterministically reproducible;
every unresolved aggregate retains its exact counts in the qualification report.

Research schema 5 adds immutable `p5_feed_calendars` and `p5_feed_qualification`.
Old rows and prior session models are not rewritten. Calendar payloads contain
confidence, seasonal slots and exceptions; associated qualifications retain all
unresolved aggregate intervals. The audit also retains exact source M1 gaps.
Queries pin a qualification, check calendar binding, and cannot cross UNKNOWN_GAP.
Explicit closure-only ranges cannot return fabricated candles.

## Qualification Limits

The calendar is retrospective, derived using all of 2021. It must not be described
as an out-of-sample forecast of feed availability or used to leak future information
into subsequent strategy evaluation. It is not applicable to another year by default.
No execution eligibility, P2/P3 admission, broker quote freshness or market-open
decision may use it. All trading remains HARD DISABLED.

Strict contiguous segments are reported separately from whole-year segmented
availability. No acceptable irregular-gap percentage was invented. P5 completion
depends on the actual six real-data ranges, not fixture multi-month tests.
Reproduction: `scripts/p5_feed_audit.py` through the TESTING.md normalized guard.
Full real results: Audits/P5-EMPIRICAL-FEED-CALENDAR.md.
