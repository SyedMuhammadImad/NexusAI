# NexusAI V2 — Project Charter

## Mission

Build a demo-only automated trading research/execution system whose economic actions are attributable, risk-authorized, broker-reconciled and evidence-backed.

## Current Product Reality

The active application is a halted authenticated historical-review application
with fixture-verified canonical lifecycle integration and an explicit historical
source/signal bridge. The legacy trading stack is inactive and contains reproduced
defects. NexusAI is **not currently an integrated trading system**: safety is now
fixture-verified; native-shaped broker reconciliation is engineering-verified,
but actual operator/demo execution remains deferred. P4 provenance and P5 real
data are verified in their bounded scope; P6 now provides reproducible historical
research, not broker-confirmed outcomes or qualified profitability.

## Core Outcomes

1. Every executed trade has exact lifecycle lineage from source to broker-confirmed outcome.
2. Deterministic risk/compliance policy controls every economic action.
3. Retry/crash behavior cannot create duplicate economic action.
4. Human and bot sources remain distinct.
5. Research uses real historical data and reproducible replay.
6. ML/RL cannot influence execution before their evidence gates pass.

## Explicitly Out of Scope Now

- live-money trading;
- RL;
- autonomous strategy generation;
- unqualified trader imitation;
- speculative new agents;
- performance claims from legacy PnL or synthetic backtests;
- cosmetic dashboard work without trustworthy metrics.

## Current Priority

**P0/P1/P2/P4/P5/P6/P7 VERIFIED_COMPLETE within their recorded scope (2026-09-22).**
M2 remains COMPLETE_WITH_RECORDED_INCIDENT; its evidence is preserved in
Components/P1-LIFECYCLE-MAP.md and Audits/P1-M3-EXIT-GATE.md. P3 engineering is
verified within non-operational/fixture/native-normalization scope under ADR-012;
P3 operator verification remains DEFERRED. Combined P3 is not fully verified.

P6 research evidence and its short-sample/cost limitations are recorded in
Audits/P6-CLOSEOUT.md. P7 now has a locked research tournament and read-only Arena;
zero cells qualified under unchanged thresholds. Evidence: Audits/P7-CLOSEOUT.md.
Next priority is deferred ADR-005 before P8. Research eligibility cannot enable trading.
Broker execution remains HARD DISABLED. No actual account, credentials or
operator database was used to produce the research results.

## Definition of Project Success

Success is not “many agents.” Success is a verified, recoverable, demo-only system with exact economic lineage, deterministic safety, broker-confirmed accounting, reproducible research and documented qualification evidence.
