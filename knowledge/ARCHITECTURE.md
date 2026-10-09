# NexusAI V2 — Architecture

## Current-Profile Operator Boundary (2026-10-05)

ADR-022 supersedes withdrawn dedicated-user/session-zero provisioning. The owner
approved a cooperative non-admin current-profile path with a separate pristine
portable terminal, one worker, exact DEMO account/server, fixed private credentials
and isolated verification state. Same-user concurrent interference is an explicitly
accepted residual risk, not OS isolation or atomic account-bound MT5 submission.
Legacy host booleans/receipts cannot be forged or reused to represent this path.
No replacement native provider is qualified yet. Existing P4/database/app broker
blocks, P2/HALT, reservations and LIVE_LOCKED remain unchanged. No native strategy
or WhatsApp routing before actual manual proof. P8 work remains deferred.

## P8 Offline Research Boundary (2026-10-01)

ADR-005 now locks separate profitability, historical human-behavior and Kronos
research. Only ADR-018's P8 deferral is superseded; no execution permission changes.
Read-only pinned P5/P6/P7 evidence -> causal signal-time features -> resolution-
available WIN/LOSS labels -> expanding chronological baseline evaluation ->
append-only P8 model registry / public evidence. Human archives and Kronos have
independent datasets, labels, dispositions and limitations. The P5 store is never
initialized or written by the P8 reader; all P8 state belongs to its ignored root.

P9 consumes a lightweight checksum-validated projection of the public research
result, without importing sklearn/torch or loading models. Missing/invalid evidence
stays unavailable. Fixture snapshots default to unavailable unless explicitly
injected with public research evidence; preview operator state remains temporary.
No P8 component creates lifecycle signals/requests, changes P2/HALT, registers an
enabled deployment, reconnects legacy agents or serves automatic predictions.
The existing canonical ExecutionRequest -> HARD_DISABLED boundary is unchanged.
See Components/P8-ML-RESEARCH.md and P8-MODEL-REGISTRY.md.

## V1 Integration Boundary (2026-09-28)

ADR-018 freezes research and authorizes conditional demo integration, not removal
of current execution gates. Actual implemented path is manual UI or authenticated
WhatsApp envelope -> durable V1 ingress -> P4 source/parser -> P1 intent -> P2
decision/reservation -> eligible ExecutionRequest -> **HARD DISABLED**.
Existing source-registry/database and application native-composition gates remain.
No UI, connector or monitoring route can submit, unhalt, or enable execution.

V1 migration 009 adds control/deployment/health audit tables, ingress checkpoints
and alert acknowledgments. Replayed identities cannot change source payloads.
Controls use revision comparison; enables reject without qualification. The five
frozen strategy definitions can be registered disabled, never execution-qualified.
Current-candle scheduling and qualified operational composition remain absent.

P9 projections read a consistent transaction. Activity windows are inclusive UTC;
economic tables are explicitly CURRENT state, not historical as-of reconstruction.
Fresh P2 evidence may supply descriptive account/quote values; stale/missing
evidence stays unavailable. Reports do not call brokers or change economic state.
Alerts/acknowledgments never clear HALT. No P6/P7 P&L is passed off as forward P&L.
Original full P9 obligations remain open, enumerated in V1 acceptance.

Connector transport is a separate operator-only process. A dedicated loopback
credential only permits the human-message endpoint, not control/monitoring APIs.
Its private SQLite outbox preserves uncertain HTTP deliveries for idempotent
ingestion replay, never economic submission replay. No connector process was run.
See Components/V1-OPERATIONS.md for provenance, scope and limitations.

## P7 Research-Only Tournament (2026-09-22)

Qualified P5 pins -> frozen P6 replay -> ADR-006 gates -> immutable P7 research
result. This path is disconnected from economic execution. Schema marker 8 adds
append-only p7_runs to the owned research root only; full individual replays stay
in the P6 ledger. No lifecycle/operator migration or application startup occurs.
The approved chronological split and bounded robustness cases are versioned;
instrument/timeframe cells cannot pool samples to manufacture qualification.
BROKER EXECUTION HARD DISABLED. See Components/P7-STRATEGY-TOURNAMENT.md.

