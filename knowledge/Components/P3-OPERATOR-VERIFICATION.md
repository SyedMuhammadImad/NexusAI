# P3 Operator Verification Boundary

2026-10-05 current authority: ADR-022 cooperative current-profile boundary replaces
the removed dedicated-user/session-zero host model. See
P3-CURRENT-PROFILE-AUDIT.md and ../Audits/P3-CURRENT-PROFILE-READONLY.md. Native host
prechecks pass; initialization timed out before account attestation. No demo trade,
qualification or execution unlock. The older procedure below is historical, not
an instruction to recreate a Windows account or deploy the removed attestor.

2026-09-13 follow-up: concrete native providers and a mandatory pre-flight
composition are now implemented and fixture-tested. Actual operator qualification
is still NOT_PROVEN; three required files are absent, no native test was run.
See P3-NATIVE-OPERATOR-PROVIDERS.md and ../Audits/P3-NATIVE-OPERATOR-QUALIFICATION.md.
The 2026-09-12 implementation/procedure below is preserved as historical evidence;
its missing-provider implementation statements no longer describe the newest code.

Date: 2026-09-12. Authority: current human operator-tooling authorization,
ADR-008, ADR-010 / P2-DEMO-1.0 and ADR-011. Baseline: `cf6a412`.
Status: **IMPLEMENTED / FIXTURE_VERIFIED; OPERATOR PATH NOT_QUALIFIED**.
Actual demo NOT_RUN; P3 PARTIAL; P4 BLOCKED.

## Bounded Implementation

`core/rebuild/operator_verification.py` adds an operator-only composition around
existing P1/P2/P3 contracts. This is not a native login helper, VM provisioner,
strategy, source adapter or replacement risk engine. No default-app wiring or
normal runtime activation changes. No migration or policy-number change.

1. `VerificationLedger.create` exclusively creates a new UUID directory and
   `ledger.sqlite3` under `.p3-verification/`. Native scope requires the actual
   repository workspace; fixture scope permits temporary workspaces. No arbitrary
   database filename can be selected. New state explicitly starts HALTED.
2. The local run marker and existing append-only audit record bind run/account
   identity and file identity. Resume checks the fixed layout and binding.
   Reparse/symlink/junction paths, replaced/hardlinked databases and linked SQLite
   sidecars reject. Checks precede each SQLite connection. These are defense in
   depth, NOT an OS sandbox; exclusive ownership is still required against races.
3. `OperatorVerification` requires that specialized ledger and an exact match to
   `SafetyConfiguration.approved_account_key`. It accepts a reviewed isolation
   verifier and a deferred operator connector; it does not import MT5, load .env,
   select an ambient terminal or obtain credentials itself.
4. Missing isolation verifier blocks BEFORE invoking the connector. The verifier
   must independently validate the account/session, exclusive ownership/no-live
   route, credential scope, context provider, ledger ownership and stop procedure.
   Its returned opaque receipt is an evidence reference, not proof by itself.
   No JSON flag, secret value, server name or test receipt qualifies this boundary.
5. Connected attestation is then checked for exact account/server/currency/scope/
   session, positive DEMO mode, connectivity, permissions, hedging and freshness.
   Lease checks surround reads and precede send. Connection failure is sanitized,
   HALTs local state and cannot trigger an implicit reconnect.
6. `submit_once` requires a canonical P2 request. It commits an immutable use
   record before entering the existing executor. An exclusive, flushed
   `.p3-verification/smoke-used.json` claim also prevents a NEW ledger from
   resetting the workspace test budget. Never remove that claim to retry.
   A crash or pre-send rejection may consume the budget without any order.
7. The existing `ExecutionEngine` still owns durable STARTED, final P2/HALT,
   reservations, attestation, journal/projection and ambiguity handling. Additional
   smoke restrictions require MANUAL + MARKET, empty account exposure, and exact
   fresh `volume_min`. There is no sizing clamp or safety bypass. The native
   adapter rechecks the minimum against its final broker metadata when the
   operator-only `minimum_volume_only=True` command is present.
8. Completion, exception and replay attempts HALT the isolated ledger. Recovery
   is explicitly read-only reconciliation; it cannot submit, retry, cancel or
   flatten. An actual process death cannot run `finally`; the persisted claim
   still prevents repeat submission, and recovery must HALT before observation.

The one-test restrictions implement this task's narrower authorization, not a new
ADR-010 policy. The regular application remains fixture-only. Existing migrations
001-007 are unchanged; existing append-only audit storage is reused.

## What Is Not Supplied or Qualified

