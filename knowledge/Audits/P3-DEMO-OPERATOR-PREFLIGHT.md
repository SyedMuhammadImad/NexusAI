# P3 Final Demo Operator Preflight

Date: 2026-09-12. Verdict: **PARTIAL / NOT_RUN**. P4 remains BLOCKED.

## Repository and Authorization

- Branch: `core-rebuild`.
- Inspected implementation/control baseline: `a0661082ca4906b8d369e255fea3590844d1bd7c`.
- Initial working tree: only untracked `README_SETUP.md`; left unread, untouched
  and unstaged. No application, test, migration, configuration or credential edits.
- The current human request explicitly authorizes CONDITIONAL isolated DEMO
  verification. Lack of general user authorization is NOT the blocker.
- AGENTS.md, ADR-008, ADR-010, ADR-011, SECURITY.md and current P3 controls retain
  account/isolation, qualified evidence, HALT/P2 and operator-access prerequisites.
  The request requires their proof before connection, not merely before submission.

## Evidence Inspected

Public repository source, documentation and Git metadata only:

- `backend/core/rebuild/mt5_demo.py:1-5,20-34`: adapter requires an injected client,
  account binding and session. Its documented native boundary has no atomic
  account-bound send guarantee; repeated attestation is not terminal isolation.
- `backend/core/rebuild/mt5_demo.py:62-122`: submission rechecks account, quote,
  geometry, volume, expiry and calls order_send once. These are source/fixture
  controls, not evidence of any currently connected account.
- `backend/core/rebuild/mt5_evidence.py:168-176,223-224`: reader requires an
  already-injected session and explicit qualified risk-context provider.
- `backend/core/rebuild/application.py:17-28`: normal app rejects native adapter
  dispatch and non-FIXTURE account bindings. Starting the dashboard is not an
  authorized shortcut to a native P3 verification path.
- `knowledge/Components/P3-NATIVE-EVIDENCE.md`: real baseline, cash-flow, cost and
  margin qualification remains an operator responsibility; fixtures do not supply
  real runtime evidence. Manual/netting/unsupported exits are not automatic closes.
- `knowledge/SECURITY.md`: approved storage locations do not constitute session
  isolation; credential-dependent entry points require scoped review.
- `git ls-files scripts` lists five helpers: audit_parser_history.py,
  setup_local_access.py, start_local.ps1, verify_phase0.py, verify_rebuild_ui.cjs.
  Scoped `rg -l 'MT5DemoAdapter|NativeEvidenceReader|isolated.*demo|P3.*DEMO'
  scripts -g '*.py' -g '*.ps1' -g '*.cjs'` returned no matches (exit 1).
  No qualified P3 operator harness was identified in that scope. This is NOT a
  claim that no terminal or other operator setup exists elsewhere on the machine.

No active environment file, private directory, credential/session profile or
operator database was opened or enumerated. Old chat credentials were not reused
as current account configuration or proof. No MT5 runtime was imported or called.

## Mandatory Prerequisite Matrix

| Gate | Result | Exact evidence still needed |
|---|---|---|
| 1. Current account explicitly DEMO | UNVERIFIED | Current attestation tied to an isolated allowed session; no broker read performed |
| 2. Exact configured allowed account | UNVERIFIED | Reviewed operator binding and matching attestation; old chat identifiers are not current binding evidence |
| 3. No route to LIVE | UNVERIFIED | Dedicated terminal/session selection and exclusive control with no live-account route or account-switch race; adapter checks alone are insufficient |
| 4. Approved credential boundary | UNVERIFIED for operation; no secrets accessed | Reviewed operator entry point and explicit credential/session access locations, without exposing values |
| 5. Active HALT/P2 | Fixture PASS; operator UNVERIFIED | Isolated engine/ledger wiring, current policy/hash/reservations and final HALT/P2 revalidation on that path |
| 6. Fresh valid metadata/account | UNVERIFIED | Attested account, quote, complete order/position/history inventory, instrument and valuation evidence |
| 7. Minimum safe broker volume | UNVERIFIED | Fresh volume_min/step, SL/TP constraints and P2-approved allocation at that minimum; no lot size invented |
| 8. P2-DEMO-1.0 risk context | UNVERIFIED | Qualified current baselines/cash flows, high-water mark, costs/conversions/margin and complete existing exposure/reservation attribution |
| 9. Safe stop on mismatch | Pre-connection stop PASS; operator plan UNVERIFIED | Qualified abort/latency and post-submission protection/reconciliation procedure; HALT cannot undo an already-started synchronous send |
| 10. No unrelated operator DB modification | PASS for this task's actions | No operator DB access occurred. A separate explicit scratch verification ledger must be designated before a future smoke test |

These are unmet evidence gates, not proof of a live account, invalid credentials,
or a faulty current operator database. No machine-wide state claim is made.

## Decision and Actions

Stop BEFORE broker connection. No initialize, login, account/history/quote read,
order submission, retry, cancel or close occurred. No live exposure was created by
this task; pre-existing external account state was not inspected. No strategy,
legacy reconnection, P4, secret modification or operator migration occurred.

Actual-demo lineage, broker IDs, repeated reconciliation, reservation conversion,
projection-to-broker agreement, external-entity quarantine and broker-confirmed
close are **NOT_RUN / NOT_PROVEN**. Fixture proofs remain valid in their tested
scope; they are not relabelled as actual broker evidence. No local close or
approval was manufactured to complete the gate.

## Verification

Fresh guarded tests and exact results are recorded in the dated preflight section
of `../TESTING.md`. Both the focused P3 and fifteen-module P3/P2/P1/backend
allowlists use the documented normalized P1-M2 guard, scrubbed environment,
disabled plugin autoload/cache/bytecode and temporary fixture databases.
The audit hook is not an OS sandbox and is not inherited by crash-test children;
the existing reviewed workers use explicit temporary paths and synthetic inputs.
No claim about unrelated processes or universal filesystem isolation follows.

## Minimum Remaining P3 Work

1. Prepare and review the isolated operator entry point, exact allowed demo binding,
   credential/session boundary, exclusively controlled terminal and separate scratch
   ledger. Prove no live-account routing before connection. Do not enable the
   fixture-only application or reuse legacy startup as a workaround.
2. Qualify the operator context provider and current account/instrument evidence,
   minimum-volume P2/HALT path and safe stop/protective reconciliation plan. Where
   the requested pre-connection proof needs an operator-supplied attestation,
   obtain that evidence rather than connect speculatively.
3. Only after all gates pass, perform the minimum isolated demo submission and
   reconcile exact native IDs/observations/reservations, including supported
   broker-confirmed exit evidence when required. Preserve ambiguity and never
   resubmit for a cleaner result.

This task records the stop and reruns verification; it does not implement a new
operator harness or change policy. P3 remains PARTIAL; no P3 demo exit checkbox
is checked and P4 is not authorized. The separate documentation commit containing
this report records the verification evidence; no push.
