# P3 Operator Tooling and Verification Record

Date: 2026-09-12. Baseline: `cf6a4128753a8d14ad1660964521e9fc10dd18d7`.
Branch: `core-rebuild`. Initial unrelated `README_SETUP.md` remains untracked,
unread and untouched. Work is local; no push. Verdict: **P3 PARTIAL**.

## Authorization and Work Performed

The owner explicitly authorized minimum operator-only tooling and a conditional
demo smoke test. This supersedes the preceding task's documentation-only scope,
not its unproven isolation findings. No new policy or architectural trust decision
was invented. The existing trusted injected-broker boundary remains conditional
on separately qualified operator/session evidence.

Added isolated verification-ledger creation/resume checks, deferred connector
gating, repeated exact account/session attestation, MANUAL/MARKET minimum-volume
restrictions, a workspace-wide exclusive single-use claim plus immutable audit
record, and a HALT/read-only-recovery procedure. Reused P1/P2/P3 without modifying
their policies or old migrations. The native adapter gets only an additional
minimum-volume check when the dedicated operator command requests it.

Added a credential-free diagnostic, fixture tests and operating documentation.
The diagnostic ran under the sensitive-path guard and returned:

```json
{"blocker":"MACHINE_ISOLATION_VERIFIER_AND_OPERATOR_CONTEXT_NOT_QUALIFIED","broker_actions":0,"demo_verification":"NOT_RUN","operator_path":"NOT_QUALIFIED","secrets":"NONE"}
```

Exit 2 is the expected operational rejection. The diagnostic is not a machine
probe: it states that no qualified machine-specific verifier/native connector is
supplied by this composition. It does not prove that no terminal/VM exists.

## Ten-Gate Assessment

| Required gate | Implemented/fixture evidence | Actual operator result |
|---|---|---|
| Exact allowed demo identity | Ledger/configuration and attested identity equality | NOT_ATTESTED; actual binding/session not qualified |
| Positive DEMO account | Existing native normalization and wrapper strict Attestation checks | No native connection/read; NOT_ATTESTED |
| No live route | Connector cannot run without trusted isolation verifier; default denies | Machine-specific verifier/underlying no-live controls NOT_QUALIFIED |
| Scoped credential access | No credential loader; deferred connector only after isolation check; no CLI unlock | NONE accessed; actual connector/locations still require scoped review |
| Separate verification state | New fixed-location UUID ledger; account/file identity and link checks; sentinel unchanged tests | No normal/operator store accessed; OS race/ownership isolation not certified |
| Current P2 risk evidence | Existing final P2 revalidation and reservations remain mandatory | Real baselines/cash flows/cost/margin provider not qualified |
| Fresh account/quote/instrument/position data | Existing freshness/native consistency gates, repeated attestation; negative tests | No actual native observations obtained |
| Minimum permitted size | Exact minimum required at both engine and native transport boundary; no resize | Actual minimum not observed; no volume selected |
| Authoritative HALT | Fresh run HALTED, no auto reset, final P2/HALT check, stop/recovery HALT | Fixture-proven only; no real operator process tested |
| Explicit stop procedure | Documented no retry/close on ambiguity; durable quota survives process death | Real timeout/latency/terminal ownership and external stop procedure unqualified |

## Economic Proof

Fixture lineage, native-shaped journal/reconciliation, repeated-read idempotency,
reservation conversion, strict account rejection and one-shot recovery are tested.
Actual-demo request -> broker -> terminal-state lineage is **NOT_PROVEN**.
No broker IDs or observations were invented as operator evidence. No local close,
live exposure, strategy, P4, normal-app native activation or legacy reconnection.

No MT5 module import, initialize, login, native read, submit, cancel or close was
performed. No credential file/profile or operator database was read, enumerated,
copied or modified. Tests use temporary synthetic stores; public documentation
reads are not account inspection. Claims of no exposure/access concern this task,
not unrelated processes or pre-existing broker state.

## Regression Evidence and Limits

Exact fresh counts, command allowlist, diagnostic reproduction, first-run failures
and guard limits are recorded in ../TESTING.md. New process-death coverage uses
only an explicit temporary path and scrubbed synthetic environment. The guard
is not an OS sandbox and does not propagate into that child. Existing migration
files are unchanged. No operator database migration was performed.

## Remaining Blocker

**Real machine/session and risk-context qualification**, not general lack of human
permission. The code's trusted isolation contract has only a fixture provider;
the actual verifier/native connector still must be implemented/reviewed against
a designated exclusive no-live environment. Exact current allowed demo binding,
scoped credential/session location, real P2 context and operational stop evidence
must accompany it. Do not replace this work with an assertion flag or fixture data.

The operator procedure and prerequisites are explicit in
../Components/P3-OPERATOR-VERIFICATION.md. Stop BEFORE connection until they are
proven. Then run the single minimum-volume verification and preserve all evidence.
P3's actual demo exit remains unchecked; P4 stays blocked. This tooling/evidence
work is committed separately; the containing Git commit identifies the exact tree.
