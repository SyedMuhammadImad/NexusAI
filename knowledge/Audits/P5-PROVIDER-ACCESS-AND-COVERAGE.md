# P5 Provider Access and Continuity Review

Date: 2026-09-14. Branch: core-rebuild.
Baseline: 46209637a5253486ea19f4be715abba9cecb29f9.
Verdict: P5 PARTIAL; P6 BLOCKED. No new market history acquired in this batch.
Existing HistData evidence retained; diagnostic metrics added. No completed
second-provider adapter or cross-provider price corroboration is claimed.

## Access Evidence and Exact Blocker

Dukascopy's official [historical-data export guide](https://www.dukascopy.com/wiki/en/development/data-export/)
documents the cfg-public-proper-wallaby S3 bucket in eu-west-1 with Requester Pays.
It explicitly requires valid AWS credentials and requester billing. The guide was
retrieved successfully over HTTPS (200) after the web reader could not open it.
No AWS credentials were inspected, account opened, permission expanded or charge
incurred. Instrument prefixes in that bucket are UNVERIFIED without authorized
discovery; a published CFD name is not proof that the bucket contains its history.

The [website terms](https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/)
restrict automated collection without written consent and website database use.
The documented S3 service is a concrete alternative, not authorization to run an
anonymous website scraper. No legacy datafeed bulk probe, circumvention or
unapproved scraping was performed. Public availability alone is not a permission
or continuity attestation.

