# V1 Current-Profile Worktree Review - 2026-10-05

Starting branch: core-rebuild. Starting HEAD: d98b9c5.
Every initial changed/untracked file was read without reading private credentials,
operator databases or environment files. No initial file contains an active secret;
example and test values are placeholders/fixtures. No REVERT or deletion performed.
KEEP below means bounded retained engineering, never operational qualification.

| Initial path | Classification | Purpose, completeness, tests and disposition |
|---|---|---|
| backend/core/rebuild/monitoring.py | KEEP | Heartbeat coverage, lineage, counters; fixture-tested in test_v1_completion; no native producer |
| backend/core/rebuild/native_operator.py | KEEP / DEPRECATED host branch | SYSTEM_FILES support depends on removed infrastructure; not replacement qualification; retain historical fixtures, do not invoke |
| backend/core/rebuild/operations.py | KEEP | Reads monitoring/observer projections; remains HARD_DISABLED; fixture-tested |
| backend/examples/p3-operator.example.json | KEEP | Public LOCAL placeholder, no credentials; old service contract remains historical |
| frontend/src/OperationsWorkspace.jsx | KEEP | Shows added evidence tables; controls remain disabled; build verification required |
| README_SETUP.md | KEEP / historical | Original control-package installation note, not current phase instructions; no runtime consumer/secret |
| backend/core/rebuild/host_attestation.py | KEEP / DEPRECATED provider | Pure legacy receipt validator; tested, not current-profile proof |
| backend/core/rebuild/operator_bootstrap.py | KEEP / DEPRECATED entry point | Read-only native evidence normalization tested; native_bootstrap depends on removed attestor and was never run; reuse pure collect only after qualification |
| backend/core/rebuild/qualification_basis.py | KEEP | ADR-019 once-only cash-flow/boundary producer; fixture tests; does not reconstruct missing history |
| backend/core/rebuild/strategy_observer.py | KEEP | Five frozen rules, closed-bar checkpoint/replay, BID/tick semantics; observation-only and P4 strategy firewall retained |
| backend/tests/test_p3_readonly_bootstrap.py | KEEP | Native-shaped fake evidence, invalid-account/history guards; no native import |
| backend/tests/test_v1_completion.py | KEEP | Baseline, observer, monitoring, historical receipt and script fixture tests |
| backend/tests/test_v1_operator_audit.py | KEEP | Mocked legacy diagnostics/native interop compilation; never actual repairs in tests |
| scripts/p3_attestor_client.ps1 | KEEP / DEPRECATED | Old authenticated file exchange; removed service dependency, not launched |
| scripts/p3_operator_host_probe.ps1 | KEEP / DEPRECATED | Old scheduled worker; not current-profile launcher |
| scripts/p3_operator_status.ps1 | KEEP / DEPRECATED | Historical fixed task diagnostics/repair; no replacement qualification claim |
| scripts/p3_system_attestor.ps1 | KEEP / DEPRECATED | Old read-only SYSTEM service source, not installed/recreated |
| scripts/provision_p3_readonly_runtime.ps1 | KEEP / DEPRECATED | Historical dedicated-worker repair; default PLAN_ONLY, removed identity/protected profile required for changes; do not run |
| scripts/repair_p3_batch_logon.ps1 | KEEP / DEPRECATED | Historical single-account policy repair; default PLAN_ONLY; no current authorization |
| scripts/repair_p3_operator_credential.ps1 | KEEP / DEPRECATED | Historical single-account password repair; default PLAN_ONLY; no current authorization |
| scripts/update_p3_metadata_probe.ps1 | KEEP / DEPRECATED | Historical protected task deployment; default PLAN_ONLY; no current authorization |

All removed-account references in the above are historical/provider-specific,
not prerequisites to recreate the account. Existing provisioning remains blocked
by ADR-021. Current-profile replacement is ADR-022, a distinct contract, never
fabricated dedicated_identity/session_zero booleans. Existing deprecated tools
remain preserved for evidence and tests, not installed or operational consumers.

## Regression reproduction and narrow repair

Initial guarded broad selection: 1 failed,1177 passed,2333 warnings,273.23s.
Failure: test_p8_research.py::test_registry_concurrent_replay. Windows denied
concurrent replace/read of the same content-addressed JSON artifact. Publication
occurred before the registry's SQLite BEGIN IMMEDIATE, permitting competing
publishers despite serializing the later registry insert. Introducing commit:
c6e3c55 (this publication implementation first appears there).

New deterministic storage test failed on the old code: publication did not hold
the cross-connection writer lock. Initial new tests:1 failed/1 passed,3.84s.
Fix: serialize artifact inspection/publication and append-only registry insertion
inside the existing SQLite write transaction. Preserve fsync, atomic replacement,
hash/path validation, crash recovery and immutable registry rows. No retries,
permission suppression, test skips, model fitting, parameter changes or research
result rewrites. The narrow P8 storage repair is solely the explicitly requested
regression fix; P8 research remains PASS_THROUGH/deferred.

Final guarded broad:1180 passed,2333 warnings,289.09s. Focused154 passed,32.81s;
all runs zero sensitive/operator attempts and forbidden modules[]. Frontend build
passes; existing desktop/mobile seven-page checks pass with browser errors[].
Preview is fixture-only and stopped. Native operator/broker/V1 remain unproven.
This commit preserves the reconciled non-executing integration baseline; subsequent
operator documentation records its immutable hash. Nothing was pushed.
