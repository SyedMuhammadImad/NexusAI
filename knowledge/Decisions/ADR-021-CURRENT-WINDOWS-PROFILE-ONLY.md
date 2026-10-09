# ADR-021 - Current Windows Profile Only

Status: **ACCEPTED**, 2026-10-02, explicit owner instruction to remove the separate
NexusAI Windows account/profile and perform future work in the current profile.

The actual dedicated account is NexusAIDemoOp, not REDACTED_SOURCE. It was created
under the earlier explicitly approved ADR-019 provisioning/isolation boundary.
The owner now withdraws that dedicated-account arrangement. Stop/unregister its
host-probe and privileged attestor tasks, remove only the bound dedicated Windows
account/profile and dedicated ProgramData infrastructure, preserve the project
and private broker configuration, and restore the owner's access on the exact
project boundaries without reading credential values.

Do not create another Windows account or reinstall the removed infrastructure
without new explicit authorization. The provisioning entry point is fail-closed.
ADR-019's qualification-start equity semantics remain approved; its dedicated
Windows provisioning arrangement is superseded. ADR-020's bootstrap sequencing
approval does not authorize recreating that arrangement or weakening any gate.

Future ordinary coding/research runs in the current Windows profile. Broker
execution remains HARD_DISABLED and LIVE_LOCKED. This decision is NOT proof that
the current personal profile satisfies operator isolation, and does not authorize
an administrator trading worker, shared-terminal fallback, unqualified broker
access or an execution-policy bypass. A qualified replacement operator boundary
is still outstanding. No demo connection/order occurred before this instruction.