P7 Arena addition: P6 persisted trades + final P7 result -> deterministic bounded
snapshot/event artifact -> authenticated read-only app routes -> existing React
hash page #/tournament. Browsers select timestamps/filters but never compute gates.
Artifact/result hashes bind the projection; missing/stale evidence fails closed.
The local preview uses synthetic access and a fresh temporary lifecycle fixture;
only read-only P7/status routes are reachable, never historical operator stores.

## P6 Non-Executing Research Plane (2026-09-22)

Pinned P5 ResearchDatasetReader -> validated ResearchData -> closed-bar Features /
BaseStrategy -> explicit research candidate -> BID/ASK cost/geometry admission ->
ADR-004 reconstruction -> immutable research result/trade ledger -> pinned P7 input.
No strategy runtime is connected to the active app, P2 approval or P3 submission.
The optional canonical representation is non-authorizing; P4 still rejects
NEXUSAI_STRATEGY economic eligibility. Broker execution remains HARD DISABLED.

Research-only schema marker 7 adds p6_runs/p6_trades under the existing owned P5
research root. Atomic append-only publication preserves all P5 and prior research
evidence. No operator/lifecycle schema or database is migrated by the study.
Complete contracts, definitions, costs, chronology and limitations:
Components/P6-STRATEGY-RESEARCH.md. Current verification status is in CURRENT-STATE;
older P5/P6-not-started sections below describe their dated phase checkpoints.

## P5 Alternative Native-Bar Research (ADR-017)

EV public annual exports -> strict dual-sided Candle normalization -> immutable
research datasets/raw receipts -> separate native-hour/session qualification ->
version-pinned ResearchDatasetReader. Research schema marker 6 adds an immutable
qualification table; no prior schema or dataset is rewritten. Provider selection
is explicit, not an automatic latest/fallback splice. HistData schema 1-5 evidence
and paths below are retained. Unknown gaps cannot be crossed by a qualified query.

P6 can consume dataset/qualification IDs and UTC ranges without provider-specific
retrieval code. Native H4 prices are checked against H1 on both sides; incomplete
expected hours are withheld from research, never synthetically repaired. Source
volume remains UNKNOWN; K-line conversion is data-only, not Kronos runtime proof.
No market-data calendar is P2/P3 broker evidence. All execution remains HARD
DISABLED under ADR-012. P5 VERIFIED_COMPLETE; P6 READY, not implemented here.
See Components/P5-ALTERNATIVE-PROVIDER.md and its closeout audit.

## P5 Empirical Feed Availability (ADR-016)

Research schema 5 stores immutable empirical calendar/qualification evidence.
Calendar-aware 1H/4H resampling consumes only real M1 observations, requires all
expected minutes, and binds source/calendar/rule IDs in the dataset manifest.
It is separate from the older complete-24/7-bin versions and operator/lifecycle
stores. Empirical feed availability cannot authorize execution; P2/P3 still require
live validated broker evidence. See Components/P5-EMPIRICAL-FEED.md.


## P5 Session-Aware Query (ADR-015)

The dedicated research store now supports separate immutable session qualification
reports binding candle version, observation qualification and versioned calendar.
Expected closures may bridge a query; unknown/provider gaps cannot. Calendar
contradictions fail closed. No candle rewrite, resampler change or execution path.
Exact HistData calendar certainty remains PARTIAL; see Components/P5-SESSIONS.md.


## P5 Data Foundation Checkpoint (2026-09-14)

The non-executing research plane now has a dedicated HistData provider boundary,
Decimal Candle model, immutable raw/versioned dataset store and range-query API.
It has no executor, lifecycle/operator-store dependency or strategy/ML import.
M1 source bars aggregate only into complete UTC-anchored 1H/4H bins; questionable
datasets retain evidence and default research queries reject them. Old validator
versions remain immutable but cannot qualify through the current default query.
No authoritative V2 path imports the legacy synthetic/random backtester.

