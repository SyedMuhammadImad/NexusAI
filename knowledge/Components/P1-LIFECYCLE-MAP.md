# P1 Milestone 1: Canonical Lifecycle Map

## Current Human Disposition (2026-09-10)

M2: **COMPLETE_WITH_RECORDED_INCIDENT** by explicit owner acceptance following
review commit `f32eb2b3cc426350b18f3f2a44890c9e75afd991`. The unchanged operator
database hash, integrity, schema/data, size/mtime and tested isolation support the
decision; unmeasured filesystem access-time effects are accepted, not disproven.
Historical PARTIAL statements below remain the dated record, not current status.
No database repair/access is authorized. M3 is existing P1 exit-gate verification,
not a new feature milestone or permission for P2/broker/trading work.

## P1-M3 Final Exit Verification (2026-09-10)

**M3 COMPLETE; P1 VERIFIED_COMPLETE.** Existing M1/M2 implementation already meets
the five P1 exit criteria; no new feature, source/test edit or migration was needed.
Fresh guarded broad regression: 218 passed / 1010 warnings / 27.08s. Focused
M1/M2/isolation selection: 94 passed / 754 warnings / 15.25s. Both exit 0; six
synthetic guard checks; zero sensitive/operator access attempts; no forbidden
runtime modules. Application/test baseline: f32eb2b3cc426350b18f3f2a44890c9e75afd991.

The exact requirement -> source -> test -> result matrix, unresolved later-phase
limits and reproducible commands are in `../Audits/P1-M3-EXIT-GATE.md` and
`../TESTING.md`. Historical "remaining" sections below describe their original
milestone checkpoints; they do not authorize new work or override this closeout.
No operator data/credentials were accessed for M3. Broker execution, P2 policy,
legacy backfill/revision and learning-store atomicity are not claimed complete.

## Pre-Implementation Evidence

Recorded 2026-09-10 before source modification. Repository `D:/project`,
branch `core-rebuild`, HEAD `386e512347bd022d8cbd0c5a79649d25ca5b3fdc`.
Approved baseline `ae800c743bb7216b666dfca11c4751fb79022282` is an ancestor
(`git merge-base --is-ancestor`, exit 0). Only `README_SETUP.md` is untracked;
no tracked source changes existed. All requested authority notes and nine ADRs
read; 001/002/003/004/007/008/009 accepted, 005/006 deferred unchanged.

CURRENT VERIFIED BEHAVIOR is not the P1 TARGET BEHAVIOR below.

