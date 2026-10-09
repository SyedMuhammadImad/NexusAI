# Local Secret Storage and Agent Access Policy

## WhatsApp Source Metadata Authorization (2026-10-02)

Owner confirms the existing authorized sender number and announcement source.
connectors/whatsapp/identity.mjs is OPERATOR-ONLY for this bounded lookup, using
only backend/private/whatsapp/v1/auth and new immutable source-identity-UUID.json
receipts in that same ignored boundary. Approved phone/labels arrive via stdin,
never hardcoded source or command-line arguments. No normal/private operator DB,
MT5/.env/other credential store or message history is accessed. It cannot send,
deliver, create a connector token or enable execution.

Matching names are discovery criteria, not standalone authority. Verify exact
PN/LID, linked account, group and membership/admin evidence; retain exact IDs
privately. Public diagnostics contain fixed codes, booleans and matching titles,
not phone/account/group IDs, messages or secret values. Native failures are
sanitized. Internal provider API drift must fail closed, not infer identifiers.

## WhatsApp Login-only Operator Authorization (2026-10-02)

The owner requests QR linking before providing source group/sender details.
connectors/whatsapp/pair.mjs is OPERATOR-ONLY for the fixed ignored
backend/private/whatsapp/v1/auth boundary. It uses no personal browser profile,
connector token, MT5 credentials or operator database. No application message
handlers, delivery, broker calls or execution unlock exist in that launcher.
Its visible dedicated browser shows QR directly; payloads/provider errors are
not printed. Linking is not group/sender authorization or economic permission.
Tests inject fake clients and never access the real authentication directory.
No concurrent connector/pairing against this profile. Bounded failed shutdown may
stop only the client-owned browser handle, reports uncertainty and cannot claim
durable session restoration. Existing sensitive-path rules remain unchanged.

Authority: owner's P0 blocker-remediation request, 2026-09-10. This operational
policy resolves B02/B03; it does not amend any accepted or deferred ADR.

## Approved Locations

- `backend/.env` and other intentionally local-only runtime `.env` variants.
- `backend/private/**`, including future `mt5/`, `whatsapp/`, `tokens/`, `keys/`.

Broker/MT5 credentials, API secrets, passwords, access/control tokens, private keys
and session credentials must be stored only in those ignored sensitive locations.
New integrations must use this convention. An external configured session store
is also sensitive and operator-only; a location change requires explicit review,
not silent relocation by an agent. No real credential was created or moved for P0.

`.gitignore` excludes `.env`, `.env.*` and `backend/private/`. The exception
`!.env.example` permits reviewed placeholder templates outside private directories.
Templates must never contain usable secrets. A public certificate or legitimate
JSON/key configuration is not globally ignored merely because of its extension.
Secrets outside approved locations violate policy even if a scanner misses them.

## Ordinary Agent Scope

V1 addition (2026-09-28): `connectors/whatsapp/operator.mjs` is OPERATOR-ONLY.
It reads only the explicitly configured `backend/private/whatsapp/v1/` boundary
and may create a dedicated browser session/QR/outbox there. Do not invoke it during
normal coding, builds or tests. Live use is not qualified; dependency review and
authorized source/linking remain mandatory. `bridge.mjs` and its tests are pure
fixture-safe transport/queue code and do not import the WhatsApp client.
`scripts/v1_preview.py` uses the normalized guard and a fresh temporary fixture DB;
its public synthetic token cannot be substituted for an operator credential.

Agents must not read, print, copy, modify, enumerate contents of, or use credentials
in active environment files, `backend/private/**`, configured WhatsApp/session
stores, SSH/private-key locations, browser profiles/credential stores, user-home
credential stores or unrelated machine secrets. See root `AGENTS.md`.

Checking Git tracking and ignore metadata for explicitly named paths is allowed.
It does not permit opening active secrets, reading their values for comparisons,
or recursively listing private contents. Safe scans inspect tracked/staged public
content and emit only finding identifiers/paths/line numbers, never values.
Stop on suspicious staging; do not force-add ignored files.

Normal development and P1 verification need no real broker, API, WhatsApp or
control-token credentials. Use mocks, temporary databases, placeholders and
synthetic account IDs; the current allowlist is in `TESTING.md`.

## OPERATOR-ONLY Entry Points

