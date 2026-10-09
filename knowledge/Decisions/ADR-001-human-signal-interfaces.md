# ADR-001 — Signal Source Interfaces

Status: **ACCEPTED**  
Accepted during P0 governance review.

## Decision

NexusAI V2 recognizes five source classes.

### Execution-capable sources

1. `WHATSAPP_HUMAN` — live signals from an explicitly configured human source. Eligible for **demo** execution only after canonical validation and the common safety gate.
2. `MANUAL` — manually entered signals. Eligible for **demo** execution only after canonical validation and the common safety gate.
3. `NEXUSAI_STRATEGY` — bot-generated signals. Execution remains disabled until the relevant strategy/research qualification phase authorizes it; when enabled, it still uses the same common safety gate.

### Research/non-execution sources

4. `HISTORICAL_WHATSAPP` — imported historical messages/signals for review, outcome reconstruction, research, backtesting and later trader-pattern/ML research. Historical imports can never execute merely because they were imported.
5. `SCREENSHOT` — review/research extraction initially. It is not an execution-capable V2 source during the current roadmap.

## Invariants

- Every source is tagged with immutable provenance.
- Human and bot performance remain separate.
- No source may bypass deterministic validation, HALT, risk, compliance or execution controls.
- Historical data may later contribute to ML only when outcomes meet the accepted evidence/label rules.
- Adding a new execution-capable source requires a new or amended ADR.

## Consequences

P4 may implement the approved source taxonomy. Screenshot-to-execution is out of scope unless explicitly re-authorized.
