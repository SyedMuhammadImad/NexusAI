# NexusAI V2 — Authoritative Engineering Specification

**Status:** APPROVED GOVERNANCE BASELINE — P0 VERIFIED_COMPLETE (2026-09-10)  
**Evidence baseline:** 9 September 2026  
**Audited repository:** `D:/project` at commit `80f745be7a64681a2225ef7565a344a186a58a63`, branch `core-rebuild`  
**Implementation status:** HALTED / NOT QUALIFIED FOR TRADING  
**Purpose:** Replace the obsolete Master Prompt as the controlling requirements specification after human approval.

## 1. Source Basis and Authority

This specification reconciles three supplied artifacts:

1. `NEXUSAI_GROUND_TRUTH_AUDIT.md` — evidence of what the inspected repository actually contains and what was verified.
2. `NEXUSAI_GAP_ANALYSIS.md` — requirement-by-requirement reconciliation and disposition analysis.
3. `NexusAI_Master_Prompt.md` — historical intended architecture and requirements.

The Master Prompt is **not implementation evidence** and is no longer authoritative where it conflicts with the audit or this approved V2 specification.

### Source-of-truth precedence

For **what currently exists or works**:

1. Reproducible repository evidence, broker evidence, test output and dated audit evidence.
2. `knowledge/CURRENT-STATE.md` only when it cites such evidence.
3. Everything else.

For **what should be built**:

1. This approved `NEXUSAI_V2_SPECIFICATION.md`.
2. Accepted ADRs under `knowledge/Decisions/`.
3. `knowledge/ARCHITECTURE.md` and `knowledge/ROADMAP.md` as derivatives of the specification.
4. Historical Master Prompt only as non-authoritative background.

If implementation and specification disagree, **neither silently wins**. Record a drift finding and resolve it explicitly.

## 2. Reconciled Ground Truth

The inspected default application is an authenticated historical-review application with a persistent halted lifecycle state. It does not instantiate the retired trading agents. A substantive lifecycle/identity ledger library exists and has strong isolated fixture coverage, but the default application does not wire real signal, intent, order, deal or position ingestion into it. The legacy trading stack remains in source but is inactive under normal startup and contains reproduced defects in risk, execution replay protection, portfolio accounting, compliance gating, event delivery, synthetic backtesting and learning attribution.

The latest isolated full suite collected 170 cases: 169 passed, 1 failed, with the failed archive idempotency test passing on a focused rerun. This is **not** a trading-system completion metric and does not establish broker operation, profitability or production readiness.

## 3. V2 Mission

Build NexusAI into a **demo-only, evidence-driven automated trading research and execution system** in which every economic action is attributable, risk-authorized, broker-reconciled and reproducible.

The V2 system must be able to prove this chain for every executed trade:

`Source Event -> Canonical Signal -> Validated Signal -> Trade Intent -> Risk/Compliance Decision -> Execution Request -> Broker Order -> Broker Deal(s) -> Position State -> Broker-Confirmed Outcome`

Every state transition must have durable identity, provenance, timestamps, replay semantics and evidence.

## 4. Non-Negotiable Safety and Evidence Rules

- **HALTED by default.** No implementation phase may implicitly enable trading.
- **Demo only.** No real-money trading may be enabled by this specification.
- **No synthetic price series for strategy qualification or profitability claims.**
- **No ML profitability model trained on parser/acceptance labels.** UNKNOWN or UNVERIFIED outcomes are excluded from profitability training.
- **Chronological / walk-forward validation only** for time-series ML and strategy qualification.
- **No trading action without an authoritative deterministic admission gate.** Risk/compliance policy is evaluated before economic execution.
- **Risk/compliance veto is final for the request being evaluated.** No parallel subscriber may approve an order before a veto is known.
- **No local inferred close may become broker truth.** Outcomes must reconcile to broker-confirmed deals/positions and include defined costs.
- **Human-sourced and bot-sourced signals remain distinct end-to-end.** Unknown source is not silently reassigned.
- **At-most-once local request handling is insufficient.** Broker request ambiguity, retries, crashes and reconciliation require durable idempotency/recovery semantics.
- **No feature is COMPLETE because code exists.** Completion requires the testing gates in `knowledge/TESTING.md`.
- **UNKNOWN stays UNKNOWN.** Agents may not fill missing requirements, broker facts or metrics with assumptions.

