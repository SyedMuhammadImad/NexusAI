# P5 Closeout - Partial (2026-09-14)

Branch: core-rebuild. Baseline: 3d3fd27a5d7225ebd6fe7236c0fb49fac06f3829.
This bounded closeout is committed separately; no push. ADR-013 records the
owner-approved P5 data / P6 strategy boundary. No strategy is implemented.

## Verdict

P5 PARTIAL / IN_PROGRESS. Six annual views are qualified WITH KNOWN LIMITATIONS
for their explicitly retained segments only. None proves continuous multi-month
history. P6 remains BLOCKED. Broker execution remains HARD DISABLED.

The blocker is real-data quality/continuity, not a missing strategy. The existing
strict disjoint-range rule is deliberately NOT relaxed to obtain completion.
It may flag legitimate price movements: non-overlap alone is not corruption.
Resolve source/session evidence and corroborate questionable observations, or
acquire sufficiently complete corroborated history. No threshold is invented.

## Real Coverage

The previously downloaded full annual 2021 HistData archives were already retained
as hashed raw evidence. This batch processes their full year, not another download
of the eight-hour sample. No network, operator store or credential is needed.
Requested UTC range: [2021-01-01T00:00:00Z, 2022-01-01T00:00:00Z).
Native times use the provider's fixed EST UTC-05/no-DST convention.

| Instrument | Unique M1 source bars | Complete 1H / 4H bars | Retained 1H / 4H bars | Excluded 1H / 4H bars | Longest retained 1H / 4H segment (bars) |
|---|---:|---:|---:|---:|---:|
| XAUUSD | 353386 | 5860 / 1267 | 3328 / 216 | 2532 / 1051 | 14 / 3 |
| XAGUSD | 350676 | 4939 / 896 | 2862 / 195 | 2077 / 701 | 18 / 3 |
| USOIL / WTIUSD | 346791 | 4376 / 762 | 1267 / 26 | 3109 / 736 | 8 / 2 |

| View | First usable UTC open | Last usable UTC close | Months with usable bars |
|---|---|---|---|
| XAUUSD 1H | 2021-01-03 23:00 | 2021-12-31 20:00 | All 12 |
| XAUUSD 4H | 2021-01-06 12:00 | 2021-12-30 20:00 | All 12 |
| XAGUSD 1H | 2021-01-03 23:00 | 2021-12-31 15:00 | All 12 |
| XAGUSD 4H | 2021-01-06 00:00 | 2021-12-29 16:00 | All 12 |
| USOIL 1H | 2021-01-04 07:00 | 2021-12-31 19:00 | All 12 |
| USOIL 4H | 2021-02-25 08:00 | 2021-12-30 20:00 | Feb, Mar, Apr, Jul, Aug, Sep, Oct, Nov, Dec |

Year-spanning endpoints do NOT imply continuous coverage. No 2021-present/latest
claim. Existing recent WTI acquisition failures remain recorded in
Components/P5-REAL-DATA-EVIDENCE.md; not retried or silently replaced in this batch.
Research/broker mappings are XAUUSD/XAUUSDm, XAGUSD/XAGUSDm and WTIUSD/USOILm.
No exact broker, WTI contract-roll, volume or spread equivalence is proven.

### Stable Dataset IDs

- XAUUSD 1H: c254adbcd70038ee533d04ea01486eb0620af2a6826f1b0e231146a627b106d7
- XAUUSD 4H: b3380bcd815f49594fc3db3b4ecb89b1165841fa6066104a0d36e0fbb90732a0
- XAGUSD 1H: a596229b6024ae23313e703177fa054946b6fa4e0f08a9721847781b4410787b
- XAGUSD 4H: 6f3490df13b6c3c2ee6a23726e45a0ba67df8d2f1b38f14db7be565099705924
- USOIL 1H: fb1ff343f833a36a73cd9af75cf4268ac17336c0b2843dd4b593278c93b1efbe
- USOIL 4H: 49c05f00d973a7d85d293d388e37a173ba7602a23b8472e921cc684d2089a767

Exact raw ZIP SHA256, matching prior retained evidence:

- XAUUSD: 312229c9db5b39138c41b1e488d00ed32e158a0d1fc3f23a225b223c3271c0a4
- XAGUSD: 7ccccc89c592339ce3ca7712c1ee3758bd15fe6cbc398ef8473a3fbf840d97a3
- WTIUSD: d808a19ff0129ced92ca0de1d6c67dc073f271abee520338a7956ef39814e29d

## Original Nine Flagged Datasets

All nine were inspected. Their existing IDs/manifests remain unchanged.
Each instrument has 1M, 1H and 4H versions of 2021-01-04 12:00-20:00 UTC.
All three timeframes inherit the instrument's M1 disjoint-range flags (6 gold,
3 silver, 7 WTI); no missing timestamps or malformed OHLC were found in that sample.
Classification: UNKNOWN cause, not proven market closure or corrupt observation.
The older aggregated manifests lack source_timeframe on these flags, so their
qualification bounds conservatively use their own interval; annual manifests
explicitly retain source_timeframe=1M. Old evidence was not rewritten.

