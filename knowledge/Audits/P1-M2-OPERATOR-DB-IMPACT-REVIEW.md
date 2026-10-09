# P1-M2 Operator Database Impact Review

## Subsequent Human Disposition (2026-09-10)

Following evidence commit `f32eb2b3cc426350b18f3f2a44890c9e75afd991`, the owner
explicitly accepted M2 as **COMPLETE_WITH_RECORDED_INCIDENT**. Reasons: matching
pre-incident database hash, integrity ok, no net schema/data change, unchanged
size/mtime and proven isolation within tested scope. Remaining unmeasured
filesystem access-time effects are accepted. No repair or database modification
is authorized. The original forensic classification and historical PARTIAL
recommendation below are preserved; acceptance does not manufacture new evidence.

Date: 2026-09-10. Repository: `D:/project`, branch `core-rebuild`.
Review baseline: `f2eccbdd60cbdbc3a49651002e25ec4aa894426f`.
M2 implementation: `eb58df9ebf092b76fc14368f21027fa20d7aab1a` (the shorter
implementation identifier in the request resolves to this commit).
Pre-fix reference: `d843255f34af6e46bd72a7be44010d3e9667c156`.

## Verdict and Scope

**Incident classification: IMPACT_UNVERIFIED. M2 disposition: PARTIAL.**

The uncertainty has narrowed materially: **the stored SQLite file, including its
schema, records and header, is byte-identical to a dated pre-incident hash**.
Its size and modification time also match the prior audit. This is evidence of
no net durable SQLite schema/data/header change, not merely a passing current test.

The overall classification remains conservative because the requested scope also
includes filesystem timestamps and other side effects of opening a database.
There is no pre-incident last-access-time baseline or complete incident connection /
filesystem trace. This review itself observed the OS updating last-access time
during read-only inspection. Therefore do not claim that every filesystem metadata
effect of the earlier incident is proven absent. No durable SQLite data damage is
identified, and no database repair is recommended. Human disposition of this narrow
remaining uncertainty is required; no new implementation milestone is authorized.

This is NOT a finding that research records were corrupted. It is also not an
assertion that NTFS last-access metadata is part of SQLite's stored application data.
The distinction explains why the database-specific answers below can be NO while
the wider incident classification remains UNVERIFIED under the requested categories.

## Exact Affected Database

`D:/project/backend/data/private_trader_learning.sqlite3`

The default is calculated from the source module, not environment variables:
`backend/services/trader_learning_store.py:13`, `:22`, `:27`, `:32`.
It is not the canonical lifecycle database and does not contain migration 004.
No credential files, WhatsApp sessions or broker accounts were inspected.

### Read-Only Method

Inspected only this exact database and one manifest-identified copy of it.
No application startup or store constructor was used on either real file.
Before SQLite inspection, explicit `-wal`, `-shm` and `-journal` probes were absent.
Each connection used `Path.as_uri() + '?mode=ro&immutable=1'`, `uri=True`.
A connection authorizer allowed SELECT/READ/FUNCTION and an explicit getter-only
PRAGMA list, denying other SQL actions. No assignments, checkpoint, VACUUM, schema
initialization, migration, ATTACH, repair or test DML ran on these files.

Queries were sqlite_schema enumeration; COUNT(*) for the four known tables;
name/sequence inspection of sqlite_sequence; schema_version, user_version,
application_id, journal_mode, page_count, page_size, freelist_count, encoding,
integrity_check and foreign_key_check. No raw chat, signal payload, account or
credential values were printed. Original bytes were read only for hashing and
binary comparison; no new copy of the operator database was written.

