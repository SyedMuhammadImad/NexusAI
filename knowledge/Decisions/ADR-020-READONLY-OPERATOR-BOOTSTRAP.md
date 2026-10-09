# ADR-020 - Non-executing Operator Bootstrap

Status: **ACCEPTED**, 2026-10-02. Owner explicitly replied:
"Approve read-only operator bootstrap."

## Decision

Separate first-account evidence collection from execution qualification. The
existing path requires a running isolated terminal and risk/cost files before
reading the account needed to initialize those files. A new operator-only,
read-only bootstrap may prepare the isolated terminal and read the explicitly
configured account's identity, full broker history, inventory and metadata before
risk/cost evidence exists. It cannot submit, cancel, modify or close orders.

Credentials remain in the approved private boundary. Exact configured account,
server and positive native DEMO identity are mandatory; mismatched/non-DEMO
accounts reject. No ambient terminal/account selection or copied login profiles.
Host identity, non-admin session-zero, exclusive ownership, protected resources,
fresh account-bound attestation and configured binary checks remain mandatory.
The prepare phase may prove the absence of a terminal before starting the fixed
isolated binary. The read phase requires that single isolated terminal.

For bootstrap ONLY, absent named risk/cost evidence files require proof of the
protected containing directory. This is not risk/cost qualification. It cannot
authorize ExecutionRequests or satisfy the existing submission preflight.

Use a fresh isolated verification ledger, initially HALTED. Preserve broker
observations append-only. Initialize unused-account baselines ONLY after ADR-019
history/inventory/DEMO checks pass. Unknown external entities stay quarantined;
never adopt them or reset existing account baselines. Missing commission evidence
still blocks trading. Do not invent zero fees or reset HALT.

No numerical P2 change, live-money capability, execution enablement, strategy
activation, P8 work or P3 closeout follows from this decision. Normal execution
attestor/request contracts must not accept a bootstrap receipt as execution proof.

## Related approvals

The owner separately explicitly authorized the dedicated Windows password/task
repair and the dedicated batch-logon allow right after deny-rule inspection.
No other accounts, deny policies, broker credentials or risk limits may change.
