# P3 Execution and Reconciliation

Current governance (2026-09-13), ADR-012: **P3 ENGINEERING VERIFIED_COMPLETE**
within non-operational/fixture/native-normalization scope; **P3 OPERATOR DEMO
VERIFICATION DEFERRED / PENDING**. Actual broker verification is NOT complete.
All fixture/native evidence below is retained. Broker execution remains HARD
DISABLED; P4 READY and sequential P5-P9 work are NON-EXECUTING only. Operator
verification remains mandatory before ordinary demo execution, P10 or any
live-readiness work. No code/operator action or P4 implementation in this amendment.
Earlier combined PARTIAL/P4-blocked labels below are historical checkpoints.

Current follow-up (2026-09-12): ADR-011 resolves the prior native revision blocker.
Migration 007 and the append-only native journal/normalizer are implemented; see
P3-NATIVE-EVIDENCE.md and the latest ../TESTING.md evidence. P3 remains PARTIAL
pending isolated operator DEMO qualification. Earlier statements below describe
the original implementation and compatibility-stop checkpoints, not current
native code absence. Existing P2 policy and no-resubmission rules are unchanged.

Date: 2026-09-11. Branch: core-rebuild.
Starting baseline: 3e3e1d044d9acbae8b3c86f1794bd85db085d211.
Verified implementation commit: 87229215534c00ae5f16997af7bff16df1e512fb.
Authorization: P3 only, fixture-first verification, no push.
Status: **PARTIAL / FIXTURE_ONLY**. P0/P1/P2 remain VERIFIED_COMPLETE.
Trading: default application HALTED / NOT QUALIFIED; no native broker connected.

## Authority and Boundaries

Accepted ADRs and P2-DEMO-1.0 numerical policy/hash manifest are unchanged.
No strategy, ML, P4 ingestion, legacy-agent composition, credentials, operator DB,
terminal initialization, login or native order submission were used in this work.
This implementation is not an operational MT5 service: the injected native
snapshot reader and isolated operator session still require implementation and
qualification. Fake method-shape tests do not establish native broker behavior.

## Components

Paths below are under backend/core/rebuild/ unless stated otherwise.

| Component | Responsibility |
|---|---|
| execution_contracts.py | Demo attestation, complete snapshot, decimal orders/deals/positions/protective exits, adapter protocol |
| execution.py | Durable attempts, final P2 gate, one-send ownership, conservative recovery, atomic reconciliation/quarantine |
| mt5_demo.py | Injected MT5 method boundary; no import/initialize/login/secret loading; account checks, mapping and result classification |
| safety.py | Additive revalidate_reserved operation reuses P2 calculator at exact reserved volume |
| migrations/006_p3_execution.sql | Additive attempt/evidence/decimal projections; 001-005 unchanged |
| application.py / lifecycle_routes.py | Explicit FIXTURE-only factory and authenticated submit/reconcile paths; default writes frozen |
| lifecycle_service.py | Source trace includes attempts, events, opening orders/deals/positions and protective exit orders/deals |

The old broker ledger compares fills with original proposed volume and stores
REAL values. P2 may approve a different sized volume. P3 therefore adds exact
decimal projections linked to the P2 request; it does not weaken old guards,
rewrite intent volume or promote old fixture records to attested evidence.

Preserved lineage: source_event_id -> signal_id -> intent_id -> P2 decision_id ->
execution_request_id -> attempt_id -> broker_order_id -> broker_deal_id(s) ->
broker_position_id. Protective exits retain their own order/deal IDs linked to
the exact originating position. P5 outcome labels/accounting are not generated.

## Submission Contract

1. prepare records a deterministic immutable attempt unique per P2 request and
   intent. P1 fixture requests cannot enter P3. Correlation is a 28-character nx3-
   identifier plus independent positive 60-bit magic; collisions reject via SQL.
   These are correlation metadata, NOT broker-guaranteed idempotency keys.
2. Attest exact account ID/server/currency/scope/session, DEMO type, connection,
   trading permissions and hedging mode. Missing/contradictory evidence rejects.
   Netting allocation is unsupported; there is no symbol-only attribution.
3. Reconcile complete history/inventory, then re-run P2 using fresh evidence at
   the exact reserved volume, excluding only this request's own reservation.
   HALT/version/source/geometry/R/risk/freshness/exposure gates remain authoritative.
   Revaluation cannot exceed reserved risk/notional/margin or change protection.