The official [Trading Tools API documentation](https://www.dukascopy.com/trading-tools/api/documentation/quotes)
returned a shell and rendered blank in a temporary browser tab, so it did not
establish another supported credential-free bulk contract. The tab was closed.
This does NOT prove every anonymous export option is impossible; it records the
supported bulk route found and the alternative that could not be verified.

Required human input: an authorized data export with usage rights, or an explicitly
authorized, narrowly scoped AWS retrieval boundary and spending limit. Do not paste
credentials into chat. Then first verify instrument prefixes and availability,
request only the required period, preserve native files/hashes and test normalization
before attempting qualification. If the bucket lacks metals/WTI, a different
permitted provider/export is still necessary. No completion promise from credentials.

## Candidate Instrument Semantics

Existing HistData XAUUSD/XAGUSD/WTIUSD mapping is unchanged. Candidate Dukascopy
metals are gold/USD and silver/USD, supported by its official [gold](https://www.dukascopy.com/swiss/english/cfd/range-of-markets/gold/)
and [silver](https://www.dukascopy.com/swiss/english/cfd/range-of-markets/silver/) pages.
Native S3 keys, scaling, units, timestamp encoding and history remain UNVERIFIED.

For canonical USOIL, [LIGHT.CMD/USD](https://www.dukascopy.com/swiss/english/cfd/range-of-markets/wti-oil-cfd-trading/)
is a defensible candidate RESEARCH PROXY: Dukascopy describes a non-expiring WTI-
linked CFD, not a particular exchange futures contract and not Exness USOILm.
Its [monthly adjustment documentation](https://www.dukascopy.com/swiss/english/cfd/cfd-monthly-adjustment/)
describes a switch of the underlying futures contract during a market break with
corresponding price change/account adjustment. Historical adjustment dates and
values were NOT obtained. No roll jump is automatically declared benign.

The current [market schedule](https://www.dukascopy.com/swiss/english/cfd/range-of-markets/)
lists LIGHT.CMD/USD summer 22:00-21:00 GMT with daily 21:00-22:00 break; winter
23:00-22:00 with 22:00-23:00 break. The adjustment page adds a 20-minute earlier
stop on adjustment days. These current documents do not prove a complete dated
2021 calendar, holidays, DST transitions or HistData's session conventions.
No such calendar was retroactively applied. CFD/broker equivalence remains unproven.

## Measured Existing Annual Coverage

All rows: provider HISTDATA, requested [2021-01-01T00:00Z, 2022-01-01T00:00Z).
Expected closures = 0 PROVEN exemptions (not a claim that no closures occurred).
Until calendar evidence is supplied, unexplained missing includes real closures,
source boundaries and incomplete resampling, NOT only confirmed provider omissions.
No meaningful continuous multi-month qualified range is proven for any instrument.

| View | Expected grid bars | Actual bars | Missing without exemption | Percentage | Longest missing run (bars / hours) | Quality-withheld actual bars |
|---|---:|---:|---:|---:|---:|---:|
| XAUUSD 1H | 8760 | 5860 | 2900 | 33.105023 | 74 / 74 | 2532 |
| XAUUSD 4H | 2190 | 1267 | 923 | 42.146119 | 19 / 76 | 1051 |
| XAGUSD 1H | 8760 | 4939 | 3821 | 43.618721 | 79 / 79 | 2077 |
| XAGUSD 4H | 2190 | 896 | 1294 | 59.086758 | 29 / 116 | 701 |
| USOIL 1H | 8760 | 4376 | 4384 | 50.045662 | 74 / 74 | 3109 |
| USOIL 4H | 2190 | 762 | 1428 | 65.205479 | 22 / 88 | 736 |

Actual first/last bar OPEN timestamps UTC (before quality exclusions):

- All three 1H: 2021-01-03 23:00 through 2021-12-31 20:00; last close 21:00.
- XAUUSD/XAGUSD 4H: 2021-01-04 00:00 through 2021-12-31 16:00; last close 20:00.
- USOIL 4H: 2021-01-04 08:00 through 2021-12-31 16:00; last close 20:00.

Qualified segmented-view endpoints/counts and all dataset IDs remain recorded in
P5-CLOSEOUT.md; these raw coverage bounds must not replace those usable bounds.
WTI still has just 26 quality-retained 4H bars, longest retained run two bars.

## Flag Disposition

All 15 current original/annual dataset manifests were re-assessed without mutation.
All nine original samples have zero missing timestamps but retain 6 gold / 3 silver
/ 7 WTI source disjoint-range flags. Those intervals' exact OHLC pairs remain in
P5-CLOSEOUT.md and closeout-inspection.json. Cause remains UNKNOWN, not corruption
or a proved market/session closure. Annual flags remain individually bounded in
their immutable manifests/qualification events. No new corroborating price evidence
exists to change their disposition. Exact dataset-level classification counts and
missing interval start/end/run lengths are persisted in the coverage reports.

Missing internal intervals retain unproven-provider/session classification, outer
gaps SOURCE_BOUNDARY, incomplete aggregates RESAMPLING_BOUNDARY, duplicate/sort
events DUPLICATE/CORRECTION, disjoint moves UNKNOWN. Expected closures and actual
provider corruption are not invented from absence or a price jump alone.

## Reproducible Evidence

Ignored report: research/p5-market-data/continuity-report.json.
Report identity: 244bb30c20a6c824fa0df972e7b0330f448eebe6a7c6a43fc85f0ba10761c979.
Each dataset has a persisted immutable p5_coverage row with its own ID and exact
metrics/ranges. The script checks repeated assessment, store reopen and unchanged
raw dataset snapshots. All 15 report continuity_proven=false. Zero network data
requests, zero qualification changes and zero broker actions in that script.
Guard: six synthetic self-tests, zero protected/operator attempts, no forbidden
runtime imports. Tests and limitations are in TESTING.md and Components/P5-CONTINUITY.md.

Final tests: 89 focused passed (9.94s), 773 broad passed (1447 existing warnings,
94.79s). These prove diagnostic and existing regression behavior, not new provider
prices or complete P5. No source-layer provider expansion was made speculatively.

No P6, strategy, broker/MT5, secrets/operator DB access, model training or push.
Kronos compatibility remains PARTIAL/source-contract-only; runtime is not a P5 gate.
