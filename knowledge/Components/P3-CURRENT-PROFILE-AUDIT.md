# P3 Current-Profile Read-only Audit

## Authorized Manual Sign-in Diagnostic (2026-10-07)

Owner explicitly approved this after the two Cancel-only SDK failures. Use
`backend/.venv/Scripts/python.exe -B scripts/p3_current_profile_audit.py --audit --wait-for-manual-demo-login`.
The new flag is mutually exclusive with --wait-for-startup-cancel; either requires
--audit. Invalid CLI combinations stop before operator configuration is loaded.

The owned receipt-bound portable child opens, then the worker pauses before native
import/connection. The human signs in ONLY to the configured project DEMO account/
server. Do not automate authentication, request secrets in chat or select another
account/terminal. Only after human confirmation supply DEMO_LOGIN_COMPLETED to
worker stdin, never credentials. EOF/CANCELLED/other input rejects. There is no
human login deadline or automatic economic retry.

Fresh host checks follow the pause; their stage is POST_MANUAL_LOGIN_HOST_CHECK.
The SDK still receives explicit nominated credentials and60s timeout. Human
confirmation cannot satisfy native account/DEMO proof: mismatches/non-DEMO reject
before ledger/risk initialization. Five-second host freshness and all P2/HALT/
cost/lineage requirements remain unchanged. CLI default stays PLAN_ONLY.

Initial metadata:actual venv Python3.14.3/64-bit, main SDK5.0.6147, public/private
terminal5.0.0.6140/AMD64 with valid signatures, no pre-existing terminal process.
This rules out simple bitness mismatch, not other compatibility issues. Fixed
Oct5/Oct6 terminal journals contain no matched IPC/Python/authentication/network/
algo-block markers; absence of those markers does not establish a root cause.
After launch, one intended portable child in session1 was observed. Accessibility
returned no text for the first snapshot; do not claim Login visibility from it.

167 focused current-profile/native/bootstrap/V1 tests pass (45.86s), zero protected
access attempts and forbidden runtime modules. Broad1226 passed,2333 warnings,
423.02s, same zero-access guard. Owner confirmed manual sign-in, but explicit SDK
initialization still returned IPC timeout after fresh host checks; zero broker
actions/account attestation. Owned child stopped. Terminal-only follow-up owner
sign-in showed traffic0 / 0 Kb/zero observed established TCP; aborted before SDK.
Isolated Python3.12/same SDK6147 also returned IPC timeout. Python3.11 could not
pass existing path API checks and never reached SDK. All owned sessions finished;
main environment unchanged. Need actual terminal connection/Journal evidence
rather than unchanged initialization retries. See the diagnostic audit.
Broker HARD_DISABLED/LIVE LOCKED.

Authority: owner-approved ADR-022. Baseline:
`d00bb1ac54951859bb38dcae970235da6664b4e6`. P3/V1 remain PARTIAL.
This is a read-only operator path, not an execution provider or broker unlock.

## Fixed Boundary

`scripts/p3_current_profile_audit.py` defaults to PLAN_ONLY, without credentials or
native imports. Explicit `--audit` reads only the nominated
`backend/private/mt5/p3-operator.json` through the approved loader. Password stays
in SecretStr/in memory, never in output, source, receipt or public documentation.
No .env, other credential stores or normal/operator historical DBs are opened.
Do not create a Windows account or run old provisioning/repair scripts.

`current_profile.py` validates exact configured decimal login/server/DEMO policy
and instrument allowlist before launch. Metadata placeholders may be derived only
after native exact-account DEMO proof; never default currency to USD or fees to0.
There is no account-switch API, ambient SDK initialization or fallback login.
The approved cooperative same-user limitation remains explicit.

Fresh host evidence uses its own schema, not spoofed legacy session-zero flags:
current SID, desktop session, non-admin token, actual worker PID/base Python image,
exclusive owned terminal PID/path, non-reparse paths and restricted ACLs.
Windows PS5 receives only its system module directory, avoiding inherited PS7
security-module autoload failure. Errors contain fixed diagnostic codes only.

The one-worker Windows kernel lock is under ignored `.p3-verification/`. The fixed
new portable path is `backend/private/mt5/current-profile-terminal-v1/terminal64.exe`.
Before first copy, check MetaQuotes Authenticode signature on the fixed public
installation. Copied executable must hash-identically match it. An immutable
startup receipt binds path/hash/current SID/configured identity digest before
first launch. Existing terminal state without this receipt is not adopted. The
previous failed-start `current-profile-terminal/` is preserved, not reused/deleted.
Receipt is ignored runtime metadata, not native account attestation.