## 5. Target Architecture

### 5.1 Architectural principle

V2 is organized around a **durable economic lifecycle**, not around a collection of agents voting over an in-memory event bus.

```text
External Sources                  Bot Research Sources
      |                                  |
      +--------------+-------------------+
                     v
             Source Adapters
                     v
             Canonical Signal
                     v
        Deterministic Validation
                     v
               Trade Intent
                     v
       Authoritative Safety Gate
        [Risk + Compliance Policy]
                     v
             Execution Request
                     v
            Broker Executor
                     v
              MT5 DEMO only
                     v
        Broker Observation Bridge
         Orders / Deals / Positions
                     v
              Lifecycle Ledger
                     v
        Outcome / Accounting Engine
                     v
      Monitoring / Research Datasets
```

### 5.2 Control-plane separation

**Control plane:** configuration, halt state, authorization, policy versions, qualification state, operator actions.  
**Economic data plane:** signals, intents, decisions, execution requests, broker evidence, positions, outcomes.  
**Research plane:** immutable historical market data, backtests, strategy tournament, ML datasets/models.  
**Presentation plane:** review UI, status, dashboards. UI claims must derive from evidence, not static labels.

### 5.3 Canonical lifecycle entities

The existing rebuild ledger contracts are the starting point, not a finished integration. V2 must maintain stable IDs for at least:

- source_event_id
- signal_id
- intent_id
- safety_decision_id
- execution_request_id / client_order_id
- broker_order_id
- broker_deal_id
- broker_position_id
- outcome_id
- source identity and source type
- account identity
- policy/config version
- original source timestamp, ingestion timestamp and decision/execution timestamps

No symbol-only or “latest matching trade” attribution is allowed.

### 5.4 Safety gate

Risk and compliance are one authoritative pre-execution boundary, even if internally implemented as separate modules. The gate must:

- reject non-finite or invalid numeric values;
- enforce direction-aware entry/SL/TP geometry;
- enforce the approved minimum R:R policy before execution;
- reject unknown actions;
- enforce account/position/exposure/drawdown policies using broker-unit-aware calculations;
- reserve risk atomically enough to prevent concurrent approvals from exceeding limits;
- respect persistent HALT / kill-switch state;
- persist both approval and rejection reasons;
- never permit an asynchronous compliance violation to arrive after execution approval.

Exact sizing baselines, weekly boundaries and correlation policy remain human decisions until resolved by ADR.

### 5.5 Execution boundary

The execution subsystem is rebuilt around a durable request identity and broker reconciliation. It must distinguish:

- never submitted;
- submitted and acknowledged;
- submitted with ambiguous client outcome;
- rejected by broker;
- partially filled;
- filled;
- cancelled/expired;
- recovered after restart.

Retries must not create duplicate economic orders. A DB lock around publishing is not sufficient proof of exactly-once broker behavior.

### 5.6 Broker truth and accounting

Broker orders, deals and positions are evidence objects. Caller-supplied shapes are not automatically trusted as broker truth. A dedicated broker observation bridge must attest the account/session and reconcile observations into the ledger.

Outcome accounting must not be enabled for learning until rules for partial closes, costs, spread/slippage, same-bar TP/SL ambiguity, timeouts/no-hit, SELL direction and multi-deal positions are approved and tested.

### 5.7 Signal sources

V2 supports a common source-adapter contract. Intended source categories are:

- `human_signal`
- `bot_signal`
- `unknown` only where historical evidence cannot establish provenance

ADR-001 is accepted: `WHATSAPP_HUMAN` and `MANUAL` are demo-execution-capable after the common safety lifecycle; `NEXUSAI_STRATEGY` becomes eligible only after later qualification; `HISTORICAL_WHATSAPP` and `SCREENSHOT` are research/non-execution sources. No interface may bypass canonical validation and the common safety/execution lifecycle.

