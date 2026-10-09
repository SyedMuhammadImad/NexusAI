# P1-M3 Exit-Gate Verification

Date: 2026-09-10. Repository: `D:/project`; branch: `core-rebuild`.
Application/test baseline: `f32eb2b3cc426350b18f3f2a44890c9e75afd991`.
Disposition: **M3 COMPLETE; P1 VERIFIED_COMPLETE (non-executing fixture scope)**.
This is documentation-only verification, not a new feature milestone.

## Authority and Initial Assessment

Read AGENTS, the V2 specification, PROJECT, ARCHITECTURE, CURRENT-STATE, ROADMAP,
TESTING, RISKS, DECISIONS, all nine ADRs and P1-LIFECYCLE-MAP before changes.
Accepted ADRs 001/002/003/004/007/008/009 and deferred 005/006 remain unchanged.
The owner accepted M2 as COMPLETE_WITH_RECORDED_INCIDENT before authorizing M3.
That decision was recorded first in the roadmap, current state, lifecycle map,
risk register and incident report. The original incident is not erased.

Specification section 7 defines P1 as active-app source -> signal -> intent
identity, provenance, account binding, durable transitions and fixture
restart/replay tests without symbol-only attribution. ROADMAP expresses five
exit criteria below. M1/M2 already implement them; inspection found no minimum
missing application work. Therefore no new code, tests, dependency or migration
was introduced merely to create another milestone. Verification followed the
existing TESTING allowlist. No new architectural decision was required.

## Exact Exit Criteria

Paths below are relative to the repository. Line references are for the unchanged
application/test baseline above; test names are reproducible pytest identifiers.

| Existing P1 criterion | Implementation evidence | Fresh test evidence | Result |
|---|---|---|---|
| Canonical source/signal/intent lifecycle wired into active app without broker execution | `backend/main.py` calls create_app; `backend/core/rebuild/application.py:17` composes Ledger/LifecycleService and authenticated routers; `lifecycle_routes.py` exposes persistence, rejection and trace only | `test_p1_lifecycle.py::test_active_app_auth_halt_and_default_rejection`, `::test_fixture_request_through_same_active_composition`; `test_p1_historical_bridge.py::test_authenticated_historical_route_isolated_from_operator_storage` | PASS |
| Exact IDs survive restart/replay | `lifecycle_service.py:20,39,130` preserves first source evidence and stable IDs; `ledger.py:147` binds intent ID to account/client key; historical bridge checkpoints retain exact links | `test_p1_lifecycle.py::test_complete_fixture_chain_and_reopen`, `::test_concurrent_request_replay_and_conflicting_ids`, `::test_process_crash_and_service_retry`; `test_p1_historical_bridge.py::test_partial_failure_retry_and_restart` | PASS |
| Provenance/account identity preserved | `lifecycle_contracts.py` immutable contracts; `ledger.py:94` account check; `lifecycle_service.py:160` exact-ID trace; `historical_canonical_bridge.py:44` preserves source/time/parser identity | `test_p1_lifecycle.py::test_complete_fixture_chain_and_reopen`, `::test_forged_signal_source_lineage_and_unknown_trace`, `::test_unbound_default_and_no_implicit_fixture_account`; `test_phase2_integrity.py::test_account_isolation_and_no_unbound_economic_writes`; `test_p1_historical_bridge.py::test_raw_evidence_and_explicit_time_and_parser_provenance` | PASS |
| Duplicate same-symbol signals remain distinct | Signals keyed by source identity, intents by account/client identity, never symbol alone; historical identity includes exact message occurrence | `test_p1_lifecycle.py::test_independent_same_symbol_and_invalid_lineage`; `test_p1_historical_bridge.py::test_different_transcripts_and_distinct_same_symbol_messages`, `::test_identical_occurrences_are_not_dropped`, `::test_exact_zip_and_repack_preserve_archives_and_share_canonical_lineage` | PASS |
| Negative/replay/crash tests pass | `ledger.py:113` transactional commit/rollback; request/decision guards in service and migrations 003/004; bridge PENDING/SOURCE_ONLY/VALIDATED checkpoints | `test_p1_lifecycle.py::test_failed_audit_rolls_back_operation`, `::test_process_crash_and_service_retry`, `::test_sql_request_guard_rejects_unapproved_lineage`; `test_p1_historical_bridge.py::test_source_transaction_rollback_does_not_claim_link`, `::test_partial_failure_retry_and_restart`; all nine regression modules | PASS |

## Additional Requested Priorities

- Complete P1 lineage: SourceEvent -> signal.v2 -> intent.v2 -> persisted decision
  -> exact approved fixture request. Trace joins exact source/signal/intent IDs to
  decisions/requests and existing broker collections; absent broker evidence is
  empty, never inferred. This is not completion of the later broker/outcome chain.
