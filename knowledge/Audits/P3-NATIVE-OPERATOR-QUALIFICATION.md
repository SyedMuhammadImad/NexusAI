# P3 Native Operator Qualification Audit

Date: 2026-09-13. Branch: `core-rebuild`.
Pre-task baseline: `1b51674288442a050fdbb55bddde43aa9622ed73`.
Bounded implementation/evidence are committed together; identify the containing
commit with `git log -1 -- knowledge/Audits/P3-NATIVE-OPERATOR-QUALIFICATION.md`.
No push authorized or performed. Unrelated untracked `README_SETUP.md` was left alone.

## Verdict

**P3 PARTIAL. Native provider behavior fixture-verified; actual operator path
NOT_QUALIFIED, account NOT_ATTESTED, DEMO NOT_RUN. P4 remains BLOCKED.**

The prior missing implementations are supplied in native_operator.py and the
Windows collector. Their runtime qualification cannot be inferred from passing
fixtures. This task stopped at actual metadata pre-flight, before MT5 import or
connection. No credential values were read/copied, no operator DB accessed,
no verification DB created on the actual machine, and no order or close attempted.
No real-money exposure was introduced by this task.

## Actual Pre-Flight Evidence

Command: `.\backend\.venv\Scripts\python.exe -B scripts/p3_native_preflight.py`.
Emitted result: status FAIL, blocker MISSING_OPERATOR_EVIDENCE, broker_actions 0.
Only exact named-path metadata was inspected, without directory-content discovery.

| Operator file | Present |
|---|---|
| backend/private/mt5/p3-operator.json | false |
| backend/private/mt5/p3-risk-basis.json | false |
| backend/private/mt5/p3-costs.json | false |

| Mandatory gate | Report | Actual evidence missing |
|---|---|---|
| Exact account allowlist | FAIL | No approved native configuration loaded |
| DEMO attestation | FAIL | No connected native account read |
| Server/company/terminal | FAIL | No attested native identity or terminal |
| No-live acceptance | FAIL | Dedicated host/session isolation not qualified |
| Instrument eligibility | FAIL | No current native instrument data |
| Fresh P2 context | FAIL | Recorded risk/cost files absent; no native snapshot |
| Minimum volume | FAIL | No current broker volume metadata or approved request |
| HALT state | FAIL | No isolated operator session created/qualified |
| Policy version | FAIL | No configured native policy binding evaluated |
| Isolated verification DB | FAIL | Native run never created; fixtures only |
| Credential boundary | FAIL | Required configured boundary not qualified; no secrets read |

FAIL means prerequisites were not established, not a claim that broker state was
observed and invalid. No account identifiers or credentials are included here.

`git check-ignore -v` confirmed the three fixed files match `.gitignore:47`
(`backend/private/`), and verification state matches `.gitignore:31`
(`/.p3-verification/`). `git ls-files` for those exact paths/state returned no
tracked files. No existing secret contents were needed for these checks.

Scoped staged diff check passed without whitespace errors. The staged-path and
credential-pattern screen returned zero sensitive paths and zero pattern findings;
it inspected staged public changes only and emitted counts, not values. This bounded
screen is not a credential-revocation check or an exhaustive repository-history audit.

## Source and Fixture Evidence

| Requirement | Implementation | Verification scope |
|---|---|---|
| Host/account provider | WindowsTerminalIsolation, windows_host_snapshot, p3_windows_host.ps1 | Synthetic host negatives, binary/time changes, native-shaped account/company/path/DEMO tests; collector syntax PASS; actual OS NOT_PROVEN |
| Explicit native connection | NativeConnector | Exact synthetic path/login/server/portable parameters, lazy import, no retry and redacted failure |
| Native P2 evidence | NativeP2Context | Actual reader/journal/project_native with fake native data; strict risk history/costs/freshness/ownership/margin tests |
| Minimum-lot final check | _AttestedAdapter | Minimum/MARKET/finite/current-equity margin checks; equality at 25% accepted in fixture; larger/missing/invalid rejects |
| Mandatory pre-flight | connected_preflight, NativeOperatorVerification | No send on FAIL, HALT authoritative, no pre-flight approval bypass, single-use replay rejection |
| Isolation/state/recovery | Existing VerificationLedger, OperatorVerification, P3 engine | Broad regression, temporary DBs, revision/restart/crash/partial-fill/lineage tests |

Final counts and guarded reproduction are recorded in ../TESTING.md. First provider
run had 57 passes/one test failure: a test referenced a nonexistent fake-broker
counter. Corrected to the existing `calls` counter and reran. Four serialization
warnings from deliberately invalid fixture values were addressed without relaxing
validation. No failing assertion was deleted or marked skipped.

The final focused run passed **307 tests / 168 warnings**, and the broad run
passed **604 tests / 1318 warnings**. Both include the two final mandatory-pre-flight
tests; the earlier 305-test P3 run also passed. Every guarded run reported six
synthetic guard self-tests, zero protected/operator access attempts and no forbidden
runtime modules. The Python audit guard is not an OS sandbox; prior reviewed crash
workers use synthetic environment and temporary stores. Actual Windows process/ACL
behavior, service deployment, native latency and broker behavior are NOT proven.

## Exact Remaining Operator Requirements

1. Provision the designated dedicated non-admin, non-interactive Windows terminal
   environment and independently qualify exclusive/no-live operation, metadata
   visibility, protected storage and immediate stop handling. Do not reuse an
   uncontrolled desktop session or elevate/skip failed checks to pass.
2. Configure only the fixed ignored operator files, using actual account/terminal
   binding, recorded UTC daily/weekly/high-water/cash-flow evidence and qualified
   commission data. Do not paste credentials into chat or reconstruct missing
   history by assigning current equity to every baseline.
3. Run the operator read-only attestation path. Prove current native account,
   metadata, quote/inventory freshness, HALT denial and safe minimum-volume sizing.
   Deliberate P2 reset remains necessary; the tooling never unlocks automatically.
4. Only after all gates pass, prepare one canonical MANUAL/MARKET P2 request at
   broker minimum with valid SL/TP, cost-adjusted R and reservation. Use the gated
   one-shot wrapper. Preserve all state on rejection/ambiguity; never reset the
   claim or retry entry merely to get a cleaner test.
5. Prove actual order/deal/position lineage, idempotent reconciliation, reservation
   conversion and broker-confirmed terminal state under the current exit criteria.
   No local close or legacy helper is an acceptable substitute.

These are outstanding requirements, not actions that occurred. No new policy or
architectural decision was invented; accepted ADRs and P2 limits remain unchanged.
