# ADR-007 — Legacy Retention Policy

Status: **ACCEPTED**  
Accepted during P0 governance review.

## Decision

Use the lifecycle:

**QUARANTINE -> REPLACE -> PROVE -> DELETE_CANDIDATE -> HUMAN APPROVAL -> DELETE**

Legacy code is not automatically trusted because it exists or has isolated tests, and it is not automatically deleted because it is inactive.

## Rules

- Known defective legacy risk, compliance, portfolio and execution behavior must not be reactivated wholesale.
- The synthetic/random-price backtester must not produce V2 qualification claims.
- Old orchestrator/event-bus/learning code may be inspected as evidence or for isolated reusable logic, but reuse requires verified semantics and tests.
- Verified compatible parser and lifecycle/ledger foundations are preservation/reuse candidates.
- Coding agents may inspect, characterize and propose deletion candidates.
- Actual deletion requires dependency analysis, preservation/rollback planning, regression evidence and explicit human approval.

`DELETE_CANDIDATE` is never permission to delete.
