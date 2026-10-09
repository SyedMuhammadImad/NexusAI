# ADR-008 — Forward Demo and Live Authorization

Status: **ACCEPTED**  
Accepted during P0 governance review.

## Decision

NexusAI V2 recognizes four conceptual operating states:

- `HALTED` — no order submission.
- `RESEARCH` — historical/replay/research only; no broker execution.
- `DEMO` — controlled MT5 demo execution only after the roadmap reaches the relevant phase.
- `LIVE` — **LOCKED / UNAUTHORIZED throughout the current V2 roadmap**.

A configuration change alone must never be sufficient to enable real-money execution.

## Demo requirements

Before demo economic action is allowed, the execution boundary must attest the permitted demo account/environment and fail closed if account identity/type cannot be established. HALT and the authoritative safety gate remain effective in demo.

## Future qualification

Three months of forward demo is a minimum evidence window, not an automatic live unlock. Future qualification must consider sufficient trade evidence, performance after costs, drawdown, expectancy/risk-adjusted metrics where appropriate, source/strategy/instrument separation, risk violations, reconciliation failures, data-quality incidents and recovery behavior.

Passing qualification produces evidence for human review only.

## Live authorization

No agent, model, scheduler, source, confidence score, UI control or ordinary configuration value can authorize live money. Any future live-readiness effort requires a separate explicit human authorization and new safety/operational review outside current V2.
