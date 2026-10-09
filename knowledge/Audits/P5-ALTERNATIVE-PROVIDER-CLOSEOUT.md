# P5 Alternative-Provider Closeout

Date: 2026-09-15. Branch: `core-rebuild`. Implementation base:
`1d0696dfaf74c6aafa2f4cb2e83151de886b2814`. This audit is committed with the bounded
P5 work; no push. Unrelated untracked `README_SETUP.md` is excluded and untouched.

Verdict: **P5 VERIFIED_COMPLETE**, under the owner's native-bar, meaningful
multi-month research requirement and ADR-017. P6 READY, **NOT STARTED**.
P3 operator verification remains DEFERRED; broker execution HARD DISABLED.

## Exact Evidence

Machine-readable committed metadata: [P5-ALTERNATIVE-DATA-EVIDENCE.json](P5-ALTERNATIVE-DATA-EVIDENCE.json).
Evidence ID: `821c867d5b29065f54d1df5f5876ba995da8b9a71557e79427c91a44c3ae3ba5`.
Full local audit: `research/p5-market-data/alternative-audit-9057b9c919b4a06c4ab2ba615501e77526c48e29a67dddf373c8125138d20270.json`.
The suffix is the canonical report hash, not a hash of pretty-printed bytes.
The local audit's root `qualified: false` describes the full acquired interval;
individual immutable qualification entries and their bounded segments carry the
research verdict. It does not mean that no segment qualifies or that P5 is blocked.

Thirty public annual gzip files (three instruments x two frames x five years)
were acquired from EV Trading Labs. Raw files plus full catalogue responses are
length-framed in immutable raw-store bundles; every source has URL, SHA-256,
bytes/count/bounds, acquisition/ingestion evidence and adapter version. Offline
reparse of all 30 files matched canonical content hashes and catalogue metadata.
No partial failed response became a qualified dataset. No account/payment needed.
Provider selection, sources, attribution/licensing caveats and mapping rationale:
[P5-ALTERNATIVE-PROVIDER.md](../Components/P5-ALTERNATIVE-PROVIDER.md).

### Acquired Coverage (Not Full-Range Qualification)

Requested UTC range: `[2021-01-01T00:00, 2026-01-01T00:00)`.
All prices are BID OHLC with ASK OHLC separately retained; volume meaning UNKNOWN.

| Instrument | H1 observed | H1 expected | H1 closed slots | H1 unknown slots | H4 observed | H4 expected | H4 closed slots | H4 unresolved bins |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| XAUUSD | 29563 | 29992 | 13832 | 429 | 7996 | 8085 | 2871 | 167 |
| XAGUSD | 29563 | 29992 | 13832 | 429 | 7996 | 8085 | 2871 | 167 |
| USOIL/WTI | 29551 | 29992 | 13832 | 441 | 7994 | 8085 | 2871 | 173 |

H4 unresolved bins include native observations with incomplete expected hourly
constituents, not only entirely absent H4 bars. Those observations remain stored,
but cannot be consumed through a query spanning that interval. Longest unresolved
run: H1 82,800 seconds; H4 115,200 seconds, for each instrument. Unconfirmed
holidays/early closes are included in UNKNOWN, not excused as provider closures.
All 23,986 supplied H4 bars match available H1 bid/ask OHLC; zero price mismatches.
All three full hourly histories have zero regular-calendar observation conflicts.

### Shared Qualified Range

For ALL three instruments and BOTH timeframes:
`[2025-09-02T00:00:00+00:00, 2025-11-27T20:00:00+00:00)` = **86.8333 days**.

| Instrument | H1 observed = expected | H1 known closed slots | H4 observed = expected | H4 known closed slots | Unknown bins / longest unknown gap |
|---|---:|---:|---:|---:|---|
| XAUUSD | 1445 | 639 | 389 | 132 | 0 / 0 |
| XAGUSD | 1445 | 639 | 389 | 132 | 0 / 0 |
| USOIL/WTI | 1445 | 639 | 389 | 132 | 0 / 0 |

Each view is `QUALIFIED_WITH_KNOWN_LIMITATIONS`, with exact dataset, qualification,
calendar and raw receipt IDs in the JSON evidence. Full datasets contain 53 H1/H4
segments for each metal, and 55 H1 / 54 H4 segments for WTI. No full five-year
uninterrupted claim. Individual longest ranges are also retained in the local audit.