### 5.8 Research architecture

Research is downstream of trustworthy market data and outcome semantics:

`Immutable real candles -> deterministic replay/backtester -> strategy library -> tournament/walk-forward qualification -> optional ML filter -> forward-demo qualification`

The historical “30 strategies” list remains a **research backlog**, not an implementation obligation until the research foundation passes its gates.

### 5.9 ML architecture

The acceptance classifier is not a profitability model. ADR-005 is intentionally DEFERRED: future bot profitability filtering and human-trader imitation must not be conflated. Until ADR-005 is accepted, profitability/imitation ML remains disabled for execution.

Any future profitability filter must use verified economic outcomes, chronological/walk-forward validation and a documented activation gate. The old AUC 0.58 / 200-trades-per-instrument numbers are retained as historical proposals, not automatically authoritative thresholds.

### 5.10 RL

Reinforcement learning is **DEFERRED**. No RL implementation, dependency, environment, training or activation belongs in the current roadmap before the core lifecycle, safety, broker reconciliation, research pipeline and forward-demo evidence are qualified. RL may never bypass deterministic risk limits.

## 6. Disposition Register

### KEEP

Preserve and build upon these bounded capabilities unless new evidence disproves them:

- Default persistent HALT / execution-disabled behavior.
- Current token enforcement and authenticated write controls.
- Corrected deterministic signal parser behavior, including repaired TP integer tokenization and finite/timestamp contract tests.
- Lifecycle ledger identity/integrity work: strict contracts, account binding, transactional signal/intent persistence, exact lineage, quarantine, migrations and SQL identity guards.
- Source archive preservation and review history/correction capability.
- `UNVERIFIED` outcome semantics for historical review records; never reinterpret them as profitable labels.
- Chronological splitting and train-only scaling principle where already correctly implemented.
- FastAPI + React/Vite + SQLite foundation only as **bounded retained infrastructure**, not as a claim that all infrastructure is “solid.”
- Demo-only execution constraint.
- Human/bot provenance separation requirement.
- Evidence-first audit discipline and versioned requirements authority.

### FIX

- Historical archive deduplication contract/test: decide whether identity is byte-container or normalized transcript, then make implementation and tests agree.
- Cross-database historical approval consistency and revalidation gaps.
- Docker/readiness healthcheck mismatch with token-required health behavior.
- UI/status wording so measured facts, static policy and dated verification are clearly distinct.
- End-to-end source identity propagation where existing stores/serializers drop it.
- Original-time propagation and freshness evidence at the actual action boundary.
- Exact learner-store chronological query only after targeted inspection verifies the current SQL; do not “fix” an UNKNOWN by assumption.
- Any retained legacy utility must have its call contract verified before operational reuse.

### REBUILD

- Active source-to-ledger ingestion bridge.
- Authoritative deterministic validation + risk/compliance admission gate.
- Risk sizing and exposure engine with finite/action/broker-unit semantics, reservations and persistent halt enforcement.
- Execution engine with durable request identity, idempotency, crash recovery and broker reconciliation.
- Broker-to-ledger attestation/observation bridge.
- Position/accounting/outcome engine based on broker-confirmed evidence rather than local inferred closes.
- Common source adapter architecture for human and bot signals.
- Real historical candle store and provenance checks.
- Real deterministic backtester/replay engine.
- Monitoring based on broker-confirmed lifecycle and data-quality evidence.

### DELETE_CANDIDATE

Deletion requires dependency review, preserved audit evidence, tests and explicit approval. Nothing here is pre-authorized for deletion.

- Synthetic/random-price legacy backtesting execution path.
- Legacy adaptive weight mutation based on unverified outcomes.
- Symbol-only/latest-same-symbol outcome attribution path.
- Retired local-close portfolio behavior if no approved consumer remains.
- Obsolete sentiment influence and unused orchestration slots if V2 does not retain that architecture.
- Unreachable/duplicate legacy application wiring after preservation and consumer analysis.
- Other duplicate stores/services only after lineage/migration requirements are proven.