P5 is PARTIAL; P6 remains BLOCKED on sufficient qualified continuous history.
Accepted ADR-013 moves strategy replay to P6. The additive research qualification
table preserves immutable manifests and separately projects explicitly bounded
usable segments. Contiguous queries reject gaps; segmented queries must opt in and
retain boundaries/provenance. No reconstructed continuity or execution path.
Details: Components/P5-MARKET-DATA.md and Audits/P5-CLOSEOUT.md. P3 operator
verification remains DEFERRED and the P4 broker hard block is unchanged.

## P4 Source Integration (2026-09-13)

The active application now exposes authenticated non-executing source ingestion.
An append-only source registry gates canonical persistence, intent admission and
P2 request eligibility. MANUAL/WHATSAPP_HUMAN may reach P2; strategy remains
UNQUALIFIED and historical/screenshot remain research-only. No source auto-submits.
P4 configuration permanently blocks P3 attempt creation in that ledger, blocks
ExecutionEngine construction/snapshots, and cannot compose with an execution
adapter in the app. Explicit old P1-P3 fixture compositions remain test-only.
Details and limits: Components/P4-SOURCE-INTEGRATION.md; evidence: TESTING.md.
The governance-only descriptions below are the earlier ADR-012 checkpoint;
P3 operator verification remains DEFERRED and live execution stays unauthorized.

## Current Non-Executing Boundary - ADR-012

P3 ENGINEERING is VERIFIED_COMPLETE only within non-operational/fixture/native-
normalization scope. P3 OPERATOR DEMO VERIFICATION is DEFERRED / PENDING, not passed.
The engineering dependency is released for sequential P4-P9 work; operational
broker execution stays HARD DISABLED. This is a governance amendment, not a new
runtime switch or an OS-isolation claim.

```text
Signal -> Canonical lifecycle -> P2 Safety -> ExecutionRequest
                                            -> BROKER EXECUTION DISABLED
```

No source adapter, data service, strategy, tournament, ML filter, dashboard or
scheduler may bypass the canonical/P2 boundary, load native execution into normal
composition, call operator verification tooling, or silently reconnect legacy
execution. Fixture/research requests/outcomes remain labeled non-operational;
an approved request is not a broker submission and cannot auto-drain into orders.
Each future P4-P9 integration must test preservation of this hard block.

P4 READY; P5-P9 advance sequentially after their predecessors and existing semantic
gates. ADR-005/006 remain deferred. P10 requires P3 OPERATOR VERIFICATION + P9.
Actual demo execution outside a separately authorized isolated verification step,
P10 and any live-readiness work require completed operator verification. LIVE
remains locked under ADR-008 even after demo verification.

No application code is changed. `core/rebuild/application.py:create_app` rejects
native adapter/account injection and defaults to no executor; existing operator
helpers are separate and remain unqualified. The full broker-flow diagram below
is a target for a qualified future operating state, not the allowed P4-P9 path.
Earlier dated composition statements remain historical evidence.

## Current vs Target

### Verified current architecture

- FastAPI authenticated review/status application.
- Persistent HALTED lifecycle state.
- Historical import/review/correction path.
- Deterministic parser with repaired TP tokenization.
- Lifecycle/identity ledger plus active P1 canonical persistence service/API,
  verified with fixtures; default execution remains disabled.
- No active default-app trading-agent composition.
- Legacy trading stack retained but inactive.

### P1 M1 composition (2026-09-10)

`main.py -> create_app -> Ledger + LifecycleService + authenticated lifecycle_router`.
The entrypoint itself was source-inspected, not started with operator credentials.
Factory tests prove source/signal/intent persistence, decisions and fixture-only
request identity. Reuse signals/order_intents/risk_decisions/account/observation
tables; add source_events and execution_requests through migration 003.

Default policy persists rejection. Fixture approvals require explicit construction
with a supplied database and synthetic account and are not accepted from HTTP.
No request dispatch exists; requests remain FIXTURE/RECORDED_NOT_SUBMITTED.
M2 subsequently added the explicit historical-review canonical bridge below;
P2 safety and P3 broker reconciliation remain missing.
See `Components/P1-LIFECYCLE-MAP.md`; the target diagram below is not a claim that
the entire chain is implemented.