## Cross-Provider Findings

2021 same-UTC BID-close overlaps: gold 5711, silver 4921, WTI 4363 bars.
Price correlations: 0.998787 / 0.999311 / 0.999614. Median absolute relative price
differences: 0.01991% / 0.03440% / 0.04687%. Largest same-time offsets are preserved,
not suppressed; several are price moves shifted by the seasonal timing difference.

Important discrepancy: JAN/FEB/DEC same-hour return correlation is approximately
1.0. APR-OCT correlation is approximately 0.99992 / 0.99988 / 0.99998 when comparing
EV timestamp t with HistData timestamp t+1 hour. Zero-lag full-year return
correlations are only 0.4424 / 0.5468 / 0.5498. This strongly supports a seasonal
alignment difference. It does not identify which provider is wrong from statistics
alone or prove independent upstream sourcing. EV explicitly supplies UTC Unix
timestamps; the preserved HistData parser follows its documented fixed-EST rule.
Neither source was shifted, modified or spliced. Exact timing equivalence remains
UNVERIFIED; comparison diagnostics are PROVEN, equivalence is not a P5 claim.

## Exit-Gate Verification

| Existing P5 requirement | Result / evidence |
|---|---|
| Trustworthy real source data | PASS in provider-native research scope: public exports, native shape/basis, hashes, raw reparse and price-path corroboration |
| All three have meaningful multi-month coverage | PASS: same 86.83-day qualified interval for all six combinations |
| H1/H4 access | PASS: exact pinned queries, expected-hour completeness, bid/ask aggregate comparison |
| Deterministic identity | PASS: content hashes, replay, immutable IDs and restart/reopen equality |
| Complete provenance | PASS: 30 source URLs/hashes/counts/bytes, catalogues, ingestion time, mapping/normalizer and calendar references |
| Bounded session/gap classification | PASS within qualified ranges; unknowns excluded elsewhere, no holiday guessing or calendar conflict |
| No synthetic authoritative observations | PASS: none introduced/detected; no forward-fill or repaired prices; upstream tick completeness is not independently proven |
| Version-pinned backtest interface | PASS: ResearchDatasetReader, shared range and reopen equality, unknown-range and obsolete-ID rejection |
| Provider-independent consumption | PASS: common qualification-ID/UTC-range reader; no strategy imports or provider retrieval required by consumer |
| Kronos data-only contract | PASS for K-line representation and lineage/as-of; runtime/checkpoints/volume suitability remain P8 |

## Verification Runs

- New provider/session/query module: **45 tests** included in final selection.
- Focused seven-module P5 suite: **165 passed in 27.82s**.
- Broad 26-module fixture-safe P5/P4/P3/P2/P1 and rebuild/parser/import regression:
  **849 passed, 1447 warnings in 204.79s**. Warnings remain existing technical debt,
  not silently reported as zero or production certification.
- Real acquisition: exit 0, all six versions persisted. Real raw reparse,
  qualification replay/reopen, comparison and K-line audit: exit 0.
- Shared-range evidence command: exit 0, six exact queries/reopen checks passed.
- Each guarded run: six synthetic guard self-tests, zero sensitive/operator-path
  access attempts, forbidden runtime modules `[]`.
- Initial fixture test exposed injected HTTP data being marked real; fixed by
  mandatory fixture marking for injected clients and retested. Missing Windows
  timezone data was resolved with the explicit pinned dependency, not guessed DST.

## Limits and Preservation

Research price proxy only; not broker fills, validated spreads, profit labels or
execution evidence. WTI exact contract/roll construction remains unverified.
Native H1 is not independently complete M1/tick coverage. Volume remains UNKNOWN.
P5 never downloaded protected M1/current-year exports, used credentials, modified
operator stores, connected brokers, submitted orders, built strategies or trained
models. Direct Dukascopy data was not downloaded. HistData archives, datasets,
calendars, prior audits and ADR-016 remain intact. No data is redistributed/pushed.

P5 blockers: **NONE for the authorized native-bar research exit gate**.
Residual timing/licensing/volume/contract limitations must remain visible in P6/P8.
Next authorized roadmap phase: P6, NON-EXECUTING, not started by this task.