Launch only the fixed child in portable mode; verify host before native import,
then exactly one explicit SDK initialize(login,password,server) with60s startup
timeout. No automatic reconnect. Native last_error descriptions are never emitted;
only recognized numeric codes map to fixed diagnostics. In particular -10005 is
IPC timeout, not password rejection. Official sources:
[initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py),
[last_error](https://www.mql5.com/en/docs/python_metatrader5/mt5lasterror_py).

After successful initialization, prove exact account/server/DEMO, portable data
path, actual currency/company/build/leverage and algo permissions. Then and only
then create/resume a specialized account-bound VerificationLedger, HALT it, collect
native history/inventory/instrument/quote observations and derive ADR-019 unused-
account qualification-start baselines. No original credential config rewrite or
commission fabrication. This tool never creates a P2 approval, reservation,
economic attempt, default-app enablement or HALT reset. It cannot complete P3.
Finally disconnect SDK and stop only its owned, read-only child, including when
SDK shutdown raises. Failed startup retains its receipt for bounded retry.

## User-cancelled Diagnostic Retry

2026-10-06: user confirmed cancellation during a paused retry. Accessibility
inspection found Login/Password/Cancel controls absent while the main workspace
was visible, yet the SDK still returned IPC timeout. The dialog is NOT the sole
cause. User must handle authentication dialogs; the agent does not click/type.
The following handshake removes the human cancellation timing race, not IPC itself.

1. User confirms readiness to press Cancel on the initial Login dialog. Do not
   enter credentials, switch accounts or open another terminal.
2. Run from repository root, non-elevated current profile:
   `backend/.venv/Scripts/python.exe -B scripts/p3_current_profile_audit.py --audit --wait-for-startup-cancel`
3. The process prints AWAITING_STARTUP_CANCEL and pauses before native import/
   initialize. User presses Cancel when the dialog appears, then confirms.
   Operator supplies CANCELLED on process stdin only after that confirmation.
   EOF/other input rejects; this does not enter anything into the Login dialog.
Host freshness/ownership is rechecked after the pause. SDK still uses exact
   approved local credentials; no default/ambient login is selected.
4. Inspect sanitized result; stop on any mismatch or unqualified evidence. Do not
   place a trade or interpret READONLY_AUDIT_COMPLETE as operator qualification.
5. Only after actual account/history/metadata/cost evidence and a separately
   fixture-verified current-profile execution composition pass may the ordered
   manual P2/reservation/full-lineage smoke test proceed. Commission unknown
   remains a blocker. Later strategies/WhatsApp/P9 stay behind manual proof.

Stop procedure: this tool has no submission API. On mismatch stop the audit; do
not launch a second worker/terminal. Owned read-only child is stopped on exit. If
cleanup fails, leave execution disabled and inspect exact process metadata before
any retry; never kill an unrelated terminal or claim economic state was closed.

The completed comparison also used an isolated, hash-verified official6231 SDK
wheel without changing main6147/public6140. After confirmed Cancel and modal-free
inspection, it returned CURRENT_PROFILE_IPC_TIMEOUT at CONNECT. No account was
attested. Do not repeatedly rerun this diagnostic or claim a specific root cause.
An earlier pre-SDK failure did not capture its exception. Freshness failures now
map to CURRENT_PROFILE_HOST_EVIDENCE_STALE; the post-pause stage is explicit
POST_CANCEL_HOST_CHECK. The five-second gate is not relaxed. Manual isolated
DEMO sign-in authorization was requested; no such procedure performed yet.

## Evidence Limits

2026-10-06:187 focused/1215 broad fixture tests passed, zero protected attempts.
These prove
the fixture-safe software contracts, not native broker/account qualification.
Actual demo attestation, economics, risk/cost adequacy, HALT/restart with real
broker evidence, active strategy/WhatsApp routing and full P9 remain unproven.

2026-10-07 final guarded regression:1217 passed,2333 deprecation warnings,462.45s;
zero protected/operator attempts and forbidden modules.37 focused current-profile
tests passed (17.91s). No phase or execution-state upgrade. Manual sign-in remains
unauthorized/not performed pending the explicit human response.
