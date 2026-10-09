# Nightly NexusAI Drift Audit Prompt

Perform a read-only NexusAI consistency audit.

Read `AGENTS.md`, `NEXUSAI_V2_SPECIFICATION.md`, and all core `knowledge/` control files. Compare them with the current repository, recent Git changes, dependency manifests and test results.

Detect and report:

1. code changes not reflected in current-state/architecture documentation;
2. documentation claims unsupported by evidence;
3. roadmap tasks marked complete without required gates;
4. failing/flaky tests or skipped critical tests;
5. new dependencies;
6. architecture drift;
7. TODO/FIXME/HACK markers introduced;
8. secret/credential exposure risk;
9. unapproved scope expansion;
10. stale verification dates;
11. changes to HALT, demo-only, risk/compliance or execution controls;
12. new deletion candidates or restored legacy paths.

Do not modify source code. Do not change statuses automatically. Do not rewrite architecture. UNKNOWN remains UNKNOWN.

Write `knowledge/Audits/DAILY-AUDIT-YYYY-MM-DD.md` with severity levels CRITICAL/HIGH/MEDIUM/LOW/INFO and exact evidence paths/tests/commits where possible.
