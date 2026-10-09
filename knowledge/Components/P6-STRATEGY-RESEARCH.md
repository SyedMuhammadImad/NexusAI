# P6 Deterministic Strategy Research

Authority: owner's P6 implementation task, ADR-003/004/006/012/013/017. Research
only; no source-registry, P2, execution-engine, broker or application wiring change.
Technical tournament readiness does NOT resolve ADR-006 ranking/qualification.
No new economic policy or architectural decision is required for this bounded
implementation of the already authorized P6 research plane.

## Components and Interfaces

- `backend/core/rebuild/research_strategies.py`: frozen BaseStrategy catalogue,
  streaming Decimal Features and read-only Frame. No outcomes/account/clock inputs.
- `backend/core/rebuild/strategy_research.py`: pinned ResearchData loader, closed
  context iterator, cost/geometry gate, replay, outcome reconstruction, metrics,
  canonical representation and append-only ResearchLedger.
- `scripts/p6_research.py`: fixed study from committed P5 evidence, offline only.
- `backend/tests/test_p6_research.py`: synthetic fixtures only, including actual
  child-process death/rollback, concurrent/restarted ledger and P4 integration.
- `knowledge/Audits/P6-RESEARCH-RESULTS.json`: portable study/metrics/run IDs.
  Exact trades/signals/configuration are immutable `p6_runs` / `p6_trades` in the
  existing owned `research/p5-market-data/market-data.sqlite3`, NOT an operator DB.

Additive research schema marker 7 creates the two new tables and update/delete
guards. Prior P5 tables/versions/observations are unchanged. Each entire result
publishes in one BEGIN IMMEDIATE transaction. Exceptions/process death roll back;
concurrent retries compare the exact artifact before returning the same identity.
No wall-clock field participates in a replay. Artifact/run/trade IDs hash canonical
JSON binding engine, rules, exact parameters, dataset/qualification/row/provenance
hashes, costs, periods and any secondary dataset. Corrections require new identity.

P7 consumption: `ResearchLedger(store).read(run_id)` verifies artifact hash and
returns the complete JSON contract. The study index identifies exact run/artifact
IDs, period, technical eligibility and metrics without strategy-specific parsing.
It never means "latest" and does not select a winner or authorize execution.

## Data and Splits

Primary: EV Trading Labs BID OHLC plus separate ASK OHLC; volume UNKNOWN and unused.
HistData is preserved separately and not spliced. Source/provenance/range identity
comes from P5-ALTERNATIVE-DATA-EVIDENCE.json; all six complete IDs are repeated in
the P6 study index. Loader uses ResearchDatasetReader and rejects unqualified,
fixture, wrong-ID, mixed, unordered or one-sided evidence. No network acquisition.

All UTC, half-open: qualified history **2025-09-02 00:00 to 2025-11-27 20:00**.
In-sample ends **2025-10-15 00:00**; out-of-sample starts there. Split selected as
a fixed calendar boundary, not optimized. Warm-up may use earlier qualified rows,
but each period begins flat. No earlier-period position or label leaks across the
split. Unfinished trades are UNKNOWN/right-censored, not forcibly profitable or
silently closed. The last closed pre-split bar may signal an entry at the OOS
boundary; all its features were available at that instant.

Each instrument has 1,445 H1 and 389 H4 observations. The full acquired five-year
archive is NOT the research range. Qualification/calendar selection was
retrospective; this OOS partition is not prospective or independently held-out
performance validation. Long warm-ups legitimately leave few trades.

## Exact Feature and Parameter Rules

Versions: `p6-rules-v1`, `p6-features-v1`, `p6-replay-v3`, `p6-costs-v1`.
Decimal precision 40. Strategy parameters are ATR period 14, stop distance 2 ATR,
target distance 2 times that stop distance. ATR is an intentional signal rule,
never a fallback. Only stop multiplier/reward multiplier are configurable in v1;
unsupported indicator-period overrides reject rather than being ignored.

EMA seeded with first N-close arithmetic mean, then alpha=2/(N+1). MACD uses
12/26 EMA and 9 EMA signal, seeded from nine available MACD values. RSI uses
Wilder average gains/losses (14 and 2), first N price differences; flat=50 and
positive gains with zero losses=100 are valid, not bugs. ATR14 uses Wilder
smoothing seeded from 14 true ranges; first TR=high-low. Supertrend uses midpoint
+/-3 ATR, carried final bands, prior-close reset and direction changes only.

Rolling-ADX is explicitly a RESEARCH VARIANT, **not Wilder ADX**: directional
movement sums/TR sums over 14 bars, then arithmetic mean of 14 available DX values.
Threshold25 and a DI-difference zero crossing. Stochastic14 and Williams14 use
rolling range (flat range maps stochastic to50). Bollinger20 uses population
standard deviation and two deviations. CCI20 uses typical price, mean absolute
deviation and scale0.015. All exact feature/rule specifications are also stored in
each result configuration, not hidden in a display name.

