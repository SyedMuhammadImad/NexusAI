# ADR-019 - Qualification-start Baselines and Operator Provisioning

Status: **ACCEPTED**, 2026-10-02, for the two explicit owner approvals in chat.

## Qualification-start initialization

After positive configured DEMO identity, complete account history and empty
inventory are evidenced, an unused account may initialize daily, weekly and
high-water equity from its first fresh qualification snapshot. Preserve its actual
timestamp as `qualification_started_at`; do NOT claim an observation at midnight
or a full prior day/week. UTC period labels remain the P2 period identifiers, not
the timestamps of equity measurements. No P2 numerical limit changes.

Initialization is once-only and account-bound. Recorded prior trading, existing
P2 baselines, missing history, unknown cash flows, stale evidence or mismatches
reject. Persist immutable evidence; retry/restart cannot reset a loss baseline.
Subsequent same-period samples cash-flow-adjust the retained bases and high-water
mark. UTC day/week rollover requires an evidenced boundary equity observation;
missing boundary evidence blocks admission rather than inventing midnight equity.

This supersedes ADR-018's existing-account-only choice for this unused demo
account, not its recorded-history prohibition for previously traded accounts.
Neither approval nor initialization proves the account is actually unused.

## Provisioning authorization

The owner authorizes one-time elevated provisioning of a dedicated non-admin
Windows operator identity, isolated portable terminal and restricted directories,
and will handle Windows elevation. Trading must never run elevated. Existing
host attestation, session-zero, exclusive-process, ACL, exact binary/account,
fresh P2, cost and HALT gates remain mandatory. Provisioning is not qualification.
Do not weaken a failed host gate or silently introduce a privileged trading path.

The owner additionally APPROVED a separate privileged, read-only isolation
attestor after the non-admin metadata probe could not resolve 151/373 process
owners. Its output is restricted to fresh account-bound process/session/ACL
evidence. It has no broker API, credential-return route or trading callback.
Provisioned privileged scripts/configuration must be write-protected from the
non-admin worker and normal coding identity. Requests must be authenticated to
the dedicated worker SID, fixed protected resources and actual requesting PID;
replay, stale receipts, extra request fields and incomplete ownership reject.
The broker worker cannot supply arbitrary paths, scripts or commands for elevated
execution. Existing isolation booleans remain mandatory, not bypassed by IPC.

## Scope

Active P8 work is DEFERRED for V1; retain the verified 2026-10-01 research evidence
and negative/insufficient/runtime-blocked dispositions. No new training/research.
P10 is DEFERRED_FORWARD_QUALIFICATION; P11 is OUT_OF_V1_SCOPE. Broker execution
stays HARD_DISABLED pending actual operator and end-to-end qualification.
