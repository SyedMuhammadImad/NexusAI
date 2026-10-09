# P2 Authoritative Safety Engine

Subsequent P3 integration (2026-09-11): revalidate_reserved reuses the P2 calculator
at the exact reserved volume inside the serialized execution boundary. P2's locked
numerical policy/hash manifest and ordinary admission semantics are unchanged.
P3 remains PARTIAL / FIXTURE_ONLY; see P3-EXECUTION-RECONCILIATION.md. Current P2
regression: 79 passed; final broad fixture suite: 401 passed. This does not grant
operator/broker qualification or authorize native app dispatch.

Date: 2026-09-11. Status: VERIFIED_COMPLETE within the non-executing P2 scope.
Authority: ADR-003, ADR-008, ADR-010 / P2-DEMO-1.0.
Policy baseline commit: 9739f26 (separate from implementation).
Verified implementation commit: `23a03fa3120cca54742ae6b5d0a6fb75f29fa7e6`.
The subsequent closeout commit records this reference only; source/tests are unchanged.

## Implementation

`backend/core/rebuild/safety.py` owns synchronous admission. `SafetyInputs`,
`AccountSnapshot`, `Quote`, `Instrument`, `Exposure` and `SafetyConfiguration` in
`safety_contracts.py` are credential-free injected contracts. No MT5 import,
credential loader, network client, legacy agent or order dispatcher is introduced.

The existing factory can explicitly compose this engine and a trusted input
provider. HTTP cannot supply an APPROVED decision, alter risk limits or reset HALT.
Startup still halts. Missing provider/evidence rejects; without P2 configuration
the prior disabled path remains. Factory account injection remains FIXTURE-only.
The internal operator-reset method requires a reason, identity, fresh reconciled
account evidence and passing loss gates; it increments the HALT version.

The path is canonical intent -> synchronous safety evaluation -> durable decision
and atomic reservation -> ELIGIBLE_NOT_SUBMITTED request. The request is NOT an
order and has no dispatcher. HALT, current policy, veto, reservation state/expiry
and evidence freshness are checked again when requesting eligibility. Replaying
an old decision returns historical evidence, not renewed eligibility.

Migration 005 adds P2 policy, baseline, evaluation, decimal reservation, immutable
observation and request tables. Migrations 001-004 are unchanged. Existing source,
signal, intent, account and risk_decision IDs are reused; trace exposes the linked
P2 reservations/requests. Existing FIXTURE-only execution_requests remain intact.
Historical/screenshot SQL guards remain effective. No operator migration ran.

## Numerical and Evidence Boundaries

- Decimal arithmetic uses a local precision of 40. Approved allocations and P2
  reservations are decimal strings, not binary floating-point risk calculations.
  Existing risk_decisions REAL amount columns are compatibility mirrors only;
  non-representable mirrors reject. Future P3 must consume the P2 allocation, not
  the original intent's requested_volume or a legacy risk-column mirror.
- Instrument evidence supports explicitly valued LINEAR_ACCOUNT_CURRENCY only.
  Tick, value/notional coefficients, margin per lot, commission, volume bounds and
  conversion time are mandatory. Unsupported valuation modes reject. These
  inputs are supplied evidence, not broker measurements performed by P2.
- Account used_margin must represent the complete broker-side used/reserved
  margin inventory; local unsubmitted reservation margin is added separately.
  Account exposures include manual/external, pending and ambiguous openings.
  A partial fill must match the exact local intent, symbol, direction and filled
  quantity before its position exposure replaces the proportional reservation.
- Existing BUY positions mark on the executable liquidation side (BID), SELL on
  ASK. A stop apparently crossed while exposure remains reported blocks admission
  for reconciliation, never releases capacity. New BUY admission uses ASK and new
  SELL uses BID, with adverse allowance and conservative tick normalization.
- MARKET source entry absence is retained, not fabricated. The opt-in
  deterministic_v3_p2 parser recognizes XAGUSD and absent MARKET entry; the default
  parser behavior/version remains unchanged. Explicit alias configuration is
  required when source symbols differ from the exact broker allowlist.
- Daily/weekly evidence uses UTC boundaries and persistent cash-flow-adjusted
  baselines. Equivalent timezone representations cannot bypass same-period
  baseline checks. Missing/contradictory evidence rejects. Baseline evidence is
  trusted injected input; actual broker cash-flow attestation remains P3 work.

## Recovery and Policy Versions

SQLite BEGIN IMMEDIATE serializes evaluation, baseline changes, decision and
reservation allocation; failure rolls the transaction back. Process-crash fixtures
cover death before commit and after commit. Exact retries reuse a decision and
reservation; a final veto cannot be overridden by another source or request.

Only RESERVED (proved unsubmitted) capacity can time-expire at 60 seconds.
SUBMISSION_BEGUN, AMBIGUOUS and PARTIAL never time-release. Partial fills require
matching position evidence plus a proportional remaining reservation. Ambiguity
retains the full reservation; terminal conversion/release requires explicit
terminal evidence. Observation simulation is FIXTURE-account-only and idempotent
by evidence ID. This is a P2 contract, NOT an attesting P3 broker bridge.