`scripts/validate_p3_operator_files.py --operator-files` is an offline, read-only
OPERATOR-ONLY schema/consistency check for the three fixed P3 files. It emits fixed
statuses, not input values or exception text. No MT5, terminal binary, database,
HALT reset or order is reached. Without the flag it validates only public examples.
The setup task never runs private-file mode against real files. See
Components/P3-OPERATOR-SETUP.md for fields, sensitivity and required evidence.

2026-09-13 addition: importing `core.rebuild.native_operator` is credential-free.
Its `load_settings`, fixed private risk/cost readers, `open_native_operator`,
`NativeConnector`, `WindowsTerminalIsolation` and `native_readonly_preflight`
are explicit OPERATOR-ONLY operations, not routine test/startup helpers.
`scripts/p3_native_preflight.py` without flags performs only metadata inspection
of three fixed approved paths; `--attest` may read those private files and connect
only after host gates. `scripts/p3_windows_host.ps1` inspects designated host
identity/process/ACL metadata; never run it as a routine credential-free test.
No credential transfer, discovery, live fallback, private JSON callback or CLI
unlock is provided. Native identities/evidence belong only in protected isolated
verification state; public reports contain gates/digests, never logins/passwords.
See Components/P3-NATIVE-OPERATOR-PROVIDERS.md. This task ran metadata-only mode,
which stopped on missing files before credential/native/database access.

| Existing entry point | Why routine agents must not run it |
|---|---|
| `scripts/verify_phase0.py` CLI / `scan_repositories()` | Loads active environment/token values, including sibling repositories, for known-secret comparisons. Its pure `restore()` function may be tested with synthetic temporary fixtures only. |
| `scripts/verify_rebuild_ui.cjs` | Reads the active private control token for runtime UI verification. |
| `scripts/setup_local_access.py` | Reads environment/private token and may create local access material. |
| `scripts/start_local.ps1`, `start.sh` | Launch local runtime; setup/runtime can read active credentials. |
| `backend/main.py`, `backend/legacy_application.py`, runtime server commands | Load local environment/runtime configuration. Legacy startup remains forbidden by phase gates. |
| `create_app()` with token omitted | May read the private control-token file; tests must pass an explicit synthetic token or explicit empty string. |

This is a reviewed minimum catalog, not permission to run unlisted scripts.
Review transitive imports and fixture construction before adding tests/helpers to
the ordinary allowlist. Do not run blanket test discovery that imports legacy
runtime configuration in the credential-bearing checkout.

Credential-dependent checks require explicit operator authorization describing
paths, purpose and allowed actions. That authorization does not override halted
execution, phase gates or the live-money prohibition. These scripts are retained;
their operator-only classification does not justify deletion.

## P3 Operator Tooling Boundary (2026-09-12)

The owner explicitly authorized minimum P3 operator-only tooling. The pure
`core.rebuild.operator_verification` module and `scripts/p3_operator_preflight.py`
do not load credentials, connect to native MT5 or open an existing operator store.
The diagnostic is permitted for credential-free verification and exits 2 while
no qualified operator composition exists. There is no CLI execution unlock.

`OperatorVerification.connect(connector)` is OPERATOR-ONLY when supplied a real
connector. The injected isolation verifier must establish the exact allowed demo
account, exclusive no-live session, scoped approved credential locations, isolated
filesystem ownership, qualified context and stop procedure BEFORE the connector
can run. No machine-specific verifier or native connector is supplied/qualified
by the current work. Never replace it with a boolean or import a fixture verifier
into the real path. The existing secret boundary and live prohibition still apply.

New evidence-only run state belongs in ignored `.p3-verification/`, never credentials.
Only fresh fixed-path ledgers are created there; normal data/private stores are
not migrated. File/link checks are not OS isolation. Do not remove the workspace
single-use claim or create a second checkout to bypass the one-trade authorization.
Components/P3-OPERATOR-VERIFICATION.md documents the remaining qualification.

## Local Editor State

`knowledge/.obsidian/` is ignored. Its four existing JSON files are local editor
settings/UI state, not part of the approved governance ZIP. No cross-machine
configuration was selected for tracking. Existing local files are preserved.

## Evidence Limits

This is a storage and operating policy plus tested Git exclusions, not OS ACL
enforcement. Ignore rules do not prevent reads or force-adds. Safe format scans
cannot prove absence of every arbitrary password, encoding or unknown token.
Remote history cleanup, prior exposure and provider revocation remain UNVERIFIED
by this task. Local Git recovery does not restore ignored credentials/databases
or provide an off-device backup. No external secret stores were inspected.
