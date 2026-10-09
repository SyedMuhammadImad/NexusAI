# Controlled Rebuild Status

Date: 8 September 2026. This is a checkpoint, not a declaration that the whole rebuild is finished.

Latest checkpoint: the local acceptance gates for Phases 0, 1 and 2 have passed.
See [Phase 0-2 Verification](PHASE_0_2_VERIFICATION.md) for scope and evidence.
The news API key found in older sibling Git histories still needs provider-side rotation.
Off-device backup and any remote-history remediation remain open operational work.

Specification: `D:/project/NEXUSAI_REBUILD_MASTER_PLAN.md`.
Evidence source: `D:/quant project/audit-2026-09-08/NexusAI_Forensic_Audit.md`.

## Runtime Boundary

The default `main:app` now creates an authenticated review-only application. It does not import
the legacy application, instantiate trading agents, connect to MT5, or start a price/event loop.
The retired application startup raises an error. No environment mode enables trading in the new app.
The new lifecycle database starts `RECOVERY_REQUIRED`; review startup persists `HALTED`.
There is no resume/activation endpoint. Manual halt acknowledges persistence only, not broker closure.

Allowed writes are historical import/correction/approval and persistent halt. All other mutations,
including synthetic backtests, test signals, screenshot submission, model training, broker modification,
and halt reset, return 423 after authentication. WebSocket streaming is disabled, not falsely presented
as a repaired fan-out stream. Public/private GETs require the local control token.

## Preservation

- Source baseline commit: `ef0ddce`.
- Baseline tag: `nexusai-forensic-baseline-2026-09-08`.
- Rebuild branch: `core-rebuild`.
- Local private snapshot: `D:/quant project/rebuild_backups/20260908T112424Z`.
- Six legacy SQLite databases copied using SQLite backup and verified with integrity checks,
  table counts and logical dump hashes, including BLOB contents.
- 93 source/runtime evidence files copied and hashed; dependency/build/cache directories excluded.
- Source, images, archives, logs, configuration, tests, manifests and audit evidence retained.
- Original audit verification backend additionally retained; its inaccessible temporary-directory
  artifacts and generated frontend build are not claimed as preserved primary evidence.
- Snapshot files marked read-only. This is tamper-evident local storage, not immutable off-device storage.
- Configured mode was `exness_demo`; configured trade allowlist was EURUSDm, USOILm, XAUUSDm.
  Those are configuration observations, not a fresh broker-account attestation.
- No remote configured or pushed in this new repository. The current repository object scan found no matching
  configured secrets. The scan of both older sibling object databases found the configured NEWS_API_KEY
  in two versions of `backend/VERIFICATION_REPORT.md`. No secret value was emitted or history rewritten.
  Remote GitHub state was not fetched or verified; rotation/remediation remain operator actions.

| Preserved database | Verified record counts |
|---|---|
| trading.db | 35 trades; 104 equity rows; 5,000 events; 7 weights |
| private_trade_journal.sqlite3 | 4 signals; 3 execution records; 3 alerts |
| private_setup_learning.sqlite3 | 2 setups |
| private_signal_images.sqlite3 | 1 image record |
| private_trader_learning.sqlite3 | 2 signals; 0 execution events; 0 shadow predictions |
| chat_imports/archive.sqlite3 | 1 import; 784 messages; embedded archive retained |

## Implemented Foundation

### Parser and source

`deterministic_v3` separates explicit TP slot numbers from ordinary prices. It rejects missing,
nonpositive, malformed/nonfinite prices, conflicting directions, duplicate fields/TP slots,
invalid geometry and invalid timestamps. `signal.v1` is frozen, carries source/hash/version/timestamps,
and requires explicit origin time. Core parsing does not substitute upload time for origin time.

Historical comparison inspected all 784 messages without editing the archive. The v3 review flags 59
signal records due to price or additional validation differences; only two have changed price fields.
One price difference is an existing manual correction and one is malformed stop-loss formatting.
This is not evidence of 59 corrupted fills or trades. The original v2 report is retained; the new report
is `backend/data/lifecycle/parser_review-v3.json`, excluded from Git. Corrections were not overwritten.

### Lifecycle identity

