# P5 Real Market Data Foundation

Current 2026-09-15 closeout: **P5 VERIFIED_COMPLETE**, P6 READY/non-executing,
not started. ADR-017 adds EV Trading Labs as a distinct primary research provider;
all six 2021-2025 datasets have a shared qualified 86.83-day range. HistData stays
preserved secondary/limited corroboration evidence, with no rule relaxation.
The earlier checkpoints below are historical and no longer the phase verdict.
Current provider contract, mappings, native-H1/H4 limits, query API and exact
evidence: Components/P5-ALTERNATIVE-PROVIDER.md and
Audits/P5-ALTERNATIVE-PROVIDER-CLOSEOUT.md. Broker execution remains HARD DISABLED.

Latest: ADR-016 / Components/P5-EMPIRICAL-FEED.md now permits a separately versioned
empirical research calendar and all-EXPECTED-M1 aggregation. Earlier complete-only
datasets remain immutable. No synthetic price repair or execution eligibility.
Six new datasets are reproduced; residual gaps still prevent P5 completion.


Session follow-up: ADR-015 / Components/P5-SESSIONS.md adds an immutable calendar
qualification and explicit session-aware query. Expected closures may bridge;
unknown gaps cannot. Raw rows, prior qualifications and complete-only resampling
are unchanged. Current inferred Saturday-only calendar does not produce a
multi-month range; P5 remains PARTIAL. See Audits/P5-SESSION-QUALIFICATION.md.


## HistData-First Revision

ADR-014 supersedes the prior adjacent-range exclusion policy. Qualification rule
`p5-observation-validity-v2` preserves valid disjoint-range bars and their price-gap
flags. Missing timestamps and conflicting duplicates remain explicit; contiguous
queries still cannot bridge unknown gaps. Old qualification rows are retained.
`histdata_audit.inventory` audits actual monthly CSV rows inside saved annual ZIPs;
`scripts/p5_histdata_audit.py` rebuilds M1/1H/4H in the dedicated research store,
checks replay/reopen equality and persists annual/monthly coverage reports.
Identical canonical datasets intentionally retain content IDs; new qualification
IDs identify changed validity semantics. Annual M1 versions are also persisted.
Exact evidence and unresolved session qualification: Audits/P5-HISTDATA-FIRST.md.


Status: bounded data foundation implemented; overall P5 PARTIAL / IN_PROGRESS.
No P6 or execution work. Implementation base: P4 commit `b13b236`.

Current follow-up: Components/P5-CONTINUITY.md supplies immutable coverage metrics
without redesigning storage or changing any qualification. Exact existing ranges,
missing counts and second-provider access findings are in
Audits/P5-PROVIDER-ACCESS-AND-COVERAGE.md. No new continuous range is qualified.
Dukascopy is evaluated, not admitted as a canonical provider; historical data access
and normalization remain unproven. HistData remains the sole stored provider.

## Current Closeout Scope

Accepted ADR-013 moves strategy replay to P6. P5 owns qualified real datasets and
their deterministic interface only. Annual history and bounded qualification are
implemented; meaningful continuous multi-month coverage remains unproven, so P5
is PARTIAL and P6 BLOCKED. See Audits/P5-CLOSEOUT.md for current evidence.

## Existing Code Disposition

`services/yahoo_history_service.py` maps metals/oil to GC=F/SI=F/CL=F futures proxies,
uses 5-minute data, skips malformed candles and replaces cache rows. It is not
reused as authoritative P5 storage. The legacy random/synthetic backtester remains
quarantined outside V2 imports under ADR-007; it is not deleted or reconnected.
P5 modules import neither lifecycle execution nor strategies/backtesters. P4's
existing broker hard block and P3 operator deferral remain unchanged.

## Provider and Mappings

