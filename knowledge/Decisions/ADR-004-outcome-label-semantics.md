# ADR-004 — Outcome Label Semantics

Status: **ACCEPTED**  
Accepted during P0 governance review.

## Decision

Canonical terminal/evaluation states include:

- `WIN`
- `LOSS`
- `BREAKEVEN`
- `TIMEOUT`
- `AMBIGUOUS`
- `UNKNOWN`
- `CANCELLED`

### Demo/live broker-observed lifecycle

Broker evidence is authoritative for economic position state and closure. Local price inference must not manufacture a broker-confirmed close.

### Historical reconstruction

For directionally valid historical trades using approved real market data:

- TP before SL -> `WIN`
- SL before TP -> `LOSS`
- both barriers reachable inside the same bar when ordering cannot be proven -> `AMBIGUOUS`
- insufficient/unreliable evidence -> `UNKNOWN`
- evaluation window expires without a defined terminal barrier -> `TIMEOUT`

No intrabar path may be invented from OHLC alone.

### ML eligibility

`WIN` and `LOSS` may become binary profitability labels when all future dataset requirements are satisfied.

`AMBIGUOUS`, `UNKNOWN`, and `CANCELLED` are excluded from binary profitability training.

Treatment of `BREAKEVEN` and `TIMEOUT` is deferred to ADR-005 because it depends on the exact ML objective.

## Invariants

- Partial fills, partial closes, multiple deals, costs and strategy/manual exits require broker/evidence-aware accounting.
- Uncertainty is represented explicitly rather than forced into WIN/LOSS.
