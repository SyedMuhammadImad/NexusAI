# NexusAI V2 — Decision Index

P0 governance decisions accepted by the user are authoritative where they amend the original V2 proposal.

| ADR | Decision | Blocks | Status |
|---|---|---|---|
| ADR-001 | Signal source interfaces | P4 | **ACCEPTED** |
| ADR-002 | Timestamp/freshness policy | P2/P4 | **ACCEPTED** |
| ADR-003 | Risk policy semantics | P2 | **ACCEPTED** |
| ADR-004 | Outcome label semantics | P5/P8/P9 | **ACCEPTED** |
| ADR-005 | Three separate research tracks and temporal labels, P8-RESEARCH-1.0 | P8 | **ACCEPTED / LOCKED**; owner policy 2026-10-01; no execution authority |
| ADR-006 | Research-only tournament qualification, P7-RESEARCH-1.0 | P7 | **ACCEPTED / LOCKED**; owner policy 2026-09-22 |
| ADR-007 | Legacy retention policy | cleanup/all phases | **ACCEPTED** |
| ADR-008 | Forward demo and live authorization | P3/P10+ | **ACCEPTED** |
| ADR-009 | Historical archive identity/dedup semantics | maintenance/P5 | **ACCEPTED** |
| ADR-010 | Initial P2 demo safety policy, P2-DEMO-1.0 | P2 | **ACCEPTED**; policy LOCKED; C01-C03 approved |
| ADR-011 | Revision-aware append-only broker observations | P3 | **ACCEPTED**; explicit human approval 2026-09-12 |
| ADR-012 | Split P3 engineering/operator gates; sequential non-executing P4-P9 | P4-P10 dependencies | **ACCEPTED**; explicit owner roadmap amendment 2026-09-13 |
| ADR-013 | P5 data qualification / P6 strategy replay | P5/P6 | **ACCEPTED** |
| ADR-014 | Observation validity separate from continuity | P5 | **ACCEPTED**; explicit owner valid-bar retention requirement |
| ADR-015 | Versioned session-aware research qualification | P5 | **ACCEPTED**; owner session-model task; market inference remains explicit |
| ADR-016 | Empirical versioned HistData research calendars | P5 | **ACCEPTED**; explicitly forbidden for broker/execution eligibility |
| ADR-017 | Alternative single-provider native-bar research qualification | P5 | **ACCEPTED**; owner alternative-provider task; no HistData relaxation or execution eligibility |
| ADR-018 | V1 scope; frozen P5-P7, deferred P8, full P9 independent of P8; conditional demo integration | V1/P3/P9 | **ACCEPTED for scope only**; not broker qualification or changed P2 limits |
| ADR-019 | Qualification-start baselines and dedicated operator provisioning | V1/P3 | **ACCEPTED**; baseline semantics retained; dedicated Windows arrangement superseded by ADR-021 |
| ADR-020 | Non-executing operator bootstrap sequencing | P3 | **ACCEPTED**; no submission authority; removed infrastructure cannot be recreated under this approval |
| ADR-021 | Remove dedicated Windows account/profile; current-profile work only | V1/P3 | **ACCEPTED**; broker execution stays disabled pending replacement qualification |
| ADR-022 | Cooperative current-profile DEMO operator boundary | V1/P3 | **ACCEPTED** 2026-10-05; explicit same-user trust, no native qualification implied |

## Governance result

ADR-012 separates P3 ENGINEERING VERIFIED_COMPLETE (bounded non-operational scope)
from P3 OPERATOR DEMO VERIFICATION DEFERRED / PENDING. P4 is READY, P5-P9 follow
sequentially in NON-EXECUTING mode, and P10 requires P3 operator verification + P9.
Broker execution remains HARD DISABLED. No P4 implementation, actual broker
qualification or live-readiness authorization follows from this documentation task.
The accepted dependency amendment does not resolve ADR-005/006 or weaken ADR-008/010/011.

The policy decisions required to design P1 are resolved. ADR-005 and ADR-006 are intentionally deferred because their decisions are not needed for the canonical lifecycle foundation.

The preceding P0/P3 dependency statements preserve their historical scope.
On 2026-09-22 the owner explicitly resolved ADR-006 for research-only P7.
The preceding P8 deferral is historical. On 2026-10-01 the owner explicitly
authorized P8 research and locked ADR-005. This supersedes only ADR-018's P8
deferral; no coding agent may invent model activation or economic authority.

## P5/P6 Boundary (2026-09-14)

Accepted ADR-013 records the owner's move of strategy replay from P5 to P6.
P5 qualifies real datasets and their deterministic query interface. Bounded
uncertainty remains visible/excluded; no strategy or execution authorization.

## P2 Policy Record (2026-09-11)

The owner's 21 initial demo policy sections are accepted in ADR-010 and recorded
verbatim in `Components/P2-SAFETY-POLICY.md`. All supplied numerical limits replace
the prior missing values; they are not legacy defaults. The owner subsequently
approved C01-C03 for the same initial version: policy LOCKED, implementation ready.
The policy-recording task itself did not authorize engine changes. The owner
subsequently authorized P2 implementation; its fixture verification is recorded
in Components/P2-SAFETY-ENGINE.md. P2 is now VERIFIED_COMPLETE without changing
the accepted numerical policy or authorizing P3.
