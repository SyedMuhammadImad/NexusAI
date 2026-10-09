# ADR-012 - Split P3 Engineering and Operator Verification

Status: **ACCEPTED**
Authority: explicit owner roadmap-amendment request, 2026-09-13.
Inspected baseline: `6c2cbc7de8d1ad804d2c14a2e57eaa1c654fdc93`.

## Decision

Separate engineering completion from operational qualification:

- **P3 ENGINEERING: VERIFIED_COMPLETE**, exclusively within the existing
  non-operational/fixture/native-normalization scope.
- **P3 OPERATOR DEMO VERIFICATION: DEFERRED / PENDING**. Actual machine/account
  qualification and demo broker verification remain incomplete.
- **BROKER EXECUTION: HARD DISABLED** for the application and all P4-P9 work.

Do not label combined P3, actual broker verification, production readiness or
forward-demo qualification VERIFIED_COMPLETE. Deferral is not a waiver and does
not reduce any operator gate or existing evidence standard.

This explicitly amends the phase dependency portions of the V2 specification and
ROADMAP: full operational P3 completion no longer blocks non-executing P4-P9
engineering/research. It replaces the former P5 parallel-development dependency
with the sequence below. It does not amend ADR-008 live restrictions, ADR-010
risk policy, ADR-011 evidence semantics or the substantive phase exit criteria.

## Dependency Sequence

| Phase | Status now | Required dependency / scope |
|---|---|---|
| P0 | VERIFIED_COMPLETE | Existing evidence retained |
| P1 | VERIFIED_COMPLETE | Existing evidence retained |
| P2 | VERIFIED_COMPLETE | Existing evidence retained |
| P3 Engineering | VERIFIED_COMPLETE | Bounded non-operational engineering only |
| P3 Operator Verification | DEFERRED | PENDING actual isolated operator/demo evidence |
| P4 | READY | Non-executing source/canonical engineering only |
| P5 | BLOCKED | P4 |
| P6 | BLOCKED | P5 |
| P7 | BLOCKED | P6 |
| P8 | BLOCKED | P7 |
| P9 | BLOCKED | P8 |
| P10 | BLOCKED | P3 OPERATOR VERIFICATION + P9 |

P4-P9 become eligible sequentially for non-executing engineering/research, not
automatic implementation in this task. Phase-specific evidence, data quality and
accepted semantics remain required. ADR-005 and ADR-006 remain DEFERRED; resolve
their decisions before implementing dependent ML/tournament semantics. This ADR
does not invent those decisions, authorize unverified training labels, or qualify
any strategy/model for execution. P11 remains outside current authorization.

## Mandatory Execution Boundary

```text
Signal -> Canonical lifecycle -> P2 Safety -> ExecutionRequest
                                                |
                                    BROKER EXECUTION DISABLED
```

An ExecutionRequest is not submission permission. Missing real safety evidence
still rejects; synthetic inputs and simulated outcomes retain fixture/research
provenance. No P4/P5/P6/P7/P8/P9 component, UI, scheduler, source adapter or research
process may load an operational adapter, call the isolated operator helpers,
reconnect legacy agents, switch execution on, or bypass P2/HALT/the hard block.
Future integration acceptance must demonstrate that signals/requests stop at this
boundary and that no broker submission or fabricated broker outcome is possible
through its normal non-executing paths. Do not queue stale research approvals for
automatic broker submission when operational qualification is later completed.

P3 operator verification is mandatory BEFORE:

1. Any actual MT5 demo execution outside the separately authorized isolated
   verification step itself.
2. P10 forward demo qualification (also requires P9 and existing qualification rules).
3. Any live-readiness work. This is necessary, never sufficient: ADR-008 keeps
   LIVE locked and requires separate explicit authorization outside this roadmap.

The only potential exception to the hard block is the existing isolated operator
verification step, after separate explicit authorization and every original
account/isolation/P2/HALT/minimum-volume gate is proven. That exception is not
available to P4-P9 and is NOT authorized or run by this amendment. No credentials,
MT5 connection, order, HALT reset, environment/config change or application code
change is authorized here.

## Evidence Preserved and Limits

Existing TESTING.md records 307 focused P3 and 604 broad tests at the provider
closeout, plus 100 offline setup/provider tests at the setup closeout. These are
prior bounded results, not newly rerun tests or actual account attestation.
P3 execution/reconciliation, native normalization, revision history, crash/replay
and isolated-wrapper evidence remain intact. See Components/P3-EXECUTION-RECONCILIATION.md,
Components/P3-NATIVE-EVIDENCE.md and Audits/P3-NATIVE-OPERATOR-QUALIFICATION.md.
The historical missing-files pre-flight is preserved; private paths are not
rechecked in this task and their current contents remain unknown.

Source inspection of `backend/core/rebuild/application.py:create_app` confirms
normal composition has no execution adapter and refuses native accounts/adapters;
explicit execution injection accepts FIXTURE scope only. Existing native operator
helpers remain separate, gated and unqualified, not deleted. HARD DISABLED here
preserves that application boundary and governs future integrations; a Markdown
amendment does not create a new OS-level broker lock or prove machine isolation.

Verification for this amendment is documentation dependency/status consistency,
preserved evidence/unchecked operational gates and Markdown-only Git diff checks.
No application tests or operator processes are run; runtime state is not newly
attested. Old dated PARTIAL/P4 BLOCKED statements remain historical checkpoints
superseded by this explicit split, not erased evidence.

Document verification passed: all 12 P0-P10 split-status rows, sequential P5-P9
dependencies, P10's combined dependency, retained unchecked demo attestation gate,
accepted ADR/execution-boundary wording, Markdown-only tracked diff and whitespace
checks. The unrelated untracked README_SETUP.md was left untouched. No application
or operator state change is part of this result.
