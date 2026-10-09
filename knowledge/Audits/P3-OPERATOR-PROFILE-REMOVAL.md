# Dedicated Windows Operator Removal - 2026-10-02

Owner redirected the task from demo qualification to immediate removal of the
separate Windows account/profile and current-profile-only work. Actual account:
NexusAIDemoOp (not REDACTED_OPERATOR_IDENTIFIER). It had been created under the earlier explicit
non-admin provisioning approval recorded in ADR-019. ADR-021 supersedes that
Windows arrangement; no replacement account is authorized.

## Verified outcome

- Fixed, reviewed elevated removal helper exited0.
- Dedicated Windows account removed; bound Windows profile removed through
  Win32_UserProfile deletion, after exact SID/path checks and loaded-profile checks.
- Both exact scheduled tasks stopped and unregistered. Processes were stopped
  only when authoritative ownership matched the dedicated SID.
- Only the dedicated ProgramData/NexusAI/Attestor and OperatorRuntime directories
  were removed. Exact absolute targets and reparse checks preceded recursive removal.
- Project and private MT5 configuration preserved. Credentials were not read,
  printed, copied or rewritten. Owner access was restored on exact project
  boundaries by ACL changes, not by moving secrets or opening operator databases.
- Subsequent independent metadata query: dedicated accounts0, dedicated Windows
  profiles0, dedicated tasks0, project AGENTS.md present.
- Native MT5 connection/order/close:NOT_RUN. Economic broker actions0. Execution
  remains HARD_DISABLED/LIVE_LOCKED. No operational P3/V1 completion claim.

Ignored diagnostic receipt:
tmp/nexusai-profile-removal-2d14279c846d4e6a9300309559eda3df.json.

## Preserved preceding evidence

Final guarded cleanup/operator/bootstrap fixture run:42 passed in20.72s, exit0;
sensitive/operator access attempts0, forbidden runtime modules[]. The three
cleanup tests cover plan-only behavior, exact identity/path constraints and the
withdrawn-provisioning guard. Actual removal is proven separately by the elevated
receipt and independent Windows metadata query, not inferred from fixture tests.

Owner-approved Windows password/task repair succeeded; separately approved batch
logon repair granted only the dedicated account's allow right after deny checks.
Fresh host metadata audit passed63/63 and showed the configuration present, risk
basis absent, cost basis absent. This was never broker qualification. The offline
runtime path was unavailable to that account; attempted dedicated runtime setup
was subsequently removed under the newer instruction. No account credentials
were requested again or taken from Windows' vault.

Read-only bootstrap architecture was explicitly approved and recorded in ADR-020.
Its bounded implementation was interrupted by this newer removal request; it was
not run against MT5. Do not describe it as a qualified native operator path.

Focused bootstrap/operator/V1 fixture checkpoint:74 passed,32.21s, sensitive
access attempts0, forbidden runtime modules[]. This predates the final cleanup
tests and is narrower than operational qualification. Earlier relevant P3/P2/P1
checkpoint:518 passed. Earlier broad run:1145 passed/1 failed, Windows temporary
P8 registry concurrency PermissionError; not a clean broad-suite claim. No P8 fix.

## Next boundary

Normal coding/research uses the owner's current profile. The dedicated-account
provisioning entry point is disabled. Do not silently bypass the old isolation
contract, substitute the shared desktop terminal or enable trading. Current-profile
operator qualification remains outstanding; no further broker work occurred after
the owner's redirection. Unfinished source changes remain separate from this audit.