## Catalogue and Technical Eligibility

All entries use BUY/SELL symmetric definitions. Crossover means previous <= and
current > for BUY, >= and < for SELL. Re-entry thresholds require prior strictly
outside and current reaching/crossing inside. Rolling "prior" windows exclude the
current candle. No optimization was performed. Warm-up counts are source bars.

| ID | Family / Rule | Warm-up | Eligibility |
|---|---|---:|---|
| p6-01 | TREND: EMA9 crosses EMA21 | 22 | TOURNAMENT_READY |
| p6-02 | TREND: EMA20 crosses EMA50 | 51 | TOURNAMENT_READY |
| p6-03 | TREND: EMA50 crosses EMA200 | 201 | TOURNAMENT_READY |
| p6-04 | TREND: MACD crosses signal | 35 | TOURNAMENT_READY |
| p6-05 | TREND: Supertrend direction flips | 15 | TOURNAMENT_READY |
| p6-06 | TREND: rolling-ADX>=25 and DI zero crossing | 28 | TOURNAMENT_READY |
| p6-07 | TREND: close crosses prior20 high/low | 22 | TOURNAMENT_READY |
| p6-08 | TREND: close crosses EMA200 (pullback/re-entry proxy) | 201 | TOURNAMENT_READY |
| p6-09 | MEAN_REVERSION: RSI14 re-enters30/70 | 16 | TOURNAMENT_READY |
| p6-10 | MEAN_REVERSION: opposing 10-bar price/RSI changes, RSI<40/>60; not pivot divergence | 26 | EXPERIMENTAL |
| p6-11 | MEAN_REVERSION: outside prior Bollinger band, inside current band | 21 | TOURNAMENT_READY |
| p6-12 | MEAN_REVERSION: stochastic re-enters20/80 | 15 | TOURNAMENT_READY |
| p6-13 | MEAN_REVERSION: Williams re-enters-80/-20 | 15 | TOURNAMENT_READY |
| p6-14 | MEAN_REVERSION: RSI2 re-enters10/90 | 15 | TOURNAMENT_READY |
| p6-15 | MEAN_REVERSION: one outer Bollinger band touched by low/high; both => no signal | 20 | TOURNAMENT_READY |
| p6-16 | MEAN_REVERSION: CCI re-enters-100/100 | 21 | TOURNAMENT_READY |
| p6-17 | BREAKOUT: previous completely observed UTC date high/low | 49 | TOURNAMENT_READY |
| p6-18 | BREAKOUT: prior20 range<=4 current ATR; close crosses range | 22 | TOURNAMENT_READY |
| p6-19 | BREAKOUT: fixed London-labelled UTC window, H1 only | 24 | TOURNAMENT_READY |
| p6-20 | BREAKOUT: fixed NY-labelled UTC window, H1 only | 24 | TOURNAMENT_READY |
| p6-21 | BREAKOUT: previous completely observed ISO UTC week high/low | 241 | TOURNAMENT_READY |
| p6-22 | BREAKOUT: previous close broke its prior20 range; current wick retests level and closes beyond | 22 | EXPERIMENTAL |
| p6-23 | BREAKOUT: genuine volume-spike breakout unavailable | 20 | DISABLED_VOLUME_SEMANTICS |
| p6-24 | STRUCTURE: prior20 H/L both above/below preceding disjoint20; current close breaks recent range | 41 | EXPERIMENTAL |
| p6-25 | STRUCTURE: wick sweeps prior20 extreme then closes back inside; both sides => no signal | 21 | EXPERIMENTAL |
| p6-26 | STRUCTURE: third candle low>first high (BUY) or high<first low (SELL) | 15 | EXPERIMENTAL |
| p6-27 | STRUCTURE: order-block selection/displacement/mitigation rules not defined | 1 | INSUFFICIENT_DEFINITION |
| p6-28 | STRUCTURE: wick crosses 61.8% prior20 range retracement, closes beyond, EMA50 directional filter | 50 | EXPERIMENTAL |
| p6-29 | STRUCTURE: double-pattern pivot/tolerance/confirmation rules not defined | 1 | INSUFFICIENT_DEFINITION |
| p6-30 | STRUCTURE: head/shoulders pivot/symmetry/neckline rules not defined | 1 | INSUFFICIENT_DEFINITION |

30 concepts, 26 implemented: 20 technically ready, 6 experimental, 3 underdefined,
1 disabled. No claim that pattern proxies capture institutional/discretionary
meaning. Every implemented rule has positive BUY/SELL and absent-evidence tests.
Ready means reproducible P7 input, not statistical/economic qualification.
London/NY H4 combinations explicitly INSUFFICIENT_DATA, not silently enabled.

