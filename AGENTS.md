# NexusAI V2 — Coding Agent Operating Rules

## Authority

Before any repository modification, read in order:

1. `NEXUSAI_V2_SPECIFICATION.md`
2. `knowledge/PROJECT.md`
3. `knowledge/ARCHITECTURE.md`
4. `knowledge/CURRENT-STATE.md`
5. `knowledge/ROADMAP.md`
6. `knowledge/TESTING.md`
7. `knowledge/RISKS.md`
8. accepted ADRs under `knowledge/Decisions/`

`NexusAI_Master_Prompt.md` is historical intent and is **not authoritative** where it differs from V2.

## Ground-Truth Rule

Do not claim functionality from filenames, comments, class names, README text or the existence of code. Current-state claims require source/test/runtime/broker evidence. If evidence is insufficient, use `UNVERIFIED` or `UNKNOWN`.

## Scope Rule

Work only on the current authorized roadmap phase and task. Do not implement future phases, speculative agents, dashboards, strategies, ML, RL or optimizations because they appear useful.

## Plan Before Build

Before modifying code:

1. identify the exact roadmap item;
2. verify the problem exists in the current checkout;
3. identify affected files/data/contracts;
4. identify relevant ADRs and unresolved human decisions;
5. define acceptance criteria and tests;
6. propose the smallest correct change.

If the task requires a `NEEDS_HUMAN_DECISION` item with no accepted ADR, stop implementation and report the decision required.

## Safety

- Keep execution disabled unless the current phase explicitly authorizes controlled MT5 demo testing.
- Never enable live-money trading.
- Never expose, print, commit or copy secrets.
- Never use synthetic price data for qualification claims.
- Never train profitability ML on acceptance/parser labels.
- Never bypass the authoritative safety gate.
- Never treat local inferred closes as broker-confirmed outcomes.
- Never use symbol-only attribution for economic outcomes.
- Never silently change risk policy, thresholds, source expiry semantics or qualification gates.

## Sensitive-Path Boundary (P0 Owner-Authorized Remediation)

Authorized local secret storage is `backend/.env`, intentionally local-only runtime
`.env` variants, and `backend/private/**`. Future MT5, broker, WhatsApp/session,
API, access/control-token and private-key material belongs in those ignored
locations, preferably `backend/private/{mt5,whatsapp,tokens,keys}/`. Safe
`.env.example` templates remain trackable and must contain placeholders only.
Do not place secrets in source, documentation, fixtures or other configuration.

Ordinary coding agents MUST NOT read, print, copy, modify, enumerate contents of,
or use credentials from active `.env` files, `backend/private/**`, any configured
WhatsApp/session credential directory, SSH/private-key locations, browser
credential/profile stores, user-home credential stores, or unrelated machine
secrets. A credential-dependent operator task requires explicit user authorization
for its scope; general implementation/test authorization is not sufficient.
Never disclose secret values, including during an authorized operator task.

Git tracking/ignore checks on explicitly named paths are permitted; they do not
authorize opening those paths or recursively discovering private contents.
Normal implementation, P1 development, tests, linting and verification must use
fixtures, mocks, placeholders, safe `.env.example` and synthetic credential IDs.
They must not require real broker, WhatsApp, API or control-token secrets.

Use the credential-free allowlisted workflow in `knowledge/TESTING.md`.
Credential-reading runtime/startup helpers are OPERATOR-ONLY as catalogued in
`knowledge/SECURITY.md`; do not delete or run them as routine verification.
Ignore rules and these agent instructions are not an OS filesystem sandbox.

## Completion Rule

A task is not complete because code was written. Completion requires the applicable gates in `knowledge/TESTING.md`, evidence capture, and documentation updates.

After verified work:

- update `knowledge/CURRENT-STATE.md`;
- update `knowledge/ROADMAP.md` only if exit/acceptance criteria passed;
- update relevant bug/component note;
- create/update an ADR for architecture or policy changes;
- record test evidence and commit hash.

## Architecture Changes

Do not silently redesign the system. Architecture/policy changes require a proposed ADR. Accepted ADRs may override earlier V2 details only when the conflict is explicit.

## Deletion

`DELETE_CANDIDATE` is not permission to delete. Before deletion:

1. prove current reachability/consumers;
2. preserve required evidence/history;
3. identify migration/rollback impact;
4. obtain explicit approval;
5. run regression tests after removal.

## Disagreement Rule

If code, tests, vault documentation and V2 disagree, stop and report the drift. Do not automatically make code match docs or docs match code without determining which authority applies.

## P0 Decision Baseline

Accepted: ADR-001, ADR-002, ADR-003, ADR-004, ADR-007, ADR-008, ADR-009.  
Deferred: ADR-005, ADR-006.

Do not reinterpret accepted decisions or implement deferred semantics.

## P0 Closeout Constraint

Before beginning P1 code, verify and record:

1. the current repository has a recoverable baseline commit/tag;
2. the updated V2/Obsidian control files are committed;
3. credential/secret exclusions are verified.

Only after those checks have evidence may `knowledge/ROADMAP.md` mark P0 `VERIFIED_COMPLETE` and P1 `READY`.