Versioned schema contains signals, intents, risk decisions, reservations, broker orders/deals,
positions, outcomes, halt state, quarantine and audit events. Signals and deals have immutable
storage guards; audit is append-only. Immediate transactions serialize competing client requests.
Reusing a client key with a different payload fails. A second key cannot duplicate the same source/action/target.
Orders and deals join by explicit IDs. Unknown-order deals are quarantined, not assigned by symbol.
Multiple-origin/netting allocation is deliberately rejected pending explicit support.

The ledger now has immutable per-database demo-account binding, evidence account checks, checksum-verified
migrations, first-receipt preservation, exact position ownership, cumulative deal-volume limits,
idempotent observations and explicit observed order-state transitions. Actual process-crash/replay
and competing-process tests pass. This is an identity/storage layer, not an execution engine.
Universal risk, broker calls, full reconciliation and final outcome accounting remain Phases 3-6.
Zero-volume snapshots never produce CLOSED outcomes. The running review app is intentionally unbound.

### User interface

The old dashboard remains as inactive source. The default workspace shows halt/qualification and
ledger counts, not invented starting equity or inferred P&L. Historical review remains accessible;
private images are fetched with authentication and displayed through temporary object URLs.
Secrets stay in memory in the browser and are not placed in URLs or browser local storage.

## Gates And Remaining Work

| Phase | State | Exit evidence still required |
|---:|---|---|
| 0 | PASS: local preservation/version/freeze gates | Rotate exposed news key; off-device backup and remote-history remediation remain operational follow-ups |
| 1 | PASS: parser and contract gates | Unsupported provider formats stay in review; screenshot execution remains disabled |
| 2 | PASS: account-scoped identity and storage gates | Real broker integration/qualification belongs to subsequent phases; fixture evidence is not broker certification |
| 3 | NOT IMPLEMENTED | Universal halt/policy/risk authority, broker-unit sizing, atomic reservations and independent USD cap |
| 4 | NOT IMPLEMENTED | Durable submission claim, no blind timeout retries, idempotent broker boundary for every action |
| 5 | NOT IMPLEMENTED | Broker-confirmed fills/positions, partial closes, costs and exactly one final outcome |
| 6 | NOT IMPLEMENTED | Read-only startup reconciliation and actual process-crash fault injection at every boundary |
| 7 | BLOCKED FOR RESEARCH USE | Canonical broker timestamp/provenance, bar-quality checks and immutable datasets |
| 8 | BLOCKED BY 7 | Deterministic replay, realistic costs, conservative same-bar fill policy and correct metrics |
| 9 | BLOCKED BY 8 | One explicit versioned strategy, not a voting ensemble |
| 10 | BLOCKED BY 8-9 | Locked chronological development/validation/untouched test and baseline comparisons |
| 11 | DISABLED | Immutable screenshot origin, replay-safe submission and core gates 1-6 |
| 12 | DISABLED / NOT REBUILT | Authenticated, allowlisted, timestamped WhatsApp source; provider/account setup required |
| 13 | BLOCKED BY 8-10 | Independent evidence for expanding from one to three strategies |
| 14 | BLOCKED BY 10,13 | Orchestrator ablation; no unsupported keep/remove decision |
| 15 | BLOCKED | Locked forward MT5 demo qualification with real time and broker-confirmed evidence |
| 16 | DISABLED | Defensible labels, enough samples, validated core/replay/strategy/forward evidence, no-ML baseline |

Do not train a model or enable trading to make the status table look complete.
The next implementation work is Phase 3: universal policy/halt/risk and atomic exposure reservations.

## Verification Scope

- Frozen baseline: 65 existing tests passed, excluding two model-training tests.
- Current regression run: 170 tests passed, excluding those two training tests.
- Restored baseline rerun: 65 tests passed from the restored source tree, not just the working tree.
- Six genuine subprocess crash boundaries and a four-process simultaneous replay were exercised.
- Frontend production build passed.
- Headless Edge/Playwright checked 1440x1000 and 390x844: authenticated login, halted status,
  historical archive, private image decoding, no JavaScript errors and no document-width overflow.
- Screenshots are private local artifacts under `logs/rebuild-*.png`.
- No real or demo broker order, close, modification or model training occurred.
- Existing legacy tests include behaviors the audit found unsafe. Passing them is baseline compatibility,
  not evidence that those inactive agents are safe to reactivate.

Still unverified: MT5 behavior, full event-bus hardening/fan-out, actual broker account attestation,
universal action gating, broker-call crash recovery, dependency security/clean install, load/rate limits,
container deployment, real historical replay, out-of-sample performance, forward demo and ML.