### DEFER

- Building the historical list of 30 strategies.
- Strategy tournament and winner selection.
- Profitability XGBoost/ML activation.
- Human-trader imitation learning.
- Source-level performance rankings until outcomes are broker-confirmed and attributable.
- Advanced dashboard analytics whose inputs are not yet trustworthy.
- PPO/RL.
- Any live-money deployment.
- Automated architecture self-modification, adaptive agent weights or autonomous strategy generation.

### NEEDS_HUMAN_DECISION

No coding agent may choose these implicitly:

1. Which human signal interfaces are in V2: live WhatsApp bridge, manual paste, screenshots, historical review, or a defined combination.
2. Exact freshness policy: source timestamps, timezone, future timestamps, ambiguous dates, timeframe-aware expiry and duplicate arrival through multiple interfaces.
3. Risk policy details: capital/equity baseline, broker-unit conversion, maximum per-trade risk, daily/weekly boundary semantics, correlation policy and handling of unknown source.
4. Exact outcome labeling rules: SELL, both TP/SL in one bar, no-hit/timeout, spread, slippage, commissions/swaps, partial closes and multiple deals.
5. Whether future ML is a bot-only profitability filter, a separate human imitation model, or two explicitly separate systems.
6. Strategy tournament ranking/tie-breaking, degradation calculation and qualification-clock reset rules.
7. Which legacy source files are kept only for historical evidence versus retained as callable compatibility code.
8. Future post-demo live authorization process. V2 itself does not authorize live trading.
9. Exact old orchestrator weights/confirmation sets only if that architecture is intentionally retained; they are not V2 defaults.
10. External credential revocation/provider/account state where repository evidence cannot prove it.

Until a human decision exists, the safe default is **HALT / DISABLED / UNKNOWN / NOT QUALIFIED**, not an invented policy.

## 7. Phased Roadmap

### P0 — Governance, Preservation and V2 Baseline

**Goal:** establish one controlling specification and preserve current evidence.

Entry: audit and gap analysis exist.  
Required work: approve V2 spec; baseline Git state; create Obsidian control files; preserve audit artifacts; identify credential exclusions; record unresolved ADRs.  
Exit gate: repository is recoverable, V2 is approved, `CURRENT-STATE.md` is evidence-based, no coding agent treats the old Master Prompt as authority.  
Trading: **HALTED**.

### P1 — Canonical Lifecycle Integration

**Goal:** wire the active application to the existing ledger concepts without enabling broker execution.

Must establish canonical source event -> signal -> intent identities, provenance, account binding and durable transitions. Add source-to-ledger integration and failure/replay tests.  
Exit gate: canonical lifecycle can be exercised end-to-end with fixtures and restart/replay tests, with no symbol-only attribution.  
Trading: **HALTED**.

### P2 — Authoritative Safety Engine

**Goal:** one deterministic pre-execution admission boundary.

Includes geometry/R:R validation, risk policy, compliance policy, reservations, halt semantics, persistent decisions and concurrency tests. Human ADRs must resolve exact risk/freshness policies before final qualification.  
Exit gate: every simulated execution request is either durably approved or rejected by the single authoritative boundary; veto races are impossible in tests.  
Trading: **HALTED**.

### P3 — MT5 Demo Execution and Broker Reconciliation

**Goal:** prove safe economic request semantics against a demo broker environment.

Includes durable client request identity, account attestation, ambiguous-result recovery, partial-fill handling, order/deal/position reconciliation, restart recovery and demo-only enforcement.  
Exit gate: controlled demo tests prove no duplicate economic action across retry/crash scenarios and lifecycle state reconciles to broker evidence.  
Trading: limited **DEMO TEST MODE only** after explicit operator enablement.

### P4 — Source Adapters and Provenance

**Goal:** add approved human/bot ingestion interfaces without bypassing P1-P3.

Human source modality depends on ADR. Bot sources may emit canonical candidate signals only. Every source carries immutable provenance and original timestamps.  
Exit gate: duplicate/multi-interface replay, stale/future timestamps and source tagging are tested end-to-end.  
Trading: **DEMO only**.