- Non-executing boundary: default decisions REJECTED/P1_EXECUTION_DISABLED;
  requests only FIXTURE/RECORDED_NOT_SUBMITTED after exact approval. HTTP cannot
  supply APPROVED decisions, and SQL cannot promote requests to SUBMITTED.
  Proven by M1 rejection/veto, invalid-policy, SQL immutability and API tests.
- Historical firewall: canonical HISTORICAL_WHATSAPP and SCREENSHOT cannot create
  intents, approvals or requests, including fixture mode and pre-004 canonical
  intents. Migration 004 also rejects broker-order/position inserts. Proven by
  `test_direct_execution_firewall_including_fixture_and_legacy_wrapper` and
  `test_pre004_preservation_and_preexisting_historical_intent_firewall`.
- Replay/provenance: exact archive replay and transcript-equivalent repack share
  canonical identity while retaining separate containers and duplicate links.
  Distinct same-symbol events and repeated occurrences remain distinct.
- Failure recovery: transactional audit failures roll back; child-process death
  inside/after request commit recovers without duplication; historical partial
  failures recover by explicit same-ID retry. No distributed transaction claimed.
- Isolation: existing whole-service injection, default-constructor sentinels,
  concurrency/failure fixtures and normalized-path guard were rerun. No operator
  DB or credential was inspected, hashed, opened, repaired or modified for M3.

## Fresh Verification

1. Broad nine-module command from TESTING's normalized incident-review guard:
   **218 passed, 1010 warnings in 27.08s**, exit 0.
2. Same guard, focused M1/M2/incident selection:
   **94 passed, 754 warnings in 15.25s**, exit 0.

Both runs: `GUARD_SYNTHETIC_EVENT_SELFTESTS 6`,
`SENSITIVE_OR_OPERATOR_ACCESS_ATTEMPTS 0`, `FORBIDDEN_RUNTIME_MODULES []`.
Exact invocations are in `../TESTING.md`, P1-M3 Exit-Gate Verification.
The focused 94 are included in the broad 218; do not add them as unique coverage.
No failure occurred in these two runs. Warnings are the recorded FastAPI/Starlette
asyncio inspection deprecations, not hidden or repaired through dependency churn.
Earlier failed-run and incident evidence remains in TESTING and the incident report.

No blanket legacy-suite discovery, operator entrypoint import or server/browser
startup occurred. Parent audit hooks are not inherited by child processes: the
two crash-fixture paths were source-reviewed for explicit temporary SQLite paths,
synthetic account identities and the scrubbed environment. This is bounded
verification, not an OS sandbox or proof against arbitrary future native code.

## Limits and Remaining Work

- Operator runtime, actual schema deployment and broker/provider state: NOT
  VERIFIED by this task. The credential-reading main entrypoint was read as
  source only; the same active application factory was exercised with fixtures.
- P2 risk sizing, R:R admission, exposure/drawdown policy, freshness and atomic risk
  reservations: NOT IMPLEMENTED/QUALIFIED by P1. Initial accepted ADR policy is
  not proof that its engine exists; required numeric policy inputs remain explicit.
- P3 execution, broker attestation, request ambiguity/reconciliation and confirmed
  outcomes: NOT PROVEN. Retained observation-library fixtures are not broker truth.
- Live source adapters, strategies, market-data qualification, ML and performance:
  NOT PROVEN; no work on them was performed.
- Legacy learning approval spans separate databases, old imports lack provenance,
  and explicit source corrections/revisions are deferred. Existing bridge marks
  conflicting/insufficient records REVIEW_REQUIRED rather than fabricating them.
  Historical learning labels remain unverified. No legacy backfill is required by
  the five existing P1 exit criteria, and no new semantics are invented here.
- Historical access-time uncertainty remains in the M2 forensic record, accepted
  by the owner rather than retroactively disproven. No repair is warranted.

## Git and Disposition

Initial tracked tree/index were clean; only unrelated README_SETUP.md was untracked.
P0 baseline ae800c743bb7216b666dfca11c4751fb79022282 is an ancestor (exit 0).
Comparison against f32eb2b of backend, AGENTS, specification and ADRs returned
exit 0: implementation/tests/migrations and policies unchanged. No deletion.
Only documentation is committed in this closeout; no operator DB or secret file
is eligible for staging. No custom Git hooks configured/present. Commit signing
is disabled to avoid private signing-key access. No amend, history rewrite or push.
The separate documentation commit containing this report is identified in the
handoff; the tested application baseline is the full hash recorded above.

M2: COMPLETE_WITH_RECORDED_INCIDENT. M3: COMPLETE. P1: VERIFIED_COMPLETE.
P1 blockers: NONE. Trading: HALTED / NOT QUALIFIED.
Next recommended: P2 with explicit scope authorization and required policy inputs.
P2 is not started or implemented by this closeout.