HistData explicitly offers CSV data for backtesting, documents M1 bid bars, fixed
EST (UTC-05:00 without DST), and absence of volume. These are provider observations,
not an attestation of Exness fills, broker spreads or identical contracts.
Sources: [provider FAQ](https://www.histdata.com/f-a-q/) and
[ASCII file specification](https://www.histdata.com/f-a-q/data-files-detailed-specification/).

| Canonical instrument | HistData symbol | Broker reference only |
|---|---|---|
| XAUUSD | XAUUSD | XAUUSDm |
| XAGUSD | XAGUSD | XAGUSDm |
| USOIL | WTIUSD | USOILm |

Mapping version: histdata-v1. Unknown mappings reject; provider suffixes are not
derived from broker suffixes. WTI contract/roll construction and differences from
broker USOIL are unverified. No mixed-provider continuous series or exact broker
equivalence is claimed. Data remain local/ignored; no redistribution or commercial
license grant is asserted. Dukascopy was considered but not selected: its published
[website terms](https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/)
raise automated-access permission questions. No Dukascopy market data was fetched.

## Canonical Data and Quality

`core/rebuild/market_data.py` supplies frozen Candle contracts with instrument,
provider/symbol, timeframe, UTC open/close, Decimal OHLC, optional volume and kind,
optional spread, original source time and timezone evidence. Dataset manifests
carry mapping, normalization/resampling/validation versions, range/content hash,
quality and identity; receipts carry ingestion time and raw/provenance references.
The contract's 30-digit / 12-decimal-place bound rejects unrepresentable prices;
it is a technical precision bound, not a trading-price or volatility policy.

Rules reject nonfinite/nonpositive OHLC, inconsistent geometry, malformed volume,
wrong symbols, naive times, wrong durations and misaligned opens. Parsing keeps
invalid row numbers and raw bytes, rather than silently dropping evidence. Exact
duplicates coalesce; contradictory duplicates retain evidence, exclude the disputed
bar and report a gap. Out-of-order input is classified and deterministically sorted.
Adjacent disjoint price ranges are flagged for review, not automatically repaired
or declared corrupt. Legitimate market gaps may trigger that conservative rule.

Expected timestamps are evaluated over explicit half-open ranges. Missing intervals
are recorded as compact start/end/count records, with UNKNOWN_SESSION_OR_MISSING
classification. No authoritative instrument-session/holiday calendar was established,
so weekends/closures are NOT guessed into an exemption. No OHLC forward-fill.
All questionable or incomplete datasets are REVIEW_REQUIRED; default research
queries reject them and synthetic fixtures. Diagnostic reads explicitly opt out
with research=False and retain the full quality report, not qualification status.

1H/4H aggregation uses UTC epoch-anchored, left-closed/right-open bins. Every
constituent real M1 observation must be present exactly once; incomplete bins are
reported, not emitted as full candles. Source timeframe/rule version remain in the
manifest. These UTC research bars are not claimed to match a broker's daily session.
Volume remains null when unavailable. No invented spread, bid/ask mid or prices.

## Storage, Identity and Synchronization

Research storage is exclusively `research/p5-market-data/market-data.sqlite3`.
It is separate from P1-P4/operator state and ignored by Git. No operator database
is opened or migrated. Explicit fixture roots are restricted to OS temporary
storage. Existing unowned directories and linked database files reject.
This ownership check is not an OS sandbox against privileged filesystem mutation.

P5 has its own initial schema/version table; existing lifecycle migrations are
unchanged. Raw byte bundles, datasets, bars and receipts have immutable SQL triggers.
Bars are indexed/unique by dataset and timestamp; reads are ordered time-range
queries. One transaction publishes raw evidence, manifest, bars and receipt.
Provider failure before publication leaves no falsely complete dataset.

Identity includes canonical instrument/provider/mapping, timeframe/exact range,
normalizer/resampler/validator version, normalized Decimal bar content and quality.
Receipt time is deliberately excluded. Unchanged evidence re-ingestion reproduces
identity; same canonical values with alternative decimal spelling normalize alike.
Raw ZIP bytes are retained separately under hashes. Changed data create new
immutable IDs; explicit compatible parent IDs record correction/extension lineage.
Old IDs remain queryable. No ambiguous implicit latest-version selection exists.

`HistDataProvider.download/normalize` is the replaceable provider boundary. Download
forms are identity-validated; transient public form markers are not logged/stored.
Monthly downloads are preferred; explicitly identified annual archives are supported
when no monthly form exists. Wrong archive symbol/year/month, truncated/oversized
responses and HTTP errors fail closed. ZIP members are never extracted to disk.
Normalization can select a month, or explicitly use month=None for an annual
archive. The entire raw archive is retained; annual processing never fabricates
missing observations. scripts/p5_closeout.py reuses the preserved 2021 raw archives.

`sync` takes provider, instrument, timeframe, UTC start/end and optional parent ID.
Requests are bounded to 62 days, re-fetch overlaps and publish immutable versions.
Incremental extension is explicit, not automatic replacement or a hidden freshness
claim. A supplied provider error does not cause random-data or another-symbol fallback.

## Research Interface and Commands

`MarketStore.query(dataset_id, start=..., end=...)` returns ordered candles,
manifest, provenance/receipts and exact ID. Requested boundaries must align to
complete candles and remain inside the dataset. Selecting the immutable dataset
also selects instrument/provider/timeframe/version; caller cannot silently request
another symbol under the same ID. No synthetic fallback or P&L calculation exists.

Public-network commands (separate from ordinary fixture tests):

```powershell
.\backend\.venv\Scripts\python.exe -B scripts/p5_market_data.py --instrument XAUUSD --timeframe 1H --start 2021-01-04T12:00:00+00:00 --end 2021-01-04T20:00:00+00:00
.\backend\.venv\Scripts\python.exe -B scripts/p5_real_smoke.py
```

Use the normalized guard described in TESTING.md for actual verification. No app,
credential file or broker terminal startup is needed. The smoke fixes its window,
downloads each public source once, checks all three timeframes/replay/reopen/query,
and writes only a diagnostic report in the dedicated research root.

Future outcome reconstruction can read M1 or aggregated bars with exact opening/
completion timestamps and provenance. OHLC cannot prove intrabar TP-before-SL;
ADR-004 AMBIGUOUS/UNKNOWN/TIMEOUT semantics remain mandatory. No labels are produced.

## Limits

Exact real samples/IDs and acquisition failures: P5-REAL-DATA-EVIDENCE.md.
Annual 2021 raw history is processed, not 2021-present continuity. Recent WTI download
availability was not established. No actual volume, spread, broker equivalence,
approved session calendar, strategy replay, profitability or operator qualification.
Kronos source compatibility/precision/leakage limits: P5-KRONOS-COMPATIBILITY.md.

## Append-Only Qualification Interface

`research_data.ResearchData` adds only P5 research schema version 2 and an immutable
qualification table. It does not migrate lifecycle/operator stores or modify old
dataset manifests. A qualification ID hashes the pinned dataset, rule/validator,
classification events, exact accepted content, segments and limitations.

Missing provenance/synthetic evidence is REJECTED; unbounded corrupt evidence,
obsolete validation or no usable bars is REVIEW_REQUIRED. Trusted HistData data
with bounded exclusions is QUALIFIED_WITH_KNOWN_LIMITATIONS (bid proxy, no volume).
No current HistData dataset is claimed limitation-free QUALIFIED. Append-only
requalification preserves old decisions and raw evidence; it does not clear flags.

`qualify(dataset_id, closures=())` accepts explicitly evidenced closure intervals;
no real closure exemptions were supplied. `query(qualification_id,start=...,end=...)`
requires aligned contiguous complete usable candles. `allow_segments=True` is an
explicit discontinuous diagnostic/research view returning only retained bars plus
segment boundaries, requested range, pinned dataset/qualification IDs, mapping,
provenance and every exclusion. Never treat concatenated segments as continuous.
Underlying MarketStore diagnostic bars remain unchanged. There is no strategy,
P&L or execution integration. Meaningfulness is a separately evidenced exit gate,
not a hidden arbitrary minimum-length threshold in qualification.