There is **no machine-specific IsolationVerifier or native connector registered**.
The fixture verifier returns synthetic receipts and is not an operator provider.
The actual dedicated terminal/VM/OS ownership, no-live route, credential/session
configuration and exact allowed current account have NOT been inspected or proven.
No native context provider with real baseline/cash-flow/cost/margin evidence has
been qualified. Python callbacks are a trusted operator boundary, not an adversarial
code sandbox; arbitrary callbacks must never be accepted from CLI/HTTP/config.

The diagnostic `scripts/p3_operator_preflight.py` reports this missing composition
and exits 2. It neither probes private locations nor claims to discover machine
state. No connect/submit/unlock flag exists. Its fixed denial is not an attestation
that no terminal is installed. Do not change it to QUALIFIED just to obtain exit 0.

MetaQuotes documents that omitted initialization arguments can select an ambient
terminal, the last account or saved credentials. The verification path therefore
must not use omitted/default terminal selection.
[Official initialize reference](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py).
The documented order request contains trade parameters but no atomic account
binding; we retain the existing isolation requirement rather than infer one.
[Official order_send reference](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py).
No published example was executed.

## Operator Qualification Procedure Still Required

1. Designate an exclusively controlled demo terminal/session, preferably in an
   isolated environment, with independently reviewed controls excluding live
   routing/account switching and unrelated processes or shared historical stores.
   A VM name or a portable-mode flag alone is not this evidence. Provide the exact
   allowed account binding, terminal identity, credential location and session
   ownership; do not paste credential values into the repository or logs.
2. Implement and review the machine-specific isolation verifier/connector against
   those actual controls. Rechecking a user-supplied boolean is insufficient.
   It must fail before any connection when proof is absent, preserve the lease
   during all native calls and stop on mismatch. Credential access, if then
   authorized, stays in the reviewed operator-only location under backend/private
   or approved active environment storage. No discovery of other credentials.
3. Qualify real account baselines/cash flows, high-water mark, costs/conversions,
   margin, supported native metadata and complete inventories through the existing
   NativeEvidenceReader context-provider contract. Missing data never becomes zero
   commission, empty exposure or a newly invented drawdown baseline.
4. Use the new separate ledger, approved account and policy configuration. Capture
   fresh evidence, demonstrate HALT denial and perform the existing explicit P2
   operator reset only after qualification. The tool never resets HALT for you.
   Prepare a deliberate MANUAL canonical test request with source provenance,
   valid SL/TP, cost-adjusted R and requested risk that P2 allocates at exactly the
   broker minimum. The legacy intent.volume field does not override P2 sizing.
5. Confirm the stop plan, then call submit_once for that one approved request.
   Preserve the run directory, workspace claim and entire observation history.
   Reconcile repeatedly without submission; prove exact IDs and reservation state.
   No partial fill, timeout or missing response permits a second entry.

This is a required future operator procedure, NOT a list of actions performed.
Do not connect before the current user's required pre-connection gate is proven.

## Stop and Evidence Rules

- Before connection: any unproven isolation/access gate means no connector call.
- Before submission: any account, metadata, risk, HALT or volume mismatch rejects.
- At/after STARTED: retain claim and evidence; existing P3 ambiguity handling
  retains reservation/exposure and HALTs. A confirmed fill may convert reservation
  into exposure after a timeout; it is not proof that no economic action occurred.
- Call `stop()` to HALT local admission. HALT does not undo an in-flight native
  call, disconnect a terminal or close a position. Do not use account shutdown as
  a manufactured close. Native timing and the external stop procedure remain
  unqualified until tested in the isolated operator environment.
- Only supported broker-confirmed protective exits may establish terminal state.
  No manual close helper is added by this work. Unachievable or unsupported close
  remains outstanding, not an excuse to call legacy execution functions.
- Guarded reconciliation remains possible while HALTED, but a revoked isolation
  lease blocks further broker reads as well. Preserve local evidence for review.
- Global quota is workspace-scoped and process-crash-tested, not a tamper-proof
  cross-machine account quota or hardware power-loss durability guarantee. Its
  ownership and preservation remain part of the real isolation qualification.

## Verification Scope

`test_p3_operator_verification.py` uses only temporary directories, synthetic
accounts, fake brokers, fake isolation receipts and a reviewed crash subprocess.
It proves wrapper behavior and integration into real P1/P2/P3 code under those
fixtures, including native-shaped append-only reconciliation. It does not prove
an OS isolation provider or actual MT5 operation. Exact final counts/commands and
preserved first-run failures are in ../TESTING.md.