### P1 closeout (2026-09-10)

P1 is VERIFIED_COMPLETE after M2 human acceptance as
COMPLETE_WITH_RECORDED_INCIDENT and M3 exit verification. No M3 architecture or
application changes were required. `chat_import_router` composes
`HistoricalCanonicalBridge(archive, lifecycle)` for explicit authenticated
promotion into the same ledger. Archive/transcript/message identities link to
immutable source/signal evidence; historical sources stop before intent creation.
Recoverable PENDING/SOURCE_ONLY/VALIDATED checkpoints are not a distributed
transaction or an automatic recovery worker. Corrected/ambiguous evidence stays
REVIEW_REQUIRED. Existing legacy records are not silently backfilled.

Default lifecycle decisions remain P1_DISABLED rejections. Fixture requests remain
FIXTURE / RECORDED_NOT_SUBMITTED with no dispatcher. Account identity is synthetic
in tests; no broker attestation is implied. Exact exit proof:
`Audits/P1-M3-EXIT-GATE.md`. P2 and later target components below are not delivered
by this closeout; no new architectural decision or policy was introduced.

### V2 target architecture

```text
Source adapters
    |
Canonical Signal
    |
Deterministic Validation
    |
Trade Intent
    |
Authoritative Safety Gate
(Risk + Compliance)
    |
Execution Request
    |
MT5 Demo Executor
    |
Broker Observation Bridge
    |
Lifecycle Ledger
    |
Broker-confirmed Position/Outcome Accounting
    |
Monitoring / Research datasets
```

## Architectural Invariants

- Durable exact IDs across the full lifecycle.
- Source/account identity preserved end-to-end.
- Persistent HALT state checked at the economic boundary.
- One authoritative pre-execution decision boundary.
- Broker evidence, not local inference, closes the economic lifecycle.
- Ambiguous execution results reconcile before retrying.
- Research and execution share definitions where appropriate but do not contaminate each other's evidence.
- UI is a view; it does not manufacture qualification state.

## Planes

### Control plane
Auth, halt, policy versions, qualification state, operator decisions.

### Economic lifecycle plane
Signals, intents, safety decisions, execution requests, broker orders/deals/positions, outcomes.

### Research plane
Immutable candles, deterministic replay, strategies, tournament, ML datasets/models.

### Presentation plane
Historical review, operational status, evidence-backed monitoring.

## Legacy Policy

Legacy code is evidence/compatibility material until individually dispositioned. It is not the V2 architecture merely because it exists.

## Accepted P0 Architecture Decisions

- **ADR-001:** execution-capable sources are `WHATSAPP_HUMAN`, `MANUAL`, and eventually qualified `NEXUSAI_STRATEGY`; `HISTORICAL_WHATSAPP` and `SCREENSHOT` are research/non-execution sources.
- **ADR-002:** original time evidence is preserved, normalized to UTC, ambiguity fails closed, and live freshness is configurable with an initial 10-minute default.
- **ADR-003:** one authoritative risk+compliance gate; minimum R:R 1.5; missing/stale/non-finite risk inputs fail closed.
- **ADR-004:** explicit WIN/LOSS/BREAKEVEN/TIMEOUT/AMBIGUOUS/UNKNOWN/CANCELLED semantics; broker evidence closes demo economic lifecycles.
- **ADR-007:** legacy lifecycle is Quarantine -> Replace -> Prove -> Delete Candidate -> Human Approval -> Delete.
- **ADR-008:** current V2 is research/demo only; LIVE remains locked and cannot be enabled by ordinary configuration.
- **ADR-009:** historical identity is layered across archive, transcript, message and signal provenance; no silent fuzzy merge.

ADR-005 (ML responsibility) and ADR-006 (tournament qualification) are deliberately deferred.

## P2 Policy Boundary (2026-09-11)