| Current component / exact source | Classification | Current evidence / limitation |
|---|---|---|
| `backend/main.py` | REUSABLE_WITH_FIX | Default entrypoint calls create_app; reads local env at runtime, so inspected as source only, never imported for tests. No legacy startup. |
| `backend/core/rebuild/application.py:create_app` | VERIFIED_REUSABLE | Authenticated fixture HTTP, write freeze, persistent HALT. Only constructs Ledger for status/HALT; lifecycle ingestion missing. |
| `backend/services/signal_parser.py:SignalParser` | VERIFIED_REUSABLE | Deterministic extraction, finite/geometry/TP grammar tests. Parser-generated ID includes raw text; do not use that as the new source-event primary identity. |
| `backend/core/rebuild/contracts.py:Signal,parse_source` | REUSABLE_WITH_FIX | Strict immutable signal.v1, timestamp ordering, identity conflict/replay. Old source names differ from ADR-001; original timezone/raw time evidence and Source Event parent absent. Preserve v1, use explicitly versioned new contract. |
| `backend/core/rebuild/ledger.py:IntentRequest,Ledger` | REUSABLE_WITH_FIX | Exact account/client/signal identities, transactions, OPEN-level matching, replay guards. Existing intent reserves client_order_id before any safety decision; it is not an execution authorization. Extend rather than duplicate order_intents. |
| `ledger.py:DemoAccount` / account_binding | VERIFIED_REUSABLE | Immutable explicit demo-account binding and mismatch rejection. FIXTURE is not broker attestation. Default application is deliberately unbound. |
| `ledger.py:BrokerOrder,BrokerDeal,BrokerPosition` | VERIFIED_REUSABLE | Bounded fixture observation, quarantine, partial/replay/exact-lineage tests. Not attested broker truth; keep ingestion off HTTP. |
| risk_decisions table | REUSABLE_WITH_FIX | Schema exists; no persisted typed safety service, explanation or policy/version contract. Reuse table with additive columns, no parallel safety table. |
| Source Event and Execution Request | MISSING | No dedicated contracts/tables or active service. |
| trade_outcomes table | REUSABLE_WITH_FIX | Broker-confirmed-shaped schema only; no canonical outcome model/attesting writer. Existing fixtures leave outcome count zero; no outcome implementation in M1. |
| migration_runner.py; migrations 001/002 | VERIFIED_REUSABLE | Serialized, checksummed, transactional migrations and tamper/restore tests. Applied files must remain byte-unchanged. |
| chat_import_service.py; trader_learning_store.py | REUSABLE_WITH_FIX | Separate archive/import/message/learning stores, not canonical ledger lineage. Adapter/cross-database integration excluded from M1. |
| core/orchestrator.py; agents/*.py; legacy_application.py | LEGACY_DO_NOT_CONNECT | Retired composition, risk/compliance/execution/portfolio/learning/backtesting paths. No new imports or startup allowed. |
| Actual database contents, account/provider state | UNKNOWN | Private/runtime databases and secrets not opened. No live migration or broker claim. |

Fresh baseline regression: four TESTING.md allowlisted modules, **105 passed,
89 warnings in 13.98s**, exit 0; guarded parent secret access attempts 0.
Historical broader result remains 169 passed / 1 failed / 296 warnings.

## Existing Tables and IDs

- signals: signal_id; unique (source_type,source_id,source_message_id), immutable
  payload/hash, source/received timestamps, parser version/status.
- order_intents: intent_id = hash(account key, reserved client_order_id); immutable
  request/hash, signal_id FK, action/levels/volume, created_at and mutable observation
  state. Unique logical (signal,action,target position); never symbol identity.
- risk_decisions: risk_decision_id, intent_id FK, verdict/reasons, allocation
  fields, state_version and timestamp; not currently used by active app.
- reservations: intent_id FK; P2 allocation behavior not implemented here.
- account_binding: immutable singleton account key and evidence payload.
- broker_orders -> order_intents; broker_deals -> broker_orders / exact positions;
  positions -> originating intent. order_observations / position_observations
  retain replay evidence. No implied broker execution from these records.
- trade_outcomes -> positions, unique position; audit_events -> optional intent;
  quarantine stores unresolved broker evidence; halt_state is durable control.
- schema_migrations / migration_checksums preserve schema history.

## P1 Target Behavior (Not Yet Implemented at Map Creation)

SourceEvent -> CanonicalSignal(signal.v2, VALID) -> proposed OPEN TradeIntent
-> persisted SafetyDecision -> fixture-only ExecutionRequest; exact-ID trace
includes existing broker/outcome tables without creating broker evidence.

Reuse signals, order_intents, risk_decisions, account_binding and audit_events.
Add only missing source_events and execution_requests tables in migration 003;
add nullable provenance/decision metadata for compatibility with old evidence.
Do not relabel old source types, recreate IDs, backfill missing timezone evidence,
or invent historical safety approvals. Old records remain distinguishable as v1.

Source event IDs are caller-supplied stable transport IDs; unique source/message
identity prevents a second ID silently duplicating an event. Raw evidence is
immutable conflict-checked, not used as primary identity. Signal v2 ID derives
from the source event ID and contract/parser versions, not mutable display text.
Preserve raw timestamp/timezone evidence; supplied canonical datetimes must be
timezone-aware and normalize to UTC. Unknown time can be stored, not validated
into a signal. No freshness eligibility is inferred from successful storage.

Intent reuse preserves client_order_id as a reserved correlation key. A separate
request row may reference it only after an approved decision with matching intent
and account exists. Proposed volume is not an approved broker size. M1 handles
OPEN only; inherited position-action contracts remain unexposed.

Default application service always persists REJECTED/P1_EXECUTION_DISABLED
decisions. APPROVED boundary tests require explicit fixture-only construction,
an explicit database path and FIXTURE account. Requests produced there are
immutable FIXTURE / RECORDED_NOT_SUBMITTED records, never broker authorization.
This is the owner's permitted test-only boundary, not P2 risk logic. Historical,
screenshot and unqualified strategy signals cannot produce requests even in the
fixture boundary. No API accepts user-authored approvals. No default account is
invented: an unbound app can store/trace sources and signals but cannot create
account-bound intents. Tests inject synthetic account identifiers only.

HALT remains effective: no submission path, dispatcher, reset endpoint or broker
calls are introduced. All new HTTP paths use the existing token dependency and
return explicit execution-disabled/research status. Full safety/freshness (initial
configurable 600 seconds), risk allocation and demo attestation remain P2/P3/P4.

## Exact Proposed Files

Modify:
- `backend/core/rebuild/application.py`: compose service, restricted routes/write allowlist.
- `backend/core/rebuild/ledger.py`: version-aware signal/intent revalidation and
  explicit INSERT columns; preserve legacy replay payloads and methods.
- `backend/tests/test_phase2_integrity.py`: expect additive migration 003 while
  preserving migration-1/2 payload/HALT assertions.
- `knowledge/CURRENT-STATE.md`, `knowledge/ROADMAP.md`, `knowledge/TESTING.md`,
  `knowledge/RISKS.md`, this map: evidence and bounded milestone state.
- Documentation-only completion follow-up also updates `knowledge/ARCHITECTURE.md`,
  `knowledge/PROJECT.md` and `knowledge/00-DASHBOARD.md` so current composition and
  phase summaries do not continue saying P1 has not started. No ADR change.

New:
- `backend/core/rebuild/lifecycle_contracts.py`: versioned source/signal/intent,
  decision and request contracts.
- `backend/core/rebuild/lifecycle_service.py`: transactional persistence and trace.
- `backend/core/rebuild/lifecycle_routes.py`: authenticated non-executing adapter.
- `backend/core/rebuild/migrations/003_canonical_foundation.sql`: additive schema.
- `backend/tests/test_p1_lifecycle.py`: fixture, fault, SQL and HTTP invariants.

Explicitly excluded: `backend/main.py`, `backend/legacy_application.py`,
`backend/core/orchestrator.py`, all `backend/agents/*.py`, broker adapters,
learning stores/models, archive ingestion, frontend, active env/private paths,
and applied migrations 001/002. No dependency, credential or infrastructure change.

## Risks and Test Plan

- SQL constraints: source/signal/intent/decision/request mismatch must fail;
  request requires APPROVED with same intent/account/client key; immutable IDs.
- Replay: duplicate event/signal/intent/decision/request, conflicting IDs,
  independent same-symbol signals, retry/reopen and concurrent request creation.
- Input: malformed action/direction, NaN/Inf, invalid geometry, missing/naive time,
  conflicting source evidence, research/strategy ineligibility and unbound account.
- Transactions: injected failure after INSERT before audit must roll back the
  operation; dependent creation failure cannot orphan a request. Migration failure
  rolls back; v1 data and old checksums retained; no live database opened.
- API: unauthorized requests fail, default decisions reject, no approval injection,
  no broker/legacy imports, HALT/execution-disabled status remains truthful.
- Trace: causal IDs and original timestamp/timezone survive restart; absent broker
  evidence/outcome explicitly empty, never synthesized.
- Re-run all four allowlisted ledger/parser/restore modules plus new tests.
  Review additional pure parser/archive tests before broader collection; do not
  import credential-reading runtime, train models or erase historical failures.

No material architecture replacement or deferred ADR semantics are proposed.
If implementation shows evidence-loss risk or requires a new policy, stop rather
than silently revising this plan. P1 as a whole must not be marked complete.

## Implementation and Verification Result

**M1 foundation implemented and fixture-verified; P1 overall remains IN_PROGRESS.**
Implementation commit: `266e7bb6877c2f184f77bd861de046819f43643e`
(`NexusAI V2 P1 M1 canonical lifecycle foundation`), parent
`386e512347bd022d8cbd0c5a79649d25ca5b3fdc`. This evidence-reference update is
documentation-only and follows that implementation commit; no P0 history rewrite
or remote push occurred.

Implemented the proposed files without changing applied migrations 001/002,
parser logic, legacy code, main startup, dependencies, frontend or credentials.
Migration 003 is additive and exercised on temporary databases only. It preserves
v1 payloads/source labels, HALT and checksums; no old record gets inferred source
events or fabricated safety approvals. No parallel signal/intent/safety tables.

Proven chain: immutable Source Event -> signal.v2 (deterministically validated)
-> intent.v2 OPEN proposal -> persisted decision with reason/explanation/policy
version -> FIXTURE / RECORDED_NOT_SUBMITTED execution request. Every link has
exact IDs. Source raw timestamp/timezone, sender, metadata and first receipt
survive replay/reopen; same-symbol independent events remain separate.

The existing client_order_id is a preallocated correlation/idempotency key, not
an authorization. SQL and service checks require a matching approved fixture
decision/account/intent before a request row exists, and a rejection cannot be
overridden. The request ID and one-request-per-intent constraints prevent retry
duplication. Requests/decisions/source evidence are immutable. Transaction/audit
failure rolls back each creation; process death inside the request transaction
rolls back, and death after commit retains one request for deterministic replay.

The active factory composes LifecycleService. Six authenticated paths under
`/api/core/lifecycle` allow source storage, signal validation, intent proposals,
default rejection evaluation, request boundary checks and exact source traces.
No HTTP path accepts APPROVED decisions. Default requests are disabled. Explicit
fixture composition uses a supplied fixture account and database path; requests
there remain fixture evidence, never eligible for broker submission. The default
unbound app can persist sources/signals, but intent creation fails closed until
an account is explicitly supplied; no real account binding workflow was added.

Trace returns existing broker/order/position/outcome link collections, empty in
the new foundation tests. No broker evidence or outcome is manufactured. Old
observation fixtures continue to pass, but **a new-source-to-attested-broker-to-
verified-outcome chain is not proven**. The fixture-only gate does not evaluate
P2 R:R, drawdown, exposure, freshness or sizing and must not be presented as P2.

### Test Evidence

- Before source edits: 105 passed / 89 warnings / 13.98s, guarded allowlist.
- First M1 + existing allowlist: 157 passed / 343 warnings / 18.83s.
- Review then found a concurrent default-rejection retry could conflict solely
  because each attempt generated a different decision timestamp. Fixed this
  without overwriting first evidence; added a concurrent retry regression and
  process-crash tests. No earlier failed test run is being hidden.
- Expanded guarded run: **179 passed / 430 warnings / 15.76s**; parent sensitive
  access attempts 0; main/legacy_application/MT5/agents modules loaded: none.
- The same seven-module command was also run directly in a credential-free
  disposable process; final output is recorded in TESTING.md.
- Source-reviewed child fixtures inherit the credential-free environment; the
  parent audit hook is not an OS sandbox and is not inherited by child processes.
- Warnings are FastAPI/Starlette asyncio-inspection deprecations, not suppressed.
- Historical full-suite **169 passed / 1 failed / 296 warnings** is retained.
  Passing archive tests here do not close the known repackaging/idempotency gap.
  Blanket legacy collection and training tests were not run because they are
  outside the reviewed credential-free scope and can load runtime configuration.

Exact reproducible selection and fixture limits: `../TESTING.md`.

### Git and Secret Exclusion Checkpoint

Exactly 16 intended source/test/governance paths were staged in the implementation
commit. Before commit, all 133 index blobs, 181 content bodies from 226 local Git
objects, and the 16 working files were safely screened for recognizable provider
tokens, private-key headers and nearby named 32-hex credential patterns. Zero
findings; no matched values printed and no active credential contents loaded.
This is bounded pattern screening, not exhaustive arbitrary-secret detection or
proof of remote cleanup/provider revocation.

Explicit `.env`, private token and future private WhatsApp-session path probes
remained ignored/untracked; `.env.example` remains tracked. Applied migrations
001/002, main/legacy startup, orchestrator/agents and all ADRs were compared with
the P0 baseline using `git diff --exit-code`: exit 0. No deletion occurred.
Whitespace check passed with intentional Markdown hard-break whitespace allowed.
No custom commit hooks were present/configured; signing was disabled for the
command to avoid private signing-key access. Pre-existing README_SETUP.md was
not staged, modified or removed. No actual credential-file equality scan was
attempted: the task never read or wrote those files.

### Remaining Scope

Missing: historical-review-to-canonical adapter, reviewed source revision/import
identity integration, ordinary non-fixture account provisioning, P2 safety engine,
real execution requests/dispatch, broker attestation/reconciliation and canonical
verified outcome writer. Unknown: current operator database migration/runtime
state and broker/provider state (not inspected or connected).

Deferred: account/execution boundary to P2/P3, source/freshness adapters to later
P1/P4 work, archive semantic cleanup separately, model/tournament semantics to
ADR-005/006. No legacy component reconnected, no economic action, no training.

Next narrowly scoped P1 milestone: bridge an explicitly approved historical
review record into source/signal lineage with retry/restart and provenance tests,
while keeping that source permanently non-executing. Start with source/store
mapping; do not silently resolve archive identity or cross-database atomicity.

## P1-M2 Design Before Source Changes (2026-09-10)

Baseline: d843255f34af6e46bd72a7be44010d3e9667c156. Fresh reviewed
seven-module baseline: 179 passed, 430 warnings; sensitive-access attempts 0.
This section records the proposed design, not implemented evidence.

### Current Historical Flow

ZIP/TXT -> ChatImportService -> archive.sqlite3 imports/messages -> classify /
SignalParser -> ready / needs_review -> optional reviewer approval -> separate
TraderLearningStore with NOT_APPLICABLE execution and UNVERIFIED outcome.
Approval means historical review acceptance, never economic permission.

VERIFIED_REUSABLE: archive validation, bounded pagination, correction evidence,
parser, historical approval semantics (existing tests pass).
REUSABLE_WITH_FIX: container-only identity, dropped identical message occurrences,
implicit time defaults, raw TXT retention, historical canonical intent eligibility.
MISSING: canonical historical relationship and recoverable promotion state.
LEGACY_DO_NOT_CONNECT: agents, broker adapter, live ingestion, training/outcomes.
UNKNOWN: operator database contents/runtime state; these will not be inspected.

### Target Canonical Historical Flow

archive_hash + import_id -> versioned transcript_fingerprint -> exact message
identity + occurrence -> stable source_event_id -> stable signal_id -> historical
link row containing import/message provenance and observed review snapshot.
The graph stops at validated historical evidence. Execution eligibility is NONE.

Keep imports/messages in their existing archive store. Add metadata/payload fields
without rewriting earlier evidence. Preserve original ZIP and TXT bytes. Normalize
only BOM decoding and line endings for transcript identity; no fuzzy merging.
Keep different containers as separate imports, duplicate_of linking the earliest
same-group transcript import. Exact replay is idempotent. Message identity uses
source group, original local timestamp, sender, exact normalized body, occurrence;
ZIP packaging and time interpretation do not create new canonical observations.
Conflicting evidence for an existing identity fails closed, requiring revision.

Legacy review date defaults remain compatibility-only estimates. New metadata
records whether BOTH date order and UTC offset were explicitly supplied. Only
that evidence is eligible for canonical UTC; absent/legacy evidence stays unresolved.
No timezone is inferred from the laptop, phone, source country or group name.

### Ownership and Failure Boundaries

Archive writes serialize in an archive SQLite transaction. Canonical ownership
remains Ledger and migration_runner. Add migration 004 for historical_links:
the existing schema cannot express many archive occurrences linked to one source
and signal or preserve a failed promotion checkpoint. Never edit 001/002/003.
No distributed transaction is claimed. Read an archive snapshot, record PENDING,
persist source, record SOURCE_ONLY, validate signal, then record VALIDATED.
Only existing exact foreign-key lineage may be reported successful. Retry uses
the same IDs after interruption, with audit events for changed review snapshots.
Missing/invalid evidence records REVIEW_REQUIRED; technical failures remain
recoverable checkpoints. Historical corrections remain separate evidence and
are not mislabelled as deterministic parser output. Their canonical revision
semantics are deferred; do not promote a conflicting corrected projection.

HISTORICAL_WHATSAPP / SCREENSHOT are blocked at canonical intent creation,
including legacy request wrappers around V2 signals, and approved safety decision
creation. Add database guards for those sources, retaining pre-existing rows.
No fixture bypass. Existing V1 isolated observation fixtures are not reconnected.

### Proposed Files and Tests

Modify chat_import_service/routes, rebuild application/lifecycle_service/ledger;
add historical_canonical_bridge and migration 004. Add focused M2 tests; strengthen
M1 historical intent expectations and migration-count expectations. Repair the
known ZIP replay test to replay identical bytes and add deterministic repack tests
instead of relying on ZIP wall-clock timestamps. Preserve its historical failure.
Test archive/message identity, raw evidence, explicit/unknown time, approval
separation, malformed/corrected material, SQL/service firewall, concurrent replay,
fault recovery, authenticated routes, representative pre-004 migration, and all
seven reviewed regression modules. Temporary databases only. No credentials,
operator migration, browser/broker connection, outcomes, training or P2 work.

## P1-M2 Implementation and Closeout Evidence

Status: **PARTIAL**. Implementation and bounded fixture gates pass. The isolation
incident below prevents an unqualified M2 completion claim. P1 IN_PROGRESS.

### Implemented Lineage

- `archive_hash = sha256(original container bytes)`; ZIP and TXT originals retained.
- `import_id = sha256(bytes + encoded date_order:utc_offset:group:confirmed)`.
  Existing old-format import IDs are checked first on replay and left unchanged.
- `transcript_fingerprint = sha256(UTF-8-sig decoded transcript with CRLF/CR -> LF)`.
  Same-group matching fingerprints link `duplicate_of` to the earliest import.
  Container differences do not establish new underlying observations.
- New message ID: SHA256 of JSON `[historical-message.v1, group,
  original_timestamp, raw_sender, raw_body, occurrence]`, ensure_ascii=False.
  This replaces the old stripped-body identity for NEW imports only; stored legacy
  IDs/approvals are not rewritten. Exact repeated occurrences are retained, and
  whitespace-distinct records do not merge. No inferred cross-export fuzzy match.
- `source_event_id = hist- + hashed([historical-source.v1, historical_message_id])`.
- `signal_id = hashed([source_event_id, signal.v2, PARSER_VERSION])`, reusing M1.
- `historical_links(import_id,message_id)` -> canonical source_event_id -> signal_id,
  with archive/transcript/message IDs, checkpoint, reason and observed review JSON.
  Multiple imports can point to one canonical pair. Exact source/signal FKs and
  historical source/message checks enforce the canonical side of this relationship.
  The separate archive database cannot supply a cross-database SQLite FK.

SourceEvent retains raw body, raw timestamp label, raw sender, explicit time
profile, normalized UTC when legitimate, and parser/identity versions. Complete
raw record/header is retained in archive payload and link snapshot. Original
container bytes preserve exact file-level evidence. Canonical parser reuses the
historical text normalizer and deterministic SignalParser; raw source hash always
hashes original message body, never transformed parser input.

### Review and Recovery

POST/GET `/api/private/chat-imports/{import_id}/messages/{message_id}/canonical`
uses the existing authenticated router. The active factory accepts an injected
historical service factory for fully isolated tests. Promotion is explicit, not
automatic on upload or approval, and never invokes learning training or execution.

Archive import insertion and duplicate selection serialize together. Canonical
promotion records PENDING before source writes, SOURCE_ONLY after source commit,
then VALIDATED only after signal commit. Technical exceptions retain the checkpoint;
same-ID retry completes without duplicate observations. Validation/evidence conflicts
produce REVIEW_REQUIRED. Audit entries retain prior review snapshots. An interrupted
final checkpoint may leave a real signal plus SOURCE_ONLY; retry repairs the link.
There is no distributed transaction or automatic background recovery worker.

Historical approved remains historical acceptance, with learning execution
NOT_APPLICABLE and outcome UNVERIFIED. It never writes SafetyDecision.APPROVED.
Changed/corrected prices are not relabelled deterministic parser results. If an
earlier canonical signal exists it is retained, while the current snapshot becomes
REVIEW_REQUIRED. Snapshot review state is observed at promotion, not guaranteed to
reflect a later concurrent archive review. Re-promote to record later evidence.

Legacy imports lacking raw/version/time provenance remain reviewable but are not
automatically backfilled. Their exact replay returns original metadata. A changed
time profile for an already recorded source conflicts rather than rewriting time
or creating an independent observation. Fixed offsets do not infer DST/IANA zones.
Screenshots have no new OCR/image bridge; their existing canonical source type is
firewalled by the same tests. No screenshot-derived timestamp/price is invented.

### Execution Firewall / Schema

Ledger rejects historical canonical signals before returning/reusing any intent,
including an old IntentRequest wrapper. Canonical service rejects execution approval
and requests for pre-existing historical intents as well. Migration 004 additionally
blocks historical intent, approved decision, broker-order and position INSERTs.
M1 request SQL guard still excludes historical sources. Historical fixture mode
does not bypass any of these rules. V1 observation libraries remain isolated;
existing rows are preserved, not reclassified, reactivated or retroactively erased.

Migration `004_historical_lineage.sql` alone adds historical_links and guards.
Representative pre-004 source/signal/intent/account/halt rows and checksums survive
migration; foreign_key_check/integrity_check pass in fixtures. 001/002/003, accepted
and deferred ADRs, startup/legacy agents and broker source were not modified.

### Test Evidence and Isolation Incident

Fresh pre-change selection: 179 passed / 430 warnings / 22.96s.
First M2 run: 23 passed / 2 failed / 78 warnings / 7.96s; two legacy-wrapper fixtures
omitted required action. Corrected: 25 passed / 78 warnings / 6.96s.
Expanded focused M2: 31 passed / 78 warnings / 10.61s.
Initial combined: 204 passed / 564 warnings / 23.91s.
Expanded combined: 210 passed / 564 warnings / 21.86s; direct command also passed
210 / 564 / 19.09s. **These earlier runs do not establish operator DB isolation.**

Review discovered an existing test mocked ChatImportService while still evaluating
`TraderLearningStore()` as an argument. That default constructor opens
`backend/data/private_trader_learning.sqlite3` and runs schema CREATE IF NOT EXISTS.
The discarded default instance does not receive the test's signal inserts or data
SELECTs, but actual schema/file effects are UNKNOWN without a prior snapshot.
The original file-open hook did not intercept SQLite connections. Earlier claims
of no operator-database access are expressly withdrawn. No operator DB was opened
for investigation, no repair/rollback was attempted, and migration 004 was never
run against an operator DB. This incident also limits reliance on earlier M1
blanket operator-isolation claims for the same route test.

The route test now injects a complete temporary service, with a failing sentinel
for default learning-store construction. The final guard checks sqlite3.connect,
Python file access including Path objects, active .env/private and backend/data.
First corrected run: **210 passed / 564 warnings / 24.87s**. After also removing
learning-store construction from the new canonical routes and adding its negative
constructor test, final corrected run: **211 passed / 640 warnings / 26.41s**,
zero sensitive/operator
access attempts, no main/legacy_application/MetaTrader5/agents modules loaded.
Parent hooks do not propagate into subprocesses; existing crash workers were
source-reviewed, inherit a scrubbed environment and use explicit temporary DBs.
Exact command/guard and qualification limits are recorded in TESTING.md.

The older full-suite 169 passed / 1 failed / 296 warnings remains historical evidence.
The particular ZIP timestamp-dependent replay fixture now reuses identical bytes;
separate deterministic ZIP-metadata/compression tests prove the new repack contract.
No full legacy-suite/training run is claimed. Warnings are dependency deprecations.

### Changed Files and Remaining Gate

Changed: backend/core/rebuild/{application.py,ledger.py,lifecycle_service.py};
backend/services/{chat_import_service.py,chat_import_routes.py};
backend/tests/{test_chat_import_service.py,test_p1_lifecycle.py,test_phase2_integrity.py};
knowledge/{CURRENT-STATE.md,ROADMAP.md,TESTING.md,RISKS.md}; this map.
Added: backend/core/rebuild/migrations/004_historical_lineage.sql;
backend/services/historical_canonical_bridge.py;
backend/tests/test_p1_historical_bridge.py.
Pre-existing untracked README_SETUP.md is unrelated and untouched.

Minimum closeout action: owner disposition of the documented isolation incident,
or separately authorized limited operator-impact review if suitable prior evidence
exists. No before/after snapshot can be fabricated. M2 is PARTIAL pending that
disposition; do not start P2. No credential, broker, WhatsApp, training or legacy-agent
access is needed for corrected fixture verification. No push is authorized.
No claim of profitability, outcomes, TP-before-SL, live data, strategy quality,
ML readiness, risk-engine correctness, broker execution or reconciliation is made.

### Pre-Commit Git Checks

Branch core-rebuild; HEAD includes the exact M1 evidence baseline. Protected source,
migrations 001/002/003, V2 specification, AGENTS and ADR diff: exit 0. No tracked
file deletion. Secret-pattern scan: 185 local Git blob/commit/tag objects plus
16 changed/new task files, zero findings; only object/path/rule metadata is emitted.
This is pattern coverage, not provider revocation or proof of every possible secret.
Tracking-name checks returned only backend/.env.example; named active .env/private
paths are ignored. Credential contents were not read. Git fsck --full --strict and
diff whitespace checks passed. No custom Git hooks were found/configured. Signing
is disabled for the task commit to avoid private signing-key access. No push.

### Post-Commit Recovery Evidence

M2 implementation commit: `eb58df9ebf092b76fc14368f21027fa20d7aab1a`.
The M1 evidence baseline is an ancestor (merge-base --is-ancestor exit 0).
Post-commit git fsck --full --strict passed. The implementation commit contains
exactly the 16 task files listed above; no deletions or operator DB files.
Tracked working tree/index were clean; only the pre-existing untracked
README_SETUP.md remained. This documentation follow-up records the actual hash
without amending M1, P0 or the M2 implementation commit. M2 stays PARTIAL because
the earlier operator-storage isolation incident remains unresolved, despite
passing final fixture tests. No push or P2 work was performed.