The fixed numerical policy remains P2-DEMO-1.0. Effective configuration versions
are P2-DEMO-1.0/config-N; every decision includes the base version, effective
version, policy/configuration hash, input hash/evidence and allocation. Explicit
operator configuration activation requires an increasing revision and reason.
It cannot change numerical policy or expand the instrument allowlist. It releases
only proved unsubmitted reservations for fresh re-evaluation, preserves ambiguous
capacity, and cannot rewrite old decisions/requests. A stale engine/configuration
cannot authorize a request. Numerical policy changes still require an accepted ADR.

## P2 Exit Criteria

All test names below are in backend/tests/test_p2_safety.py unless identified as
P1 coverage. Evidence is fixture-based, not runtime/broker qualification.

| Existing roadmap criterion | Result | Evidence |
|---|---|---|
| One authoritative pre-execution gate | PASS | SafetyEngine.evaluate, eligible_request, authenticated factory integration; test_app_integration_stays_halted |
| Direction-aware geometry and approved R | PASS | test_contract_rejects_bad_actions_numbers_geometry, test_exact_rr, test_sell_and_limit, test_limit_rejects, test_market_metadata_checks |
| Finite/action validation | PASS | strict canonical/evidence contracts; test_invalid_account and invalid action/NaN/Inf/geometry parametrizations |
| Persistent HALT at economic boundary | PASS | test_halt_replay_is_not_eligibility, test_loss_equality, test_persistent_halt_reset_requires_operator_evidence, test_drawdown_baseline_survives_restart |
| Reservations prevent concurrent over-allocation | PASS | test_concurrent_same_instrument, test_margin_race_across_instruments, test_process_crash_atomicity, test_atomic_rollback_on_reservation_failure |
| Compliance cannot race execution | PASS | synchronous checks before atomic approval; SQL request guard; test_rejected_decision_cannot_bypass_sql; no dispatcher/subscriber |
| Approved risk/freshness ADRs implemented and tested | PASS | tests summarized below; 79 focused P2 tests and full reviewed regression selection |

## Required Verification Map

1. HALT precedence: halt replay/eligibility and persistent reset tests.
2. Historical/screenshot firewall: test_historical_firewall plus retained P1 SQL tests.
3. Unknown actions: canonical bad-action parametrization; evaluate checks OPEN/BUY/SELL.
4. Non-finite inputs: account and canonical NaN/Inf cases.
5. Geometry: invalid BUY/SELL cases and quote-dependent MARKET/LIMIT checks.
6. Minimum R: test_exact_rr below/exactly 1.50.
7. Risk limit: test_risk_cap; exact 0.50% approvals in boundary tests.
8. Exposure/count/notional/margin/buckets: test_exposure_limits, portfolio_notional,
   projected_margin_equality, portfolio_risk_equality, correlation_equality.
9. Daily/weekly/HWM equality: test_loss_equality, restart, cash-flow and UTC rollover tests.
10. Stale/missing evidence: test_stale, test_market_metadata_checks, test_invalid_account.
11. Same-direction stacking: test_no_stacking_or_hedging BUY parameter.
12. Opposite direction: same test SELL parameter.
13. Concurrent capacity: same-instrument and cross-instrument margin races.
14. Idempotency: test_approval_lineage_restart_idempotency and observation retry.
15. Durable reservations: restart and process-crash tests.
16. Safe TTL release: test_ttl_and_ambiguous_retention, expired approval revalidation.
17. Ambiguous retention: TTL and versioned revalidation tests.
18. Superseded policy: test_policy_mismatch_invalidates_request and versioned revalidation.
19. Rejections cannot create requests: test_invalid_account and direct SQL guard test.
20. Exact lineage: test_approval_lineage_restart_idempotency and preserved P1 suite.

## Results and Limits

Final focused P2: 79 passed, 76 warnings, 9.41s.
P1 regression selection: 94 passed, 754 warnings, 12.90s.
Final broad fixture-safe selection: 297 passed, 1086 warnings, 29.60s.
All exit 0; six synthetic guard self-tests; zero protected-path access attempts;
no forbidden runtime modules. Commands and failed/intermediate runs: TESTING.md.

No secret/operator database access, MT5 connection, submitted order, live WhatsApp,
strategy, training, legacy reconnection or deletion occurred. The existing guard
is not an OS sandbox and does not propagate into child processes. New crash
workers were source-reviewed and use explicit temporary databases with inherited
scrubbed environments. Warnings are retained upstream asyncio deprecations.

Not proven: broker authenticity of injected evidence, actual broker fills,
commissions, valuation correctness against an account, P3 reconciliation,
operator deployment/migration, execution safety against a live/demo server,
profitability, research/ML qualification or production readiness. P3 requires
separate authorization; P2 completion never enables trading.