ADR-010 accepts the owner's initial demo policy P2-DEMO-1.0, recorded in
`Components/P2-SAFETY-POLICY.md`. The authoritative gate is still a target, not
implemented behavior at the policy-recording checkpoint. C01-C03 are explicitly
approved; subsequent owner-authorized P2 implementation is described below.

## Verified P2 Composition (2026-09-11)

Explicit factory safety configuration/provider -> SafetyEngine -> existing
canonical intent/risk_decision lineage -> atomic decimal P2 reservation ->
ELIGIBLE_NOT_SUBMITTED request. Migration 005 adds P2 tables without rewriting
001-004 or promoting existing FIXTURE requests. The trace includes both scoped
request types. Default startup stays HALTED; missing configuration stays disabled.
Provider inputs are not caller-supplied HTTP approvals. There is no broker dispatch.

P2 VERIFIED_COMPLETE: 79 focused / 94 P1 / 297 broad fixture tests passed.
The fixed numerical policy is P2-DEMO-1.0; effective configurations use versioned
config-N identities and immutable per-decision policy/input hashes. Full numerical,
recovery and trust boundaries: `Components/P2-SAFETY-ENGINE.md`. P3 attestation and
economic execution remain unimplemented and unqualified. No legacy agents started.

## P3 Fixture Composition (2026-09-11)

The owner subsequently authorized P3. Its current result is PARTIAL / FIXTURE_ONLY,
not a running demo trading service. The preceding dated P3-missing statement is
superseded only within this bounded fixture scope.

P2 request -> ExecutionEngine -> fresh SafetyEngine.revalidate_reserved -> durable
attempt/reservation marker -> injected BrokerAdapter -> exact broker observations
-> transactional decimal P3 projections and reservation reconciliation.
MT5DemoAdapter implements injected method checks/mapping without importing,
initializing or logging in to MT5. Its native snapshot_reader is an explicit
remaining integration prerequisite, not a default stub that returns empty data.

Migration 006 adds P3 attempts/events/orders/deals/positions/protective exits. P1
canonical identities and P2 allocations remain authoritative. Separate projections
avoid the old broker ledger's original-intent-volume/REAL assumptions. Source traces
join the exact chain; no symbol-only attribution or fabricated outcome is added.

The app factory permits only explicit FIXTURE adapter injection with isolated DB,
synthetic account, token and P2 configuration. Authenticated submit/reconcile paths
remain disabled in the normal app. Operator composition and actual demo verification
are outstanding. Full scope, crash semantics, residual risks and tests:
Components/P3-EXECUTION-RECONCILIATION.md. No P4 or legacy-agent reconnection.

## P3 ADR-011 Observation Journal (2026-09-12)

The approved revision-aware architecture adds migration 007, immutable native-field
evidence/observation history and derived current heads. NativeEvidenceReader and
NativeNormalizer feed the existing ExecutionEngine transaction; evidence persists
outside the economic-projection rollback savepoint. Exact known attempt lineage
links observations without treating them as extra fills. Prior immutable P3 deal
records are preserved. P2 and HALT remain authoritative; unresolved native revision
ordering/quantity/identity retains evidence and capacity, never resubmits.

Native adapters are injected, read-only normalization is fixture-tested, and no
operator/session initialization is added. Actual demo qualification remains open.
See Components/P3-NATIVE-EVIDENCE.md for supported modes, context-provider trust,
raw evidence limits and distinction between record heads and economic projections.

## P3 Operator Verification Composition (2026-09-12)

Separate VerificationLedger -> existing SafetyEngine -> operator-only one-shot
wrapper -> existing ExecutionEngine/MT5DemoAdapter/NativeEvidenceReader boundary.
No normal-app dispatch change. Existing audit storage supplies immutable run/use
records; an exclusive workspace claim prevents creating another local run to
reset the smoke budget. No new migration or policy is introduced.

The trusted isolation verifier/native connector remain operator prerequisites,
not supplied production adapters. Default denial occurs before connector access;
only synthetic providers are exercised. Real environment, safety-context and
demo qualification remain outstanding. See Components/P3-OPERATOR-VERIFICATION.md.