SQLite immutable mode skips locking/change detection, so the review checked
hash/size/mtime and sidecar presence before and after. They were stable. This is
a stable observation window, not an assertion that the operator file is permanently
immutable or a guarantee against an undetected external concurrent change.
See [SQLite URI semantics](https://www.sqlite.org/uri.html) and
[SQLite read-only WAL behavior](https://www.sqlite.org/wal.html#read_only_databases).

## Filesystem and SQLite Findings

Observed at `2026-09-10T11:22:37.902255+00:00`, runtime SQLite 3.50.4:

| Property | Finding |
|---|---|
| File exists | YES; also independently recorded before M2 |
| Size | 40,960 bytes |
| Creation time UTC | 2026-09-01T15:22:09.7094807Z; corroborative, not sole historical proof |
| Modification time UTC | 2026-09-07T18:18:04.1600301Z; matches September 9 inventory |
| SHA-256 before/after | b770177c83e5b6885d8b19eee438ec3facac8c514c13012ac07717d7522b546e |
| SQLite journal mode | delete; header read/write versions both 1 |
| schema_version / schema cookie | 6 |
| user_version / application_id | 0 / 0 |
| File-change counter / version-valid-for | 11 / 11 |
| Schema format | 4 |
| Page count / page size / freelist | 10 / 4096 / 0 |
| Encoding | UTF-8 |
| integrity_check | ok |
| foreign_key_check | No rows; not proof of trading/learning semantics |
| WAL / SHM / rollback journal | All absent before and after inspection |
| Migration/version tables | No schema_migrations or migration_checksums table |
| Triggers / views | None |
| sqlite_sequence | Empty; no sequence allocations present |

Tables and row counts:

| Table | Rows |
|---|---:|
| trader_signals | 2 |
| trader_execution_events | 0 |
| trader_shadow_predictions | 0 |
| sqlite_sequence | 0 |

Indexes: idx_trader_signals_symbol_direction, idx_trader_signals_updated_at,
idx_trader_predictions_created_at, sqlite_autoindex_trader_signals_1,
sqlite_autoindex_trader_shadow_predictions_1. The operator trader_signals schema
still has its earlier source default 'whatsapp', whereas current source proposes
'private_signal' in CREATE TABLE IF NOT EXISTS. The constructor did not rewrite
the existing table definition. This is historical schema compatibility evidence,
not permission to migrate or normalize it during this review.

### Filesystem Access-Time Caveat

Before this inspection, last-access UTC was `2026-09-10T07:51:34.0335465Z`.
After the first read-only inspection it was `2026-09-10T11:22:37.880995Z`.
Later hash reads observed another access-time advance. No SetFileTime, timestamp
normalization, SQL write or timestamp restoration was requested or executed.
These are OS-managed read-access metadata changes; file bytes/size/mtime stayed
unchanged. Do not attribute the earlier 07:51 access time exclusively to M2 without
an event trace. Its pre-incident value is unavailable in the reviewed records.

## Historical Evidence and Identity

1. `D:/quant project/audit-2026-09-09/evidence/all_file_hash_baseline.json`
   contains the exact relative path `backend/data/private_trader_learning.sqlite3`
   and the same b770...b546e hash. The evidence file's creation/mtime is
   `2026-09-09T10:21:55.0019755Z`, before the M1/M2 commits on September 10.
   `support_evidence.py:3` fixes ROOT to this repository and `:16` hashes the
   inventoried file bytes. That script was inspected, never executed in this review.
2. The same audit's `file_inventory.json` records 40,960 bytes and modification
   time `2026-09-07T23:18:04.16003+05:00`, equal to the UTC value above.
   `final_integrity.json` at `2026-09-09T10:45:28.126649+00:00` reports no hash or
   initial metadata changes. These records do not contain last-access-time baselines.
3. `D:/quant project/rebuild_backups/20260908T160427Z/manifest.json` identifies
   `backend\\data\\private_trader_learning.sqlite3`, all four matching row counts,
   integrity ok and the backup SHA-256
   `7c4d26a93c74ab7dce66aed2da0eb30e72a1b02b52d7a6cf793fb3cb366ac916`.
   The manifest existed at `2026-09-08T16:04:40.5480486Z`.
4. The matching copy is
   `D:/quant project/rebuild_backups/20260908T160427Z/source/backend/data/private_trader_learning.sqlite3`.
   Its actual hash matches its manifest; size 40,960; integrity ok, same schema,
   indexes, table counts and empty sequence. Its bytes differ from the current
   operator file only at zero-based header offsets 27, 43 and 95. Every byte after
   the first 100 header bytes is identical. Backup counters are 12/7/12 instead
   of operator 11/6/11. Do not misreport this pre-incident copy/header difference
   as damage caused by M2.
5. `D:/quant project/rebuild_tools/preserve.py:9` identifies this repository as
   the backup source; its source code uses the SQLite backup API and verifies
   inventories. It was source-inspected only. It also contains credential-reading
   code elsewhere, so the script was NOT executed and no adjacent secret backups
   were opened. The matching manifest entry and snapshot were inspected selectively.

These are local, dated, mutually corroborating artifacts, not signed/WORM forensic
records. No unknown similarly named sibling database was treated as the operator
database. Other backup directories were listed only at their top level; this review
did not recursively search credential stores or open unrelated database copies.

## Reconstructed Incident Path

At d843255, `backend/tests/test_chat_import_service.py:166` mocked only
`services.chat_import_routes.ChatImportService` with a lambda that ignored keyword
arguments and returned a temporary archive/learning pair. At that same commit,
`backend/services/chat_import_routes.py:25` evaluated
`ChatImportService(learning_store=TraderLearningStore())`. Python evaluates that
argument before invoking the mocked constructor. The resulting default learning
store was discarded, but its initialization had already run.

`TraderLearningStore.__init__` -> parent mkdir(exist_ok=True) -> `_init_schema`
-> `_connect` -> `sqlite3.connect(self.db_path)` -> `executescript`.
The constructor has no migration-runner call, seed method, broker action or
training invocation. Its SQL consists of three CREATE TABLE IF NOT EXISTS and
three CREATE INDEX IF NOT EXISTS statements. No ALTER, DROP, user-table INSERT,
UPDATE, DELETE or version-setting PRAGMA is present in this path.

The original successful route test invokes the service four times: upload,
message list, historical approval and missing-message lookup. This implies four
default constructor executions and 24 DDL statement attempts per complete run.
Invalid pagination and rejected access fail before service construction. The
number of historical process-wide repetitions is not established by a syscall log.
The learning approval operation itself receives the temporary injected store,
not the eagerly evaluated and discarded default instance.

| Required question | Evidence-based answer |
|---|---|
| Was the database opened? | YES, reconstructed from the passing pre-fix test and eager argument path; not a retained syscall trace. |
| Read-only or read-write? | Normal sqlite3.connect(path), no URI mode=ro; read-write/create-capable. |
| Automatic table creation? | Yes if missing; existing tables make IF NOT EXISTS a no-op. Actual file/schema already existed. |
| Automatic migrations? | No versioned migrations; only the six schema-ensure DDL statements. |
| Connection establishment writes? | Can create an absent file; immediately followed by write-capable initialization. This is not a read-only API. |
| Test user-row DML against default store? | No such call in the reconstructed path; historical approval writes to tmp_path/learning.db. Whole-file hash corroborates no net operator row change. |
| Teardown writes? | TestClient teardown has no learning-store writer; conftest reset_event_bus only resets an in-memory variable. SQLite connection context manager handles transactions, not explicit application DML. |
| WAL/SHM merely from connection mode? | Possible for a database already using WAL, depending on connection/state. Source never enables WAL; this file's pre/post header and current journal mode are rollback/delete. Historical transient sidecar absence is not established by current absence alone. |
| Before assertions? | Yes, service construction occurs before the request result is asserted, including the missing-message failure path. |
| Was a transaction committed? | Missing-schema DDL would commit SQLite schema changes; fixtures demonstrate durable creation. Existing complete schema produces no application DML transaction or net file change in fixtures. Historical COMMIT/lock activity was not traced; do not invent a recorded commit. |

Python's connection context manager commits/rolls back an active transaction but
does not close the connection. executescript has its own documented transaction
behavior. These semantics were checked against the
[Python sqlite3 documentation](https://docs.python.org/3.14/library/sqlite3.html).
No cleanup behavior from the fixture is assumed to be a historical operator trace.

Git evidence: the learning-store source is unchanged across d843255, eb58df9 and
f2eccbd; its history predates M2. eb58df9 changes the route test to whole-service
injection and a default-constructor rejection sentinel. New canonical routes avoid
learning-store construction. f2eccbd is an evidence-only follow-up, not another
application fix. No implementation source was changed during this incident review.

## Impact Matrix

| Effect | Classification / qualification |
|---|---|
| Database creation by M2 | NO; prior audit and identified backup prove existence |
| Net durable schema/index/trigger change | NO; whole-file equality to pre-incident audit |
| Versioned migration / user_version change | NO; no caller and unchanged file/version evidence |
| Net durable user/training row insert/update/delete | NO; exact file equality plus no default-store DML path |
| SQLite header / sequence / application state change | NO net change; full header included in matching hash; sqlite_sequence remains empty |
| File size / mtime change | NO observed change versus the dated audit |
| Current physical integrity affected | NO corruption detected; integrity ok and exact prior file bytes |
| Historical/learning semantic qualification | NOT ESTABLISHED; unchanged legacy data is not verified trading/outcome truth |
| Incident-specific last-access / transient sidecar effects | UNVERIFIED; no before-access baseline or complete event trace |
| Durable database damage requiring repair | None identified; repair/restore would be unjustified on this evidence |

Overall category D, IMPACT_UNVERIFIED, is retained for the wider timestamp/state
question. This does not erase the proven database-specific no-net-change findings.
No evidence supports category C. Category B would require an attributable durable
metadata/schema change, not merely assuming the observed later access-time change
was caused by the earlier incident. Category A would overstate the requested wider
scope without distinguishing the unmeasured filesystem effects.

## Recurrence Prevention

**Current isolation fix: PROVEN within the exercised fixture workflow.**

- Current route test constructs both stores explicitly under tmp_path and injects
  the entire service. The default learning-store sentinel raises if reached.
- New canonical route has no learning-store constructor; its existing negative
  constructor test remains in the regression selection.
- New test-only incident characterization redirects the old default to a synthetic
  tmp_path database before reproducing the old mock. It traces 24 schema-only
  statements, proves creation for an absent fixture, and preserves a pre-existing
  seeded fixture byte-for-byte. No operator path is used in this replay.
- Eight concurrent request workflows across four workers share the injected
  temporary service; exactly one learning example results and all observed SQLite
  paths stay under tmp_path. Default construction is forbidden.
- Factory exception, SQLite exception, missing record and invalid upload retain
  their failure responses; none attempts a fallback default constructor.
- The final test guard intercepts SQLite connects as well as Python file access.
  Review found raw-string-only matching could miss relative/encoded aliases; the
  updated documented test guard resolves paths and decodes local file URIs before
  matching protected paths. Six direct synthetic-event self-checks exercise
  absolute Path, relative paths, URI and percent-encoded forms. They call the guard,
  not sqlite3.connect or open on an operator/secret file.

This is not an OS sandbox or proof about arbitrary future tests, unreviewed native
extensions, adversarial monkeypatching or operator startup. Parent hooks do not
propagate to subprocesses; existing crash workers use explicit temporary paths and
scrubbed environments. No credential-dependent verification is required.

## Remediation and M2 Recommendation

No data restoration, quarantine move, schema migration, timestamp reset, WAL
cleanup or other database remediation is justified by the findings. None was done.
Keep the existing non-execution/unqualified research gates; unchanged records do
not gain outcome or ML eligibility from passing this inspection.

**M2 remains PARTIAL; P1 remains IN_PROGRESS. Next authorized action: HUMAN_REVIEW.**
The minimum decision is whether the proven unchanged database content plus the
recorded, unmeasured read-related filesystem metadata risk is sufficient to accept
the incident. Alternatively supply an attributable prior metadata/event baseline
if available. Do not fabricate one, restore a healthy matching database, or expand
this review into M3/P2. Human incident disposition is distinct from technical repair.

Report/test evidence is to be committed separately; no history rewrite or push.
Implementation, migrations, credentials and operator database files are excluded
from staging. The pre-existing untracked README_SETUP.md remains untouched.

## Verification Run Evidence

Final normalized-guard nine-module selection: **218 passed, 1010 warnings in
36.27s**, exit 0. Six synthetic audit-event self-checks passed; actual sensitive /
operator access attempts during tests: **0**. Forbidden runtime modules: **[]**.
The exact environment-scrubbed command and full guard are retained in
`knowledge/TESTING.md`, section "P1-M2 Incident Review Verification (2026-09-10)".
This adds only the seven incident test cases to the previous 211-test selection.

The first focused run had 2 failures / 5 passes / 366 warnings in 5.39s, caused by
test cleanup closing connections across threads. The test-only cleanup was removed;
7 passed / 366 warnings in 1.56s. Combined results were 218 / 1006 / 29.95s, then
218 / 1010 / 30.19s after adding the fourth old-route service call, then the final
normalized-guard result above. No failed run is being omitted or used as a pass.
No application fix, operator repair or broader phase implementation was performed.

Material documentation updates are limited to CURRENT-STATE, TESTING and RISKS.
The roadmap, accepted/deferred ADRs and existing milestone disposition are unchanged.
The commit containing this report is the separate incident-review evidence commit;
its identifier is reported in the final handoff, avoiding a self-referential hash.

Final post-test file check again matched the pre-incident SHA-256, 40,960 bytes
and `2026-09-07T18:18:04.1600301Z` modification time. WAL/SHM/journal remained absent.
Hashing reads can update OS last-access time; no attempt was made to restore it.
The tracked documentation diff passed `git diff --check`. No custom hooks path
or active non-sample Git hooks were found before the separate evidence commit.