Exact triggering right-bar UTC timestamps and adjacent low/high ranges:

| Symbol | Time on 2021-01-04 | Previous low-high | Current low-high |
|---|---|---|---|
| XAUUSD | 14:06 | 1938.638-1940.188 | 1940.2-1940.938 |
| XAUUSD | 14:36 | 1938.138-1939.238 | 1936.538-1938.088 |
| XAUUSD | 16:49 | 1941.215-1941.708 | 1940.668-1941.21 |
| XAUUSD | 18:26 | 1941.308-1941.895 | 1941.94-1942.35 |
| XAUUSD | 19:14 | 1939.508-1939.958 | 1939.975-1941.228 |
| XAUUSD | 19:26 | 1940.198-1940.658 | 1939.638-1940.188 |
| XAGUSD | 12:10 | 27.191-27.206 | 27.207-27.23 |
| XAGUSD | 19:09 | 27.139-27.155 | 27.114-27.138 |
| XAGUSD | 19:14 | 27.128-27.15 | 27.151-27.191 |
| USOIL | 12:05 | 48.777-48.813 | 48.707-48.773 |
| USOIL | 14:43 | 48.387-48.453 | 48.457-48.543 |
| USOIL | 15:37 | 48.077-48.308 | 47.287-48.073 |
| USOIL | 16:41 | 47.447-47.483 | 47.487-47.573 |
| USOIL | 16:48 | 47.547-47.663 | 47.667-47.753 |
| USOIL | 17:48 | 47.467-47.493 | 47.503-47.563 |
| USOIL | 17:54 | 47.567-47.613 | 47.617-47.653 |

These values explain precisely why the rule fired, not why prices moved.
For example the first gold non-overlap is only 0.012 USD; size alone cannot
independently prove either feed corruption or a valid market transition.

## Classification / Qualification

Missing internal intervals: PROVIDER_GAP with session cause unproven.
Missing requested outer intervals: SOURCE_BOUNDARY. Incomplete aggregation:
RESAMPLING_BOUNDARY. Exact duplicates/order sorting: DUPLICATE/CORRECTION;
conflicting timestamps are excluded. Disjoint adjacent price ranges: UNKNOWN.
Malformed unbounded rows: CORRUPT_OBSERVATION, REVIEW_REQUIRED.
EXPECTED_MARKET_CLOSURE requires supplied matching evidence; no real exemption
was inferred. The tests exercise closure evidence with explicitly synthetic data.

Append-only qualification keeps raw manifests REVIEW_REQUIRED and separately
pins permitted segments. Unresolved intervals remain unavailable; default query
rejects them. Segmented views retain all events, missing ranges, content identity
and source provenance. They never forward-fill or represent concatenation as a
continuous market. Qualifications are not forecasts or strategy suitability proof.

## Real Range Proof

Independent pinned 1H/4H queries over UTC [July 1, July 4) and [July 1, October 1),
2021. Repeated results identical. All ordinary contiguous queries reject gaps.

| View | Three-day segmented bars | Three-month segmented bars |
|---|---:|---:|
| XAUUSD 1H / 4H | 19 / 1 | 782 / 46 |
| XAGUSD 1H / 4H | 30 / 4 | 715 / 43 |
| USOIL 1H / 4H | 8 / REJECTED (no usable bars) | 300 / 6 |

All six annual datasets reproduce the same ID on re-ingestion and the same query
after store reopen. Fixture tests additionally prove exact clean multi-day and
multi-month boundaries, pinning, state changes, gap rejection and immutable history.
Fixtures are NOT real-price evidence. Query mechanics are proven; sufficient
continuous real coverage is NOT_PROVEN.

## Reproduction and Safety

Use the normalized TESTING.md P1-M2 guard, substituting runpy.run_path for pytest:
first scripts/p5_closeout.py, then scripts/p5_closeout_inspect.py. These access
only the dedicated ignored P5 research root and preserved public archives.
Reports there: closeout-report.json and closeout-inspection.json (exact events,
qualification IDs, candle pairs and range results). Raw data/SQLite are not committed.
Successful runs report six guard self-tests, zero protected/operator attempts,
no forbidden runtime modules. Guard scope is not a machine-wide OS sandbox.

No MT5/broker, secrets, operator DB, strategy, model training or push. Kronos runtime
is absent; see Components/P5-KRONOS-COMPATIBILITY.md. Test results: TESTING.md.

Final verification: 68 focused tests passed (7.83s); 752 broad P5/P4/P3/P2/P1 and
fixture-safe backend tests passed (1447 existing warnings, 124.50s). No failed test
is suppressed. Staging checks: 18 scoped files, zero forbidden data/private paths,
zero matches in a limited staged-diff API-token/private-key pattern check. This is
not a complete secret audit. Raw research files remain ignored. Unrelated untracked
README_SETUP.md is untouched and excluded from the commit.
