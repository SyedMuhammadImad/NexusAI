# ADR-018 - V1 Operational Scope and Conditional Demo Integration

2026-10-01 amendment: the owner's new P8 research task / accepted ADR-005
supersedes this ADR's P8 deferral only. P5/P6/P7 freeze, P9's independent obligations,
V1_PARTIAL and all operator/economic gates below remain unchanged.

Status: **ACCEPTED** for scope/dependencies only, 2026-09-24.
Authority: owner's NEXUSAI V1 FINAL COMPLETION TASK. This is not an operational
qualification receipt, a new risk policy, or permission to bypass a failed gate.

## Decision

Preserve P0-P7 evidence and freeze P5/P6/P7 for V1. Defer both P8 ML tracks and
Kronos; do not resume the prior P8 task. P10 is DEFERRED_FORWARD_QUALIFICATION.
P11 is OUT_OF_V1_SCOPE. P9 no longer depends on P8 completion. Implement full
original P9 observability, not a reduced replacement, with P8_DEFERRED placeholders.

V1 targets actual isolated P3 demo proof, manual canonical trading, authorized
live WhatsApp ingestion/execution, selected deterministic demo automation, full
P9, the existing frontend, persisted operator controls, restart/reconciliation,
and an evidence export. None of these operational targets is complete by this ADR.

P3 operator verification is the first critical gate. The owner now authorizes
that isolated procedure conditionally on all existing safeguards. Normal broker
execution remains HARD_DISABLED until actual P3 evidence passes. Non-executing
engineering may proceed, but cannot manufacture an operational PASS.

After P3 passes, an explicitly composed DEMO_ONLY operational path may integrate
P4 with P3. This conditionally supersedes ADR-012's blanket P4-P9 non-execution
dependency restriction, not its separation of fixture and broker evidence. The
current application/storage block is unchanged until separately implemented and
verified within this task. Do not drop a trigger or flip a flag as qualification.
Preserve immutable prior research, fixture requests and source-policy revisions;
never drain old approvals into broker orders. Any schema change must be additive.

## Strategy Exception

The owner selects existing EMA 9/21, EMA 20/50, MACD, Supertrend and Donchian as
candidate deployments, not as profitable strategies. This explicit V1 permission
supplements ADR-001's strategy eligibility restriction for bounded demo operation
only, after P3 and the operational integration gates pass. It does NOT amend
ADR-006 gates or P7's NO_STRATEGY_RESEARCH_QUALIFIED result. Every deployment must
retain DEMO_ONLY, UNQUALIFIED_AUTOMATION and RESEARCH_EVIDENCE_INSUFFICIENT labels.
Deployment is not qualification. No new strategies, tuning or research reruns.

Fresh broker-compatible CLOSED candles must feed the unchanged P6 definitions.
Independent proposals retain exact identities; common P2 reservations/exposure
decide competing admissions, not a newly invented voting/merging policy.

## Unchanged Invariants

- Canonical source -> P1 -> P2 -> reservation -> P3 is the only economic route.
- HALT overrides persisted manual, WhatsApp and automated execution switches.
- LIVE remains structurally locked; no UI/config/message can authorize it.
- Historical/screenshot evidence never executes.
- WhatsApp requires both exact authorized group AND sender, fresh immutable message
  identity, unambiguous explicit signal fields, and common P2 sizing/admission.
- P9 is observer-only: no order retry, safety override or invented reconciliation.
- Broker observations remain append-only; ambiguous state retains risk and blocks
  resubmission. No local close may be represented as a broker-confirmed close.
- P2-DEMO-1.0, recorded risk baselines, account isolation and cost evidence are not
  weakened. Missing historical floating equity is not reconstructed from balance.
- Current owner choice: use an EXISTING demo account with recorded risk history.
  This is not permission to reset the baseline or adopt an unverified old account.

## Acceptance

The exact A-H V1 acceptance matrix and full P9 obligations are recorded in
../Audits/NEXUSAI_V1_ACCEPTANCE.md. REAL_DEMO_PROVEN, FIXTURE_PROVEN, NOT_RUN and
BLOCKED_EXTERNAL_INPUT remain distinct. No blanket completion from fixture tests.
Any unavailable live WhatsApp event or genuine strategy signal remains explicit;
do not manufacture events. No Git push. No P10 qualification or P11 implementation.