### P5 — Real Market Data and Deterministic Data Interface

**Goal:** create immutable, provenance-aware, research-qualified REAL historical datasets and their deterministic data interface (ADR-013).

No synthetic prices. Define missing candles, timezone/session normalization, corporate/provider anomalies where applicable, spread/slippage assumptions and deterministic replay.  
Exit gate: meaningful real history and qualified datasets for every required instrument/timeframe; a pinned query returns exact identity, instrument, timeframe, range, ordered real candles, provenance, quality and bounded gap/discontinuity metadata, without synthetic observations. No strategy execution belongs to P5 (ADR-013).

### P6 — Strategy Research Library

**Goal:** implement research strategies behind a stable `BaseStrategy`-like contract only after P5.

The historical 30-strategy list is a backlog. Implement incrementally; each strategy requires deterministic tests and no hardcoded invalid risk geometry.  
Exit gate: a known strategy produces reproducible replay results from the same immutable qualified dataset (moved from P5 by ADR-013); selected candidate strategies have sufficient trade counts and reproducible in-sample/out-of-sample results. No winner claims yet.

### P7 — Strategy Tournament / Walk-Forward Qualification

**Goal:** compare strategies under an approved ranking and degradation methodology.

Historical thresholds may seed an ADR but are not silently authoritative.  
Exit gate: tournament methodology is versioned; all candidates receive full metrics; eliminated/selected status is reproducible; no data leakage.

### P8 — Optional ML Filter

**Goal:** add ML only when verified economic labels and sufficient samples exist.

UNKNOWN/UNVERIFIED outcomes excluded. Walk-forward validation required. Model role and activation threshold require ADR.  
Exit gate: out-of-sample evaluation, calibration/threshold behavior, leakage checks, model/version provenance and pass-through fallback are all verified.  
Until gate passes: **ML cannot influence execution**.

### P9 — Monitoring, Operations and Evidence Dashboard

**Goal:** report truthful runtime, data quality, safety and source-separated performance.

Metrics derive from authoritative lifecycle/broker evidence. Static “passed” labels are prohibited.  
Exit gate: alerts/metrics have tested denominators, time windows and provenance; monitoring failure cannot silently enable trading.

### P10 — Forward Demo Qualification

**Goal:** accumulate a trustworthy, broker-confirmed forward-demo record.

The old “3 months” requirement is retained as a minimum historical intent, but exact success criteria and reset rules require approved policy.  
Exit gate: approved duration/trade-count/performance/risk criteria are satisfied by broker-confirmed evidence.  
Result: **does not automatically authorize live trading**.

### P11 — Advanced Research / RL

**BLOCKED** until P0-P10 are complete and a new ADR justifies it. No current implementation obligation.

## 8. Phase Blocking Rules

- P2 cannot close before unresolved risk/freshness policy ADRs needed by its tests are accepted.
- P3 cannot begin economic demo actions until P1 and P2 gates pass.
- P4 source adapters cannot bypass P1-P3 lifecycle/safety semantics.
- P6 cannot begin qualification work without P5 real-data/backtest integrity.
- P7 cannot select winners without a versioned tournament policy.
- P8 cannot train/activate without broker- or backtester-verified outcome labels and approved model role.
- P10 cannot use legacy local PnL as forward evidence.
- P11 remains blocked regardless of coding-agent suggestion until explicit human approval.

## 9. Definition of Done

A roadmap item may be marked `VERIFIED_COMPLETE` only when:

1. Requirement and acceptance criteria are documented before implementation.
2. Affected source and data boundaries are identified.
3. Unit/contract tests pass.
4. Integration tests pass where applicable.
5. Negative/failure-path tests pass.
6. Relevant regression suite passes or any unrelated failure is documented and approved.
7. For economic boundaries, restart/replay/idempotency tests pass.
8. Evidence is captured with command/test identifiers and commit hash.
9. `CURRENT-STATE.md` is updated.
10. `ROADMAP.md` status is updated only after evidence exists.
11. ADR is created/updated for architecture or policy changes.
12. No new CRITICAL/HIGH unresolved regression is introduced.

