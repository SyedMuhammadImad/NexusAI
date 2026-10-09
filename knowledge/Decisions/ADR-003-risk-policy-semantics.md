# ADR-003 — Risk Policy Semantics

Status: **ACCEPTED**  
Accepted during P0 governance review.

## Decision

NexusAI V2 has one authoritative pre-execution safety gate combining deterministic risk and compliance decisions.

The gate must evaluate, as applicable:

- persistent HALT / kill state;
- account/broker eligibility;
- finite numeric values and recognized action/direction;
- direction-aware entry/SL/TP geometry;
- minimum reward:risk;
- position sizing and exposure;
- position/concurrency limits;
- drawdown limits;
- instrument restrictions;
- correlation policy;
- risk reservations for concurrent requests.

A rejection cannot be overridden by WhatsApp source, manual input, strategy confidence, ML confidence, another agent, or UI action.

The initial global minimum reward:risk floor is **1.5**, subject to future explicit policy ADR amendment.

If required risk/account/instrument data is missing, stale, non-finite, contradictory or cannot be converted reliably, the safety decision fails closed: **REJECT / NO ECONOMIC ACTION**.

## Invariants

- Safety decisions are persisted and attributable to a policy version.
- Compliance is a prerequisite decision, not a parallel advisory subscriber.
- HALT is enforced at the economic boundary.
- Exact numerical limits for per-trade risk, drawdown, exposure, weekly boundaries and correlation are configuration/policy work and must not be invented by coding agents.