4. Commit SUBMISSION_STARTED plus SUBMISSION_BEGUN reservation before sending.
   A crash before this commit can retry after fresh gates. After it, recovery is
   observation-only, even if the actual transport call never happened.
5. Only the invocation that committed STARTED may perform the final fresh snapshot,
   P2 gate, attestation and one synchronous send, inside a serialized SQLite write
   transaction. Evidence deadlines travel with the command and are checked again
   by the transport. There is no retry/requote loop.
6. Explicit attested rejection may release capacity. None, timeout, connection
   failure, unknown/mixed results and exceptions are ambiguous. An acknowledgement
   does not create broker deals/positions. Reconciliation must supply those facts.

SQLite serializes local HALT/config changes against the final check/send. A HALT
committed first prevents sending. A HALT requested after a send starts cannot undo
it and may wait on the transaction. This is not an atomic DB-plus-broker transaction
or exactly-once broker guarantee. Concurrent recovery can conservatively halt a
not-yet-sent attempt; liveness is secondary to avoiding duplicate economic actions.

Durable states: NOT_SUBMITTED, SUBMISSION_STARTED, SUBMISSION_CONFIRMED,
SUBMISSION_AMBIGUOUS, REJECTED_BY_BROKER, PARTIALLY_FILLED, FILLED, CANCELLED.
P2 requests remain immutable original eligibility records; P3 attempts describe
current submission state. No automatic HALT reset, retry worker or timer exists.

## Reconciliation and Risk

- Snapshots must cover all attempt history and current positions under the bound
  account. Missing history is not proof of no order. Broker positions must agree
  with the safety snapshot; unresolved external/pending exposure fails closed.
- Exact correlation/magic, symbol, direction, entry type, sized volume, SL/TP and
  acknowledgement IDs are checked. Terminal regression, identity conflict, missing
  prior observations and immutable deal changes fail safe.
- Order/deal/position quantities reconcile using decimal arithmetic. Repeated
  observations do not duplicate records. A failed projection rolls back before
  quarantine and latched HALT are committed. Ambiguity restores full reserved
  capacity, including when new evidence contradicts an earlier broker rejection.
- Partial fills convert observed volume to broker exposure; the unresolved
  remainder stays reserved. Cancellation releases only the unfilled remainder.
  No TTL release is allowed after submission begins or becomes ambiguous.
- Same-symbol positions remain independently attributable where broker evidence
  permits. The test explicitly constructs prior independent approvals and also
  proves that normal P2 admission rejects stacking; it is not an adoption API.
- Passive SL/TP exits require an exact owned position, terminal opening order,
  explicit protective exit order, matching OUT deals and reconciled remaining
  quantity. Full closure additionally requires complete-inventory absence evidence.
  A missing position or local price crossing cannot manufacture a broker close.
- Partial protective exits reduce current open exposure without changing original
  fills. Proven full closure releases capacity. No WIN/LOSS or net-PnL label is made.
- Unknown external orders/positions, manual exits, close-by/netting, incomplete
  protective exits and exits while an opening remainder is unresolved quarantine
  and retain capacity. No automatic adoption/cancel/flatten behavior is supplied.
- Reconciliation while HALTED can record broker truth, but cannot submit or resume.
  Contradictions mark position projections RECOVERY_REQUIRED, not falsely CLOSED.

## Fixture Evidence

Final focused P3: **104 passed, 168 warnings, 23.19s**.
P2 regression: **79 passed, 84 warnings, 11.17s**.
P1 regression: **94 passed, 794 warnings, 17.38s**.
Final broad twelve-module suite: **401 passed, 1318 warnings, 55.24s**.
All exits 0; six synthetic guard checks, zero protected-path attempts and no
forbidden runtime modules on every run. Commands/history/limits: ../TESTING.md.

Required-case mapping into backend/tests/test_p3_execution.py:

| Requirement | Test(s), abbreviated names |
|---|---|
| Successful exact lineage / replay | success_exact_lineage_and_restart_replay |
| Rejection / contradictory rejection | broker_rejection_releases_only_attested_result; rejection_contradicted_by_order_restores_full_ambiguous_capacity |
| Concurrency | concurrent_replay_no_double_send |
| Pre-start / post-start / post-fill crash | crash_before_started_safe_resume; crash_after_durable_start_never_resubmits; process_death_recovery (3 actual subprocess deaths) |
| Ambiguous response / timeout | ambiguous_response_resolves_only_with_broker_evidence |
| Repeated evidence | repeated_snapshot_is_idempotent |
| Partial fills / multiple deals | partial_multi_deal_and_cancel_remainder; partial_then_additional_deal_full_fill |
| Same-symbol identity | same_symbol_independent_broker_positions_without_admission_stacking |
| Stale approval / HALT / policy / missing evidence | submission_revalidates_p2; submission_deadline_and_drawdown_are_durable |
| HALT at submission/recovery | halt_between_start_and_final_gate; halt_recovery_observes_but_never_sends |
| Account/environment | account_attestation_fail_closed |
| Unknown broker state / rollback | reconciliation_mismatch_quarantines_without_local_close; final_snapshot_detects_external_order; atomic_projection_rollback |
| Reservation release / protection | pending_cancellation_releases_capacity; protective_exit_requires_broker_deals_and_absence; partial_protective_close_reduces_current_position_not_history; unproven_close_never_releases |
| Active app / auth / disabled default | explicit_app_fixture_composition_and_auth; default_app_cannot_dispatch; native_adapter_not_authorized_by_app_configuration |

test_p3_mt5_boundary.py covers BUY/SELL MARKET and LIMIT mapping, account switches,
demo/environment rejection, unsupported metadata, stale/invalid quotes, expiry,
retcodes, None, and no retry. Its client is a fake Python object, not MetaTrader5.
Migration assertions advance expected version/count 5 -> 6; preservation assertions
and original migration checksums remain. Prior incidents/test history are preserved.

## Native Boundary and Remaining Work

2026-09-12 compatibility gate: **native implementation stopped, P3 PARTIAL**.
Documented MT5 same-ticket deal cancellation/PnL revision conflicts with the
current single immutable canonical payload. Five added characterization cases
prove safe conflict handling, not native normalization. The required human
disposition and precise contract/source evidence are recorded in
../Audits/P3-NATIVE-EVIDENCE-COMPATIBILITY.md. Resolve that disposition before
implementing or changing native support. No application/ADR/migration changes or
operator/broker actions were made by this follow-up. Updated regression counts
are in ../TESTING.md; the earlier implementation evidence above is preserved.

MT5DemoAdapter requires an already qualified, exclusively owned demo session and
an explicit snapshot_reader(client, since, attestation). **No native snapshot
reader is supplied.** It must establish complete broker history/inventories, stable
position IDs, broker cash flows/baselines, supported valuation/conversion/margin,
commission evidence and coherent times. Missing values cannot become defaults.
Absence evidence must derive from complete broker inventories and closing deals,
never local SL/TP inference. Existing learning/operator DBs are not broker evidence.

The transport floors point-based deviation, validates lot/tick representations and
supports explicit filling policies. It refuses quotes changed after the final P2
gate rather than spend slippage allowance twice. Out-of-allowance broker fills
cause reconciliation HALT. Stop risk is modeled, not guaranteed maximum loss.
Real broker comment preservation, calculation modes, latency, partial fills and
terminal account isolation remain unverified. Configuration alone is no proof that
the terminal cannot switch to a real account. Default app rejects native adapters.

Official documentation inspected without executing examples:
[order_send](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py),
[account properties](https://www.mql5.com/en/docs/constants/environment_state/accountinformation),
[orders](https://www.mql5.com/en/docs/constants/tradingconstants/orderproperties),
[deals](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties),
[positions](https://www.mql5.com/en/docs/constants/tradingconstants/positionproperties),
[return codes](https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes).

## P3 Exit Assessment

| Existing exit criterion | Evidence verdict |
|---|---|
| MT5 demo-only account attestation | Fixture PASS; actual connected-account/environment proof UNVERIFIED |
| Durable client request identity | PASS, fixture ledger/process-crash scope |
| Retry/crash/ambiguous reconciliation tests | PASS, deterministic fixture scope |
| Partial fill/order/deal/position reconciliation | PASS, supported fixture contracts; native reader UNVERIFIED |
| No duplicate action in controlled faults | PASS, fake broker/process faults; not native exactly-once proof |

**P3 PARTIAL, not VERIFIED_COMPLETE. P4 remains BLOCKED.**
Minimum next P3 task: implement/qualify native evidence normalization from safe
recorded broker-shape fixtures; obtain scoped operator authorization and prove an
isolated demo terminal with no real-money account reachable; then perform controlled
demo end-to-end/restart/reconciliation checks and record broker evidence. Operational
composition and operator rollout remain gated by the same evidence. Do not begin
by opening credentials/operator stores: general coding authorization is insufficient.
