# ADR-010 - Initial P2 Demo Safety Policy

Status: **ACCEPTED**
Recorded: 2026-09-11.
Policy version: **P2-DEMO-1.0**.

## Authority

The owner explicitly approved the 21 sections in the P2 POLICY LOCK request.
Their verbatim authoritative record is the Accepted Policy Clauses section of
`../Components/P2-SAFETY-POLICY.md`. This ADR accepts those supplied decisions,
not unprovided calculation assumptions or permission to implement the engine.

## Decision

Adopt the recorded initial demo-only limits, eligible instruments, capital basis,
cost-adjusted minimum R:R, evidence ages, reservation lifecycle, HALT precedence,
technical compliance and immutable policy-version requirements. Each future
safety decision must store its immutable policy version/hash. Policy changes
require a new version; recorded prior decisions remain immutable.

This resolves ADR-003's previously unapproved numerical limits to the extent
specified by the owner. It supplements, rather than replaces, ADR-003's fail-closed
single authoritative gate and final veto. Legacy defaults are not authoritative.
PDT/wash-sale concepts are excluded from authoritative P2 policy unless separately
shown applicable; this does not authorize deleting their legacy source code.

ADR-001 source eligibility, ADR-002 source-time policy, ADR-004 broker truth,
ADR-007 retention and ADR-008 demo-only restrictions remain intact. Broker-data
freshness is not a replacement for the separate live-source freshness window.
ADR-005 and ADR-006 remain DEFERRED. No execution or strategy qualification follows.

## Accepted Decision vs Gate Completion

Policy status: **LOCKED**. On 2026-09-11 the owner explicitly approved C01-C03
as authoritative clarifications of **P2-DEMO-1.0** before implementation:

- C01: projected used margin / current valid EQUITY, capped at <=25%; invalid,
  missing or stale equity rejects. MIN(equity,balance) is not this denominator.
- C02: existing-position risk uses current conservative executable-side market
  price to active SL, not original entry. Invalid/missing stops require
  reconciliation; stale quotes reject new admission. Apparent triggered stops
  inconsistent with broker state retain risk as reconciliation ambiguity.
- C03: spread is ASK-BID. MARKET BUY references ASK and moves adversely upward;
  MARKET SELL references BID and moves adversely downward. Percentage allowances
  use base executable-side entry-to-SL distance before adverse allowance.
  MARKET source entry may be absent and is provenance only when present.
  LIMIT requires explicit entry for risk/R geometry and current quotes for
  quality checks; its quote deviation compares executable quote to limit entry.
  Contradictory LIMIT semantics reject rather than reinterpret.

Full normative details are in the component note's Accepted C01-C03 Clarifications.
These decisions supersede the earlier unapproved recommendations and close the
initial policy gate. The owner expressly retains version 1.0; later policy changes
still require a new version. No existing runtime decision is rewritten.

Implementation ready: **YES**, subject to separate implementation authorization.
No unresolved initial P2 policy blocker remains. Readiness is not implemented or
tested safety, demo authorization, or P2 phase completion.

## Original Policy-Recording Consequences

P1 remains VERIFIED_COMPLETE. P2 implementation remains NOT_STARTED and the
application stays HALTED. This is a documentation-only authorization, not approval
to access an operator database, secrets or broker, or to modify application code.
No runtime policy hash is claimed to exist yet; its implementation and tests are
future P2 work. No commit/push or regression-test run accompanies this decision.

## Subsequent Implementation Evidence (2026-09-11)

The owner separately authorized P2 implementation. The numerical policy and these
accepted decisions are unchanged. P2 is now fixture-verified as documented in
`../Components/P2-SAFETY-ENGINE.md`: 79 focused P2 / 94 P1 / 297 broad tests passed.
Per-decision policy hashes and effective config-N versions are implemented; the
base policy remains P2-DEMO-1.0. No broker actions, operator migration, real-money
authorization or P3 work follows from this bounded evidence.
