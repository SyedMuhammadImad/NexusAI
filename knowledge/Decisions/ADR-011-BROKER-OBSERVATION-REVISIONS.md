# ADR-011 - Revision-Aware Broker Observations

Status: **ACCEPTED**
Authority: explicit human approval, 2026-09-12.

## Decision

Broker observations are immutable, append-only evidence. Corrections create new
observations, never replacement records. Persist observation identity, account,
broker entity type/identity, available broker version, superseded observation,
observation time, broker-reported time, normalized payload, raw evidence reference
and normalizer version. Retain complete history, including conflicting and
out-of-order evidence. Identical repeated evidence is idempotent.

Current state is a deterministic projection, not the original evidence record.
Only authoritative same-entity identity, valid normalization, consistent lineage
and possible economic history permit projection. Observations are not economic
fills: one broker deal remains one entity regardless of observation count.
Canonical request -> attempt -> order -> deal -> position lineage remains exact.

Unresolvable ordering/conflicts retain all evidence, make reconciliation ambiguous,
retain capacity, prohibit resubmission and enforce existing HALT policy. No original
evidence is deleted or rewritten to clean the latest state. No P2 limits change.

## Ordering and Implementation Boundary

Broker revision sequences, when actually supplied, or documented broker update
timestamps may establish order. Local receipt time is not a broker revision clock.
Native deal execution timestamps are not correction timestamps; differing payloads
without an authoritative revision order are ambiguous. Explicit supersession must
refer to the same entity, be acyclic and agree with available ordering evidence.
Missing predecessors remain unresolved until supplied. Out-of-order arrivals do
not roll back a newer current projection.

Immutable initial P3 rows remain preserved. An additive observation journal and
derived projection supply revision-aware state. Execution consumes only validated,
economically consistent projections; raw external or unsupported evidence never
creates an owned trade. Balance/cancellation records are retained with their native
types, not disguised as ordinary fills. Unsupported economic reconciliation stays
HALTed until authoritative evidence resolves it; this is fail-closed handling,
not an invented correction or local close.

This resolves the human-decision blocker in
../Audits/P3-NATIVE-EVIDENCE-COMPATIBILITY.md, not native qualification or operator
permission. Demo account attestation/isolation and all prior phase gates remain.
