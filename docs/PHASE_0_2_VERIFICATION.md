# Phases 0-2 Acceptance Report

Date: 8 September 2026. Scope: the first three phases, numbered 0, 1 and 2, of
`D:/project/NEXUSAI_REBUILD_MASTER_PLAN.md`. No Phase 3 risk or Phase 4 broker execution was activated.

## Result

The local software/evidence acceptance gates pass. This does not mean all security operations are
finished, nor that trading is ready. News-key rotation and off-device backup require external action.
Live broker reconciliation, economic-action idempotency and P&L accounting remain later gates.

## Phase 0: Preserve, Version, Freeze

| Requirement | Verification |
|---|---|
| Recoverable source baseline | Existing `ef0ddce`, tag `nexusai-forensic-baseline-2026-09-08`, branch `core-rebuild` retained |
| Restore actual evidence | Restored 93 files to a new directory; verified all file hashes, six SQLite integrity checks and logical-content hashes |
| Archive BLOB/media recoverable | Stored ZIP passed CRC validation; original images/archive/text/corrections/IDs preserved |
| Baseline tests run | 65 tests passed from the restored source, excluding the two forbidden training tests |
| Preserve before next migration | Additional snapshot `20260908T160427Z` verified six old DBs plus the lifecycle DB before migration 002 |
| No real-money path | Default application starts no agents or broker adapter; execution routes stay locked; mode changes do not unlock them |
| Config inventory | Configured mode/allowlist recorded privately; not mistaken for actual broker account attestation |

The restored source is at `D:/quant project/rebuild_backups/restore-drill-20260908-phase0`.
Private machine-readable evidence: `backend/data/lifecycle/phase0_verification.json`.
All six original DB logical-content hashes were rechecked after tests and remain unchanged.

Closeout rerun: `backend/data/lifecycle/phase0_closeout_verification.json` verifies a
fresh restore at `D:/quant project/rebuild_backups/restore-drill-phase0-closeout-20260908`.
All 93 files, six databases and the embedded archive passed again. The verifier now
rejects escaping/unlisted/duplicate database paths before copying, and reports archive
verification only when an archive was actually checked. Ten preservation regression
tests cover these failures, tampered hashes, and refusal to overwrite a destination.

### Security Finding

The scan covered every locally present Git object, including unreachable objects, in three repositories:

- Authoritative `files`: 137 objects at scan time; no configured-secret/private-key-pattern matches.
- `github-files`: 57 objects; two matching historical blobs.
- `github-sync-Multi-Agent-Trading-Simulator`: 186 objects; the same two matching historical blobs.

Triage confirmed that `NEWS_API_KEY` appears in two versions of `backend/VERIFICATION_REPORT.md`, line 229.
No secret value is included in this report. No broker password or other matched secret was reported by this scan.
This is a known-value and private-key-pattern scan, not proof that every conceivable secret is absent.
Remote repositories were not fetched, changed, force-pushed or certified safe.

Operator actions:

1. Revoke/rotate the exposed news API key at its provider and replace the local setting privately.
2. Arrange explicitly approved remote-history cleanup if these report versions were published.
3. Keep an encrypted off-device copy of the verified backup. Local read-only files are not WORM storage.

These findings were not hidden or erased to produce a passing report.

## Phase 1: Parser And Signal Integrity

Components: `services/signal_parser.py`, `core/rebuild/contracts.py`, historical review service.

- Parser v3 preserves `TP 120`, `TP 2400`, `TP1 2400`, `TP1:2400`, integer/decimal and multi-slot values.
- Numeric fragments, malformed duplicate fields, NaN/Inf, signs separated from numbers, bad slots,
  unsupported ranges, conflicting directions, cancellation text and invalid requested risk are rejected.
- Bounded source text and nonblank source identifiers prevent unbounded or anonymous core records.
- Frozen versioned contracts retain source/receipt/parse time, hash, identity, symbol, direction and levels.
- Missing origin time does not become valid through a receipt-time fallback.
- Repeated parse with identical source metadata is deterministic; valid arrival retries retain the first stored timestamps.
- The generated TP matrix covers 90 price/slot/separator/direction combinations in addition to explicit regressions.
- Historical comparison covers 784 messages: 59 validation/price review flags, two numeric-field differences.
  Original records and manual corrections remain unchanged. No automatic historical approval or training occurred.

Tests: `test_phase1_integrity.py`, `test_signal_parser.py`, parser cases in `test_rebuild_core.py`,
and historical review regression tests. Unsupported inputs remain review-only; this is a bounded grammar,
not a claim that every possible chat format is supported.

## Phase 2: Durable Identity And Ledger

Components: `core/rebuild/ledger.py`, `migration_runner.py`, SQL migrations 001 and 002.

| Requirement | Implementation / test evidence |
|---|---|
| Account-scoped identity | One immutable demo-account binding per DB; other-account evidence and unbound economic writes rejected |
| Durable source and request | Typed validation plus immutable source/intent payloads, source metadata columns and request price/volume columns |
| Exact ownership | Broker order -> client key -> intent -> signal; broker position -> opening intent; close deal retains both closing and original source lineage |
| Replay safety | Duplicate keys return persisted identity; changed payload/new key for same logical request rejected; duplicate evidence creates no extra economic rows |
| Partial and multiple deals | Multiple deal IDs, cumulative volume ceilings and explicit broker position snapshots; two Gold positions and opposite directions tested |
| Out-of-order evidence | Unknown-order deals quarantined; immutable promotion/replay; older snapshots cannot overwrite newer quantities |
| State persistence | PLACED/PARTIALLY_FILLED/FILLED observations update persisted intent state; terminal states cannot reopen |
| Crash recovery of storage | Abrupt `os._exit` after signal, intent, order, deal, position and within an uncommitted transaction; replay restores exactly one lineage |
| Process races | Four independent competing processes retain one signal/intent/order/deal/position identity |
| Non-destructive migrations | Version-1 payload and halt preserved, migration reruns idempotent, recorded checksum drift and unsupported version history rejected |
| Do not invent outcomes | Zero-volume snapshots require further reconciliation; no authoritative CLOSED or P&L outcome is generated here |

Tests: `test_phase2_integrity.py`, `test_rebuild_core.py`; subprocess fixture `ledger_crash_worker.py`.
Order/deal evidence is synthetic fixture evidence, never advertised as actual MT5 activity.

The operating review application is deliberately unbound to a broker account and contains no imported
fixture trades. The account adapter's actual attestation, risk approval, broker send/retry logic and final
outcome calculation are not smuggled into Phase 2. Risk/outcome tables are storage contracts, not implemented
policy/accounting engines. Netting and multi-origin position allocation remain fail-closed unsupported cases.

## Final Checks

- 170 backend tests passed; two model-training tests intentionally excluded.
- Restored-baseline run: 65 passed.
- Local app migration: versions 1 and 2, SQLite integrity `ok`.
- Authenticated status: `HALTED`, zero running agents, execution false, no account binding.
- Screenshot submit, model train and halt reset remain HTTP 423; unauthenticated access remains denied.
- Frontend build passed; desktop (1440x1000) and mobile (390x844) checks passed with no overflow or JavaScript errors, and archive images loaded.
- No broker orders, position modifications, model training, GitHub pushes or destructive history edits.

The remaining operator actions and later-phase prerequisites are collected in
[Operator Requirements](OPERATOR_REQUIREMENTS.md). No new API credential is needed
for the local Phase 0-2 implementation or its tests.

Next authorized development milestone: Phase 3 universal policy/halt/risk authority and atomic reservations.