## 10. Documentation and Obsidian Contract

Obsidian is a view over the repository Markdown. It is not a second truth database.

Required vault files:

- `00-DASHBOARD.md`
- `PROJECT.md`
- `ARCHITECTURE.md`
- `CURRENT-STATE.md`
- `ROADMAP.md`
- `TESTING.md`
- `RISKS.md`
- `DELETE-CANDIDATES.md`
- `DECISIONS.md`
- `Decisions/` ADRs
- `Audits/` dated drift/audit reports
- `Bugs/`, `Components/`, `Agents/` as the project grows

Documentation updates are part of task completion. A nightly job is a **drift auditor**, not the primary writer of project truth.

## 11. Nightly Drift Audit

Read-only job compares Git changes, code, tests, dependencies and the vault. It must detect:

- implementation changes not reflected in `CURRENT-STATE`/architecture;
- documentation claims unsupported by code/test evidence;
- roadmap tasks marked complete without required gates;
- failing/flaky tests;
- new dependencies;
- architectural drift;
- new TODO/FIXME/HACK markers;
- new secret exposure risk;
- unapproved scope expansion;
- stale evidence dates;
- changes to HALT/demo-only controls.

It writes a dated report under `knowledge/Audits/`. It must not silently rewrite architecture, statuses or source code.

## 12. Superseded Master-Prompt Rules

The following historical prescriptions are explicitly **not authoritative** in V2 unless re-approved by ADR:

- “Infrastructure is solid; touch nothing else.”
- “Risk file is well-built/correct.”
- Exact old orchestrator weights and confirmation sets.
- Parallel risk/compliance subscriber behavior.
- Proposed SQLite claim-then-publish pattern as proof of exactly-once execution.
- Hardcoded correlation examples as validated risk policy.
- Ten-minute/two-candle freshness snippets without a unified timestamp policy.
- Acceptance classifier as trader profitability/imitation evidence.
- Any success claim derived from synthetic backtests.
- Blanket preservation of defective legacy methods.
- Treating the original phase numbering as evidence that controlled-rebuild work completed those phases.

## 13. Approval Gate

Before Astra/Codex resumes implementation, the human owner must approve:

- this V2 specification;
- P0 roadmap state;
- the list of unresolved ADRs required before P2/P3;
- the rule that the old Master Prompt is historical context only;
- the rule that deletion candidates are not deletion authorizations.

Until that approval, NexusAI remains in specification/reconciliation mode and trading remains halted.

## P0 Accepted Decision Addendum

The following decisions were accepted during P0 governance review and supersede unresolved/proposed wording elsewhere in this specification where a conflict exists:

- ADR-001 — approved source taxonomy and execution eligibility.
- ADR-002 — UTC normalization, preserved original time evidence, fail-closed ambiguity, configurable freshness with initial 10-minute default.
- ADR-003 — one authoritative safety gate, global minimum R:R 1.5, fail-closed invalid risk inputs.
- ADR-004 — explicit outcome state taxonomy and broker-authoritative demo closure.
- ADR-007 — Quarantine -> Replace -> Prove -> Delete Candidate -> Human Approval -> Delete.
- ADR-008 — research/demo-only V2; LIVE locked and separately authorized in any future program.
- ADR-009 — layered archive/transcript/message/signal identity and no silent fuzzy merging.

ADR-005 and ADR-006 are intentionally deferred to their prerequisite phases.

### P0 closure note

Governance approval and repository-local P0 verification are complete as of
2026-09-10. Baseline `ae800c743bb7216b666dfca11c4751fb79022282` preserves the
control package. Recovery, committed controls and secret exclusions were checked
after that commit; exact evidence and limits are in `knowledge/P0-CLOSEOUT.md`
and `knowledge/Audits/P0-CLOSEOUT-AUDIT.md`. P1 is READY, not started. This status
update changes no architecture, ADR semantics or application/trading behavior.
