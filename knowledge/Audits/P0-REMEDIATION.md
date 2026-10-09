# P0 Blocker Remediation Evidence

Date: 2026-09-10, Asia/Karachi. Scope: B01/B02/B03 only, owner-authorized
governance remediation. P1 implementation, broker/session access, training and
application changes are prohibited in this task.

## Acceptance and Changes

| Blocker | Minimum resolution | Evidence |
|---|---|---|
| B01 | Commit reviewed V2 controls and record recoverable hash | Dedicated governance baseline commit; post-commit result in P0-CLOSEOUT-AUDIT.md |
| B02 | Approved secret locations ignored, templates trackable | AGENTS.md / SECURITY.md storage convention and positive/negative ignore probes below |
| B03 | Explicit ordinary-agent exclusion and safe default verification | AGENTS.md sensitive-path prohibition, SECURITY.md operator catalog, TESTING.md allowlist and guarded fixture run |

No source/helper change is necessary. Existing `.env` and private-directory
ignore rules already cover the owner-approved storage convention. Added comments
and a narrow `knowledge/.obsidian/` exclusion; retained all local editor files.
No general JSON, PEM or KEY extension exclusion was added. README_SETUP.md is a
pre-existing untracked file outside this P0 control package and is left untouched.

## Pre-Staging Snapshot

At 2026-09-09T19:55:23Z (2026-09-10 00:55 local):

- Branch `core-rebuild`; HEAD `80f745be7a64681a2225ef7565a344a186a58a63`.
- 101 tracked files; index unchanged; only tracked worktree change `.gitignore`.
- 25 control Markdown files scanned at this checkpoint; this evidence note was
  added afterward and must also pass the staging scan.
- All nine ADR files remain byte-identical to the approved ZIP; status fields
  accepted 001/002/003/004/007/008/009, deferred 005/006. No decision edits.

## Safe Scan Method and Results

Executed local Git metadata/object checks without loading active secrets:

```text
git status --porcelain=v1 --untracked-files=all
git diff --name-only
git diff --cached --name-only
git ls-files -z
git cat-file --batch-all-objects --batch-check=%(objectname) %(objecttype)
git cat-file <blob|commit|tag> <object-id>
git show :<index-path>
git check-ignore --no-index -v -- <explicit-probe-path>
```

In-memory pattern checks cover private-key headers (including encrypted, RSA,
EC, DSA and OpenSSH), recognizable provider prefixes (sk-, gh[pousr]_,
github_pat_, AKIA with length/character constraints), and named 32-hex credential
candidates near API-key/password/access-token/secret labels. Output includes
only file/object, rule and line metadata on a finding, never matched values.
The tracked `.env.example` credential fields were separately checked for blank,
zero or explicit placeholder values. No active environment/private contents were
opened to supply known-secret comparison values.

Pre-staging result: 167 local objects inventoried, 129 blob/commit/tag bodies and
101 index blobs scanned; zero findings and zero tracked sensitive-path candidates.
Current controls and `.gitignore` also passed. This is format-based screening,
not a guarantee that arbitrary passwords or encoded/unknown formats are absent.
Remote/sibling history and provider revocation are not certified.

## Exclusion Probes

All 15 assertions passed. Probe names do not imply files exist; no probe file
was created and no sensitive directory was enumerated.

| Explicit path | Expected and observed |
|---|---|
| `backend/.env` | Ignored, untracked; .gitignore:26 |
| `.env.local`, `backend/.env.production` | Ignored, untracked; .gitignore:27 |
| `backend/private/control_token.txt` | Ignored, untracked; .gitignore:46 |
| `backend/private/mt5/credentials.json` | Ignored, untracked; .gitignore:46 |
| `backend/private/whatsapp/session/creds.json` | Ignored, untracked; .gitignore:46 |
| `backend/private/tokens/access_token.txt` | Ignored, untracked; .gitignore:46 |
| `backend/private/keys/client.pem` | Ignored, untracked; .gitignore:46 |
| `backend/private/.env.example` | Ignored by parent directory, untracked |
| `knowledge/.obsidian/workspace.json`, `knowledge/.obsidian/app.json` | Ignored, untracked; .gitignore:49 |
| `backend/.env.example` | Trackable and already tracked; .gitignore:28 exception |
| `frontend/config.json`, `docs/public.pem`, `docs/example.key` | Not ignored; legitimate public/config extensions remain usable |

## Credential-Free Verification

Reviewed conftest, the four allowlisted modules, their runtime imports, explicit
app fixture construction and `ledger_crash_worker.py`. No runtime entry point is
imported by this subset. `create_app` gets an explicit test token and temporary
database; restore tests call only `restore()` on generated temporary snapshots,
not the operator-only known-secret scanner. Child workers use fixture account
identifiers, contracts and SQLite, with no broker imports or calls.

Executed the TESTING.md four-module selection using the existing venv Python,
bytecode/cache writes disabled and third-party pytest plugin autoload disabled.
The disposable test process retained only OS/path/temp/profile environment keys;
other inherited variables were removed without displaying or reading credential
files. This environment was inherited by its fixture subprocesses.

An ephemeral Python audit hook, installed before pytest imports, denied sensitive
`open`, `os.listdir`, `os.scandir` calls and runtime/MT5 imports in the parent.
It normalized paths and rejected active `.env` variants, backend/private paths,
common SSH/session stores and Chrome/Edge profile locations. Two deliberate
blocked probes passed before the test counter was reset. No repository helper
was created; this check is supplementary evidence, not a persistent OS sandbox.

**Run result: 105 passed, 89 warnings, 14.96 seconds; exit 0.**
**Sensitive access attempts during the parent test run: 0.**
The hook is parent-only; child workers were source-reviewed, not dynamically
audited. Warnings are FastAPI/Starlette use of deprecated asyncio inspection
APIs. No server, broker, WhatsApp session, external API or training was started.

Preserved failed check: the first temporary hook self-test missed a relative
private-path probe and raised FileNotFoundError for a deliberately nonexistent
filename. No test ran and no secret content was read in that attempt. The
verification-only harness was corrected to normalize absolute paths, both
denial probes then passed, and the complete 105-test selection was run.

The historical full application audit remains **169 passed, 1 failed, 296
warnings**, with its focused rerun and excluded training tests recorded in
CURRENT-STATE.md. This smaller passing run does not erase that failure or certify
the whole application, V2 P1/P2, trading performance or broker readiness.

## Post-Commit Evidence

The dedicated baseline and final closeout verdict are recorded in
[P0-CLOSEOUT-AUDIT.md](P0-CLOSEOUT-AUDIT.md) after actual commit verification.
No phase-completion claim is made merely from these pre-commit checks.
