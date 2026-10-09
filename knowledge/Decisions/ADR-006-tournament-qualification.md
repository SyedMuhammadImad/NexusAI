# ADR-006 — Tournament Qualification

Status: **ACCEPTED / LOCKED**, owner P7 batch authorization, 2026-09-22.
Policy: **P7-RESEARCH-1.0**.

## Decision state

Research-only tournament. No execution qualification or promotion is authorized.
Only P5 qualified data and frozen P6 TOURNAMENT_READY implementations enter.
EXPERIMENTAL, underdefined and disabled concepts are EXCLUDED. Unsupported
instrument/timeframe combinations are EXCLUDED with their reason recorded.

Use the existing qualified half-open UTC interval 2025-09-02T00:00 through
2025-11-27T20:00. Divide elapsed UTC time 70% development / 30% OOS, rounding the
boundary down to the common 4H candle boundary; report nominal and actual fractions.
This deterministic calendar split is common to all instruments/timeframes, with
no shuffling/tuning. P6 warm-up and flat-start/right-censor semantics apply.

Per strategy/instrument/timeframe: >=50 resolved total and >=20 resolved OOS.
Resolved sample/win denominator is WIN+LOSS+BREAKEVEN, as in P6. P6 priced metrics
include TIMEOUT, excluding UNKNOWN/AMBIGUOUS without assigning zero returns.
Hard OOS gates: expectancy >0R; PF>=1.20; win rate>=0.35; max drawdown<=10R;
(AMBIGUOUS+UNKNOWN)/all research trades<=0.10; sample and data/leakage checks pass.
Inclusive thresholds pass at equality. The explicitly strict positive expectancy
requirement rejects zero, consistent with the owner's <=0 degradation condition.
Undefined/nonfinite metrics cannot pass; undefined PF is not infinity.

Positive development expectancy becoming <=0 OOS fails degradation. When both
PFs are finite and development PF>0, (devPF-oosPF)/devPF>0.50 fails; exactly0.50
passes. Otherwise PF degradation is NOT_APPLICABLE, not fabricated; OOS PF must
still pass its own gate. Sharpe is informational only and may remain unavailable.

P6 BID/ASK plus 5%-of-stop-distance adverse slippage on each side applies.
Commission remains NOT_INCLUDED unless independently evidenced; current study
uses the frozen P6 excluded-commission basis. Strategies/parameters are frozen.
Every record carries SHORT_SAMPLE_RESEARCH_ONLY and never economic permission.

Classification: data/leakage/cost integrity failure => REJECTED. Insufficient
sample or missing metric evidence => INSUFFICIENT_EVIDENCE. Otherwise any failed
gate => REJECTED, all passed => RESEARCH_QUALIFIED. All individual gates remain
visible regardless of final status. Pooling instruments/timeframes to rescue a
sample or qualification is forbidden; aggregation is counts of separate cells.

Qualified results may be displayed by decreasing OOS expectancy, then PF, then
stable strategy/instrument/timeframe identity. This is a reporting order, not
winner selection, execution selection or a new reset/forward-clock rule.

Correlation uses aligned UTC daily realized R, with unresolved holding dates
excluded, zero only for observed dates without a realization, and nonzero variance
on at least two common dates. Report sample counts and SHORT_SAMPLE_RESEARCH_ONLY;
no significance claim. Absolute Pearson correlation>=0.80 forms graph-connected
high-correlation clusters; connectivity does not mean every pair exceeds0.80.
No qualified pair/evidence => explicit not-applicable/insufficient result.

Bounded diagnostics: separate all instruments/frames; split OOS in half on a 4H
boundary and replay each half; remove single best/worst priced OOS trade with
deterministic chronological tie handling; stress slippage to10% using P6 replay.
These are sensitivity diagnostics, not parameter tuning or extra promotion gates.
No shared-capital portfolio performance is inferred from independent experiments.

P7 completes when reproducible evaluation and regression gates pass even if the
result is NO_STRATEGY_RESEARCH_QUALIFIED. P8 remains a separate authorized phase;
ADR-005 remains deferred. Historical P0 deferred status is preserved as history.

Owner P7 addition: a dedicated read-only Tournament Arena is also a P7 exit gate.
It consumes persisted P7/P6 evidence, not browser-computed gates. Intermediate
snapshots are ACTIVE/AT_RISK, with PENDING gates where evidence is incomplete.
Final REJECTED/INSUFFICIENT_EVIDENCE/RESEARCH_QUALIFIED transitions occur at the end
of OOS; no unapproved irreversible early elimination rule is introduced. Results
remain independently classified by instrument/timeframe, never symbol-pooled.

## Current safe default

No strategy may be promoted to execution by this research tournament.

## When to resolve

Resolved by the owner's explicit P7 policy above after P6 closeout d058a64.
