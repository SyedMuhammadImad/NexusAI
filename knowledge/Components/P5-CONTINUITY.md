# P5 Continuity Diagnostics

Current rule: `p5-continuity-metrics-v2`, reflecting ADR-014's separation of
observation validity from continuity. Disjoint adjacent ranges are informational
and do not withhold candles. Existing v1 reports are preserved. A true
`continuity_proven` result proves timestamp structure only, not price accuracy.
Real-calendar exemption still requires applicable provider/date-specific evidence.


Status: implemented diagnostics, not continuous-history qualification.
Scope: owner-authorized P5 follow-up, 2026-09-14. No strategy, broker or ML path.

`core/rebuild/continuity.py` reads an explicitly pinned stored snapshot and
calculates deterministic metrics. `CoverageStore` adds an append-only p5_coverage
table and P5 research schema version 3. Existing raw, candle, manifest, receipt,
qualification and lifecycle tables are not changed. No operator database is used.

## Metrics

All ranges are aligned UTC half-open intervals. The expected grid includes every
bar slot until a provider/date-specific closure has evidence. It is NOT an
assertion that the instrument trades 24/7.

| Field | Definition |
|---|---|
| total_grid_bars | Range duration divided by timeframe |
| total_expected_bars | Grid slots minus fully evidenced closed slots |
| actual_bars | Stored complete bars in the requested range, before quality exclusions |
| expected_closure_bars | Union of fully covered closed slots; no duplicate counting |
| partial_closure_bars | Slots only partially covered; not exempt from missing counts |
| unexplained_missing_bars | Expected slots without a stored bar |
| unexplained_gap_percentage | Missing / expected * 100, six decimal places; null for zero expected |
| longest_unexplained_gap_bars/seconds | Longest consecutive missing non-exempt grid run |
| first_timestamp/last_timestamp/last_close | Actual stored bounds, null for no bars |
| quality_withheld_bars / usable_bars | Existing conservative quality partition, separately counted |
| closure_conflicting_observation_bars | Actual bars in fully declared closed slots; blocks continuity |
| classification_counts | ENTIRE_PINNED_DATASET classifications; not silently restricted to query |
| continuity_proven | Structural diagnostic only; zero missing/conflicts/quality exclusions |

Synthetic fixture continuity can test the geometry without qualifying the fixture.
The diagnostic does not establish provenance, authenticity, meaningful length,
acceptable trading risk or P5 completion. It never changes qualification.

## Closure Evidence Contract

Each interval requires provider, instrument, aware UTC-normalized start/end,
valid_from/valid_until, evidence_ref and a 64-hex evidence_sha256. Interval must
fall within the evidence's validity. Wrong provider/instrument, invalid dates,
naive time or missing reference/hash rejects. Overlapping intervals are unioned.
A partial closure cannot excuse an entire missing 4H bar. A stored observation
inside a fully closed bar is contradictory, not silently adopted as a closure.

This is a TRUSTED evidence-input contract, not an automatic document verifier:
the caller must independently establish the referenced calendar's truth and hash.
No real closure exemptions were supplied in this batch. Current Dukascopy hours
are not evidence of HistData 2021 sessions. No UNKNOWN flags were cleared.

## Provider Separation

The current canonical store still admits HISTDATA only. No pretend second-provider
adapter was added without native data access/normalization proof. Snapshot metrics
preserve provider identity and reject mixed-provider candles. Fixture tests cover
independent provider-labelled diagnostics and reject attempted mixing; they do not
prove live cross-provider corroboration. Foreign receipts cannot qualify HistData
candles as Dukascopy observations. No merge, precedence or synthetic repair exists.

## Persistence and Reproduction

Coverage ID hashes pinned dataset, range, rule, metrics and evidence. Repeated
assessment/restart yields identical IDs; changed closure evidence appends a new
report. SQL triggers prohibit UPDATE/DELETE. Old reports remain attributable.

Run `scripts/p5_continuity_report.py` through the normalized TESTING.md guard.
It assesses the nine original and six annual datasets, checks replay/reopen and
unchanged source snapshots, and writes the ignored research/continuity-report.json
(under research/p5-market-data). No network request, source re-ingestion, credential
or broker action. Exact current results: Audits/P5-PROVIDER-ACCESS-AND-COVERAGE.md.
