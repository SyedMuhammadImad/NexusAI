# P5 Alternative Historical Provider

Authority: owner's alternative-provider task; ADR-013/014/015/017. No P6 code,
strategies, broker connection, operator state or credentials are involved.

## Provider Evaluation (2026-09-15)

| Source | Evidence and disposition |
|---|---|
| EV Trading Labs | Selected public closed-year H1/H4 exports; all three instruments and 2021-2025 acquired without credentials or payment. Explicit local educational research attribution retained. |
| Dukascopy direct | Public export UI works and exposes hourly UTC BID/ASK. No direct market-data acquisition: website automated/database-use restrictions require a separately permitted route. Earlier AWS Requester Pays option needs scoped authorization/budget. |
| Stooq | Public World hourly archive and personal-use restriction verified. Owner-authorized CAPTCHA succeeded; browser download cancelled and direct route returned browser-verification HTML, not an archive. No bypass and no qualified data. |
| FXCM | Official free H1/M1 price catalogue covers FX pairs, not all requested metals/oil; sentiment/volume listings are not OHLC data. |
| Alpha Vantage | Public WTI interface is daily/weekly/monthly and key-based, insufficient for H1/H4. |
| Twelve Data | Commodity catalogue exists, but exact free entitlement/history/price basis not proven; key-based route not needed after working public export. |
| OANDA | REST data access needs account/token and licensing; no credentials sought or accessed. |

Primary references: [Dukascopy website terms](https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/),
[Stooq archives](https://stooq.com/db/h/), [FXCM catalogue](https://github.com/fxcm/MarketData),
[Alpha Vantage](https://www.alphavantage.co/documentation/),
[Twelve Data](https://twelvedata.com/commodities),
[OANDA introduction](https://developer.oanda.com/rest-live-v20/introduction/).
Availability statements above are dated observations, not permanent guarantees.

## Export Contract and Use

EV Trading Labs describes its exports as Dukascopy-derived candles. Closed years
at H1/H4 are public; M1/current-year access is outside this task. It grants free
use with attribution and disclaims accuracy. This project preserves attribution
and uses local educational research only; commercial/redistribution rights and
upstream sublicensing are not independently established.
[Provider specification and use terms](https://evtradelabs.com/data).

`ts`: Unix seconds, UTC bar OPEN. `o,h,l,c`: BID OHLC. `ao,ah,al,ac`: separate ASK
OHLC. `v`: retained as UNKNOWN units/meaning, not asserted exchange or tick volume.
H4 is UTC-anchored. Provider describes higher frames as precomputed M1 resamples.
Raw gzip, catalogue response, URL, annual bounds/count, SHA-256 and ingestion time
are retained. No missing prices are filled. These are native provider aggregates,
not independently audited tick completeness. Same source as above.

## Mapping

| Canonical research | Export ID | Interpretation | Future broker reference only |
|---|---|---|---|
| XAUUSD | XAUUSD | Gold/USD provider proxy | XAUUSDm |
| XAGUSD | XAGUSD | Silver/USD provider proxy | XAGUSDm |
| USOIL | WTI | WTI-labelled derivative/proxy; exact construction unverified | USOILm |

The provider identifies [WTI as Dukascopy-derived](https://evtradelabs.com/stats/WTI).
Dukascopy describes [LIGHT.CMD/USD](https://www.dukascopy.com/swiss/english/cfd/range-of-markets/wti-oil-cfd-trading/)
as a non-expiring WTI-linked CFD. This supports a CFD-proxy interpretation, but
does NOT prove EV's exact upstream instrument ID, adjustments, roll construction
or equivalence to Exness. Do not call this an exchange contract, physical spot,
or a proven continuous-futures series. No other oil series is combined with it.

## Implementation

- `core/rebuild/evtl_provider.py`: exact public catalogue binding, bounded requests,
  gzip/JSON parsing, strict numeric/native fields, annual size/count/bounds checks.
  An injected HTTP client is always fixture-marked, never silently real-qualified.
- `market_data.py`: additive provider/ASK contract. Legacy HistData payloads omit
  new fields, retaining previous content IDs and semantics. Cross-provider parents
  and mixed series reject. No old migration is rewritten.
- `export_research.py`: immutable qualification, hourly session evidence, native
  4H bid/ask consistency, unknown-gap exclusions, pinned query and K-line conversion.
- `research_reader.py`: `ResearchDatasetReader(store).query(qualification_id,
  start=aware_UTC, end=aware_UTC)` is provider-independent for qualified EV and
  retained HistData feed views. No latest-version or automatic provider selection.
- `provider_comparison.py`: paired prices/returns, offsets and lag diagnostics;
  no modification or splicing and no automatic equivalence verdict.
- `scripts/p5_alternative_acquire.py`: acquire all six 2021-2025 source series;
  no automatic qualification. Failed acquisition never publishes a partial dataset.
- `scripts/p5_alternative_audit.py`: saved-raw reparse/hash/count verification,
  qualification replay/reopen, 1H/4H comparison, pinned query, K-line contract,
  HistData comparison; reports in ignored `research/p5-market-data/` only.
- `scripts/p5_alternative_evidence.py`: verifies the audit hash, intersects all six
  qualified segment sets, repeats exact shared-range queries after reopen and
  publishes attribution-bearing metadata to the tracked closeout JSON, not raw data.

## Availability and Quality

The [upstream hours specification](https://www.dukascopy.com/swiss/english/forex/forex-trading-accounts/link/)
documents metal daily breaks and seasonal trading hours. The separate distributor
model uses New York 17:00-18:00 daily closure and Friday17:00-Sunday18:00 closure,
with `tzdata==2025.2` loaded explicitly instead of machine timezone settings.
It is a historical market inference, not official EV holiday or broker hours.
Its 2021-2025 applicability is checked against ALL observed hourly data, including
WTI; contradictions reject. Oil applicability is empirical corroboration, not an
independent upstream mapping attestation. No holidays are guessed into exemptions.

Within any accepted range every expected H1 slot is present. Native 4H bars must
match all available bid/ask constituents, and any missing expected constituent
breaks the 4H research range. Closure-only bins have no generated OHLC. Partial
open sessions are visible, not misreported as four complete trading hours.
Unexplained intervals include unconfirmed holidays, outages and early closes.

The calendar is retrospective quality metadata, not information available to a
historical strategy. P6 must keep chronological splits and must not select winners
using future prices or this closeout's longest-range selection.

## Kronos Boundary

`kronos_rows(view, as_of=...)` preserves open timestamps, OHLCV strings, dataset
and qualification IDs plus row hash; it rejects bars closing after `as_of`.
The primary K-line side is BID; ASK remains in canonical storage. UNKNOWN volume
must remain disclosed. This proves representability/lineage, not useful model
inputs, tensor preprocessing, runtime/checkpoints or training; those remain P8.

## Reproduction and Safety

Use the normalized credential-free guard from `knowledge/TESTING.md`; replace its
test invocation with `runpy.run_path` for the acquisition or audit script. Never
run the legacy application startup to acquire research data. Raw evidence and the
research SQLite store stay under the owned ignored research root. No redistribution
or push. Exact IDs, test results and residual limitations are in the closeout audit.