## Session and Context Conventions

Fixed UTC research convention v1, not claims about official London/NY opens:
London range [06:00,08:00), signals from bars opening [08:00,11:00).
NY range [11:00,13:00), signals from bars opening [13:00,16:00).
Both H1 range candles must exist. No DST adjustment and no HistData calendar use.
Dates/weeks refer to the preceding observed full UTC period, excluding the first
partly observed warm-up date/week. Closed-market missing hours are not filled.

Optional H4 context for H1 is exposed only once context.closed<=signal bar.closed;
identity/provider/range must match and both dataset IDs are recorded. Current
defaults do not use context as a filter. No partial/future H4 candle is exposed.

## Replay, Prices and Outcomes

Signal at closed source bar; next observed qualified bar's OPEN is the reference.
BUY uses ASK, SELL BID. Entry slippage is adverse 5% of |base entry-SL|. This is a
versioned research assumption, NOT measured broker slippage. The same absolute
adverse allowance applies to exit. Known closures may bridge observations; unknown
gaps cannot. Stop/target are never shifted to make a gapped entry admissible.

Geometry and cost-adjusted reward/loss must pass >=1.5 at entry. Loss denominator
=|modeled entry-SL|+exit slippage+known commission. Reward subtracts exit slippage
and known commission. Numeric/action/geometry failure rejects; no ATR repair.
Commission contract is round-trip quote currency per instrument unit with an
explicit evidence reference. Unknown commission is EXCLUDED_UNKNOWN in every
result; excluding it is not equivalent to verified zero fees. No financing,
overnight swaps, leverage, contract multipliers, market impact or volume fills.

Long barriers use BID; short barriers ASK. Opening gaps can prove which barrier
already passed at OPEN. Stops fill at worse open, targets never get favorable gap
improvement. Intrabar both-barrier reach => AMBIGUOUS. Exact H1 constituents may
resolve an H4 ambiguity only if both-side OHLC reconstruct and identities/ranges
match; unresolved H1 remains AMBIGUOUS. No invented tick order.

TP-first WIN, SL-first LOSS under ADR-004. Barrier outcome does not change merely
because costs reduce net profit. No unrequested breakeven-management strategy;
BREAKEVEN is supported in the metric contract, not manufactured by barrier logic.
24 observed bars without barrier => TIMEOUT at executable-side close. Research
split/range ending sooner => UNKNOWN, no estimated terminal PnL. Missing entry
bar is a signal disposition, not a phantom entered position. Intrabar exit time is
an interval, never exact; opening-gap and TIMEOUT timestamps are known.

One research position at a time per strategy/series/window, independent of other
strategies/instruments. Candidates during an open trade and on its exit bar are
recorded BUSY (explicit one-bar signal cooldown). Signals are still computed
without outcome inputs; future exit scanning only reconstructs the already fixed
trade. No cross-strategy portfolio, risk allocation or P2 approval is implied.

## Metrics and Boundaries

Counts include all six outcomes and all signal dispositions. Win-rate denominator
is WIN+LOSS+BREAKEVEN; TIMEOUT excluded from this denominator. Average R/expectancy,
total R and trade-R drawdown use priced outcomes INCLUDING TIMEOUT; UNKNOWN and
AMBIGUOUS excluded, not assigned zero. Profit factor is positive priced R divided
by absolute negative priced R; no losses => null, not infinity. Drawdown starts at
zero and is in additive R units, not account percent. Missing outcomes break the
negative-priced streak; that is an observed streak, not proof of hidden outcomes.

Holding time is the known duration or upper bound of the outcome bar. Exclusion
rates/counts and zero-trade results are always shown. Sharpe is withheld: no
account-return series or accepted sample policy exists. Return/drawdown is supplied
only for positive drawdown with a descriptive, non-annualized warning. No parameter
sweep, selected winner, significance, profitability or broker-fill claim follows.

`canonical_signal()` maps price/direction/SL/TP/time/provenance identity to P1 v2;
Decimal originals remain in research evidence. It creates no lifecycle DB row.
The P4 integration test explicitly persists a mapped fixture and proves strategy
NONE eligibility, idempotent ingestion, denied admission and zero P3 attempts.
No operational strategy registration or secret access is needed by this module.

## Verification and Next Gate

Evidence counts/run IDs and failure history are in TESTING.md and the P6 closeout
audit. Focused and broad guarded tests are mandatory before marking complete.
Owner explicitly accepts short/zero/negative samples as research evidence, not
framework failure. This clarifies the earlier sufficient-trades intent without
inventing ADR-006 minimums. P7 must resolve that deferred policy before tournament
qualification. P3 operator verification stays DEFERRED; broker HARD DISABLED.
