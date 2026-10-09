# NexusAI V2 — Roadmap

Status vocabulary: `BLOCKED`, `READY`, `IN_PROGRESS`, `VERIFIED_COMPLETE`, `DEFERRED`.

2026-10-07 later owner approved manual configured-DEMO sign-in diagnosis and
ordered V1 continuation. Human startup handshake implemented;167 focused pass,
broad1226 passed,2333 warnings,423.02s, zero protected attempts/forbidden modules.
Owner-confirmed sign-in did not resolve IPC:CONNECT returned timeout, zero broker
actions. Terminal-only follow-up sign-in showed traffic0 / 0 Kb without native
attestation, then aborted before SDK. Isolated Python3.12/same SDK also timed out;
Python3.11 failed the existing path API before SDK. All owned sessions finished.
Native account/risk/cost proof and all later operational gates
remain open. No P3/V1/P9 upgrade; broker HARD_DISABLED/LIVE LOCKED.

Earlier checkpoint, superseded above:
2026-10-07: final guarded broad1217 passed,2333 warnings,462.45s; zero protected
attempts/forbidden modules. No phase upgrade. Manual configured-DEMO sign-in
diagnostic authorization remains unanswered; no economic action or broker unlock.

2026-10-06: startup confirmation handshake passes187 focused/1215 broad tests.
Actual cancelled/modal-free SDK retry still reports IPC timeout. No native account
qualification, economic action, phase upgrade or broker enablement. Bounded
official SDK6231 comparison also timed out after confirmed Cancel/modal-free UI.
Root cause UNKNOWN. Updated freshness diagnostics preserve all gates;37 focused
tests passed, final broad1217 above. Manual sign-in diagnostic authorization
requested, not performed. Do not call the dialog the sole remaining blocker.

2026-10-05 current-profile V1 closure is the authorized task. ADR-022 accepts the
cooperative current-user boundary, not actual broker qualification. Ordered gates:
review dirty work -> reproduce/fix/regress -> baseline commit -> current-profile
operator audit -> first MANUAL demo -> rejection/HALT/restart -> strategy/WhatsApp
operational routing -> broker-backed P9. No new P8/P10 work or phase upgrades.
Legacy dedicated-user tooling is preserved/deprecated, never redeployed.

Current-profile operator increment:185 focused/1213 broad fixture tests pass.
Actual host prechecks pass; SDK initialization returns IPC timeout before DEMO
attestation. The subsequent Cancel-only diagnostic with two SDK versions failed;
no P3/V1/P9 completion or DEMO_ENABLED status. Older counts here are dated evidence.
Manual economic test and later strategy/WhatsApp/P9 gates remain blocked in order.

2026-10-02 owner redirection: separate NexusAIDemoOp account/profile, dedicated
tasks and attestor/runtime removed and absence verified. Current-profile-only
work under ADR-021; no replacement account authorized. Project/config preserved.
P3 operator remains pending, MT5 demo NOT_RUN, execution HARD_DISABLED. No phase
status upgrade or silent substitution of shared-terminal isolation. Evidence:
Audits/P3-OPERATOR-PROFILE-REMOVAL.md.

2026-10-02 source follow-up: approved sender and exact REDACTED_SOURCE announcement
IDs verified against the real restored WhatsApp client;32 connector tests passed.
This resolves identity discovery only, not live intake/delivery or broker gates.
See Components/V1-WHATSAPP-SOURCE-IDENTITY.md. Phase statuses remain unchanged.

2026-10-02 bounded V1 setup: WhatsApp login-first client reached ready; forwarding
and broker execution remain off.13 connector tests pass; dependency audit0 known
vulnerabilities. USD100 is owner-reported only; existing percentage risk and1.50
safety floor unchanged. Frozen strategy proposals remain nominal2R. No automatic
one-week rotation/promotion, phase closeout or MT5 qualification follows. See
Components/V1-DEMO-100-SETUP.md. Existing phase statuses below are unchanged.

Current scope authority: ADR-018 (V1 owner task, 2026-09-24); implementation
checkpoint 2026-09-28 is V1_PARTIAL. This amends dependencies, not risk policy or
operational qualification. P5/P6/P7 remain frozen; P8 research is now authorized
and verified under accepted ADR-005 / owner task 2026-10-01; full P9 remains
independent of P8. Manual/WhatsApp non-submitting integration, disabled deployment
registry and monitoring UI are bounded progress, not operational completion.
Exact remaining work: Components/V1-OPERATIONS.md; Audits/NEXUSAI_V1_ACCEPTANCE.md.

Preserved foundation: accepted ADR-012 (2026-09-13). P3 engineering is complete only
within non-operational/fixture/native-normalization scope; operator demo verification
is DEFERRED / PENDING. Combined P3 is not fully complete. Broker execution remains
HARD DISABLED. The subsequent owner-authorized P4 implementation is now verified
within non-executing fixture scope; its closeout is recorded below. Subsequent P5
data work is now VERIFIED_COMPLETE under ADR-017's alternative-provider scope.
Accepted ADR-013 keeps strategy replay in P6; P6 is now VERIFIED_COMPLETE in
non-executing research scope (2026-09-22). P7 is now VERIFIED_COMPLETE under the
owner-locked ADR-006, including the additional read-only Arena exit gate. ADR-005
was explicitly resolved for the owner's P8 research task on 2026-10-01. Earlier
P5 blockers below are preserved dated checkpoints, superseded by the closeout here.

| Phase | Name | Status | Blocking condition |
|---|---|---|---|
| P0 | Governance, Preservation, V2 Baseline | VERIFIED_COMPLETE | Repo-local gates verified; see P0-CLOSEOUT.md |
| P1 | Canonical Lifecycle Integration | VERIFIED_COMPLETE | M3 exit gates passed 2026-09-10; M2 COMPLETE_WITH_RECORDED_INCIDENT; see Audits/P1-M3-EXIT-GATE.md |
| P2 | Authoritative Safety Engine | VERIFIED_COMPLETE | Non-executing fixture gates passed 2026-09-11; Components/P2-SAFETY-ENGINE.md |
| P3 Engineering | MT5 Demo Execution & Reconciliation Engineering | VERIFIED_COMPLETE | Non-operational/fixture/native-normalization scope ONLY; no actual broker qualification |
| P3 Operator Verification | Isolated Operator Demo Verification | DEFERRED | PENDING machine/account qualification and actual isolated demo evidence |
| P4 | Source Adapters & Provenance | VERIFIED_COMPLETE | NON-EXECUTING; 49 focused / 684 broad tests; Components/P4-SOURCE-INTEGRATION.md |
| P5 | Real Market Data & Deterministic Data Interface | VERIFIED_COMPLETE | EV public real-data qualification; all six have a common 86.83-day range; bounded native-H1/H4 scope |
| P6 | Strategy Research Library | VERIFIED_COMPLETE | NON-EXECUTING; 360 reproducible real-data runs, 86 focused / 935 broad tests; Audits/P6-CLOSEOUT.md |
| P7 | Strategy Tournament + Arena | VERIFIED_COMPLETE | 570 reproducible replays; 996 broad tests; real-evidence desktop/mobile UI proof; no qualifiers required |
| P8 | Optional ML / imitation / Kronos research | VERIFIED_COMPLETE | ADR-005; negative/insufficient/blocked-runtime dispositions accepted; no model execution qualification |
| P9 | Full Monitoring & Evidence Dashboard | IN_PROGRESS | Bounded observer projections/UI proven; full native instrumentation and performance still missing; no P8 dependency |
| P10 | Forward Demo Qualification | DEFERRED | Forward qualification requires P3 OPERATOR VERIFICATION + full P9; not completed by an export |
| P11 | Advanced Research / RL | DEFERRED | OUT_OF_V1_SCOPE |

## P7 Owner-Authorized Exit Gate (2026-09-22)

- [x] Versioned locked methodology and frozen eligible P6 rules.
- [x] Six qualified P5 pins; chronological aligned70/30; no shuffle/OOS tuning.
- [x] Full metrics and all ten explicit gates for every eligible cell.
- [x] Reproducible classification, uncertainty/sample exclusions, no pooled rescue.
- [x] Instrument/frame, early/late, remove-best/worst and supported cost stress.
- [x] Correlation calculation tested; actual qualified-pair analysis not applicable.
- [x] Exact run/result identity, immutable publication, repeat and restart proof.
- [x] Persisted chronological projection and authenticated read-only APIs.
- [x] Integrated Arena: real evidence, controls, curves, retained failures, gates,
  inspector, final state, filters and desktop/mobile verification.
- [x] Focused / broad regression and frontend build/browser verification passed.
- [x] No execution qualification, broker access, P8 code or threshold relaxation.

Zero strategies qualifying does not block the approved P7 exit gate. Exact
evidence and bounded limitations: Audits/P7-CLOSEOUT.md. That checkpoint did not
authorize P8. The newer explicit P8 owner task and closeout below supersede its
next-phase statement. All historical phase notes below remain.

## P8 Owner-Authorized Exit Gate (2026-10-01)

- [x] ADR-005 three-track separation and temporal policy locked.
- [x] Qualified/pinned read-only Track A dataset and exact outcome lineage.
- [x] Causal feature whitelist/reconstruction and resolved-at-cutoff enforcement.
- [x] Deterministic expanding folds; train-only transforms; fixed operating points.
- [x] Prior/logistic/tree evaluation and strategy-ID diagnostic, full failure metrics.
- [x] Track B real archive audit and honest INSUFFICIENT_DATA; no invented negatives.
- [x] Kronos source/runtime feasibility audit; exact blocker, no fabricated inference.
- [x] Persistent research-only registry/artifact hash/restart/replay/fault safeguards.
- [x] Exact repeated fit/prediction identity; no authoritative synthetic source data.
- [x] P9 observer projection and existing dashboard desktop/mobile proof.
- [x] Focused/relevant/broad credential-free regressions; preserved P5/P6/P7 evidence.
- [x] No economic permissions, strategy activation, P2 changes, serving or retraining.

Positive prediction results, qualified filters, trained human imitation and working
Kronos are not prerequisites under the owner's explicit P8 completion rule.
PASS_THROUGH / HUMAN_IMITATION_PARTIAL / KRONOS_RUNTIME_BLOCKED are retained.
P9 remains IN_PROGRESS under its original full obligations; no P10 advancement.
See Components/P8-ML-RESEARCH.md and Audits/P8-CLOSEOUT.md.

## P0 Exit Criteria (Preserved)

- [x] V2 specification approved at governance level.
- [x] Old Master Prompt marked historical/non-authoritative.
- [x] Baseline Git commit/tag confirmed recoverable **in the user's repository**.
- [x] Updated Obsidian control files committed **in the user's repository**.
- [x] Credential/secrets exclusions verified **in the user's repository**.
- [x] Required ADRs resolved for early phases; ADR-005/006 intentionally DEFERRED.
- [x] `CURRENT-STATE.md` retains the audited evidence baseline.

### P0 closeout status

**P0 VERIFIED_COMPLETE, 2026-09-10.** Repo-local baseline
`ae800c743bb7216b666dfca11c4751fb79022282` contains the governance controls.
Post-commit recovery, control tracking, ADR, exclusion and credential-free
verification gates passed; evidence and limits are in `P0-CLOSEOUT.md` and
`Audits/P0-CLOSEOUT-AUDIT.md`. P1 became READY at that P0 checkpoint. The separately
authorized M1 work below does not unlock P2 or any later phase.

## P1 Milestones

- [x] M1 canonical lifecycle foundation: active factory/API, versioned source and
  intent contracts, persisted fixture decision/request lineage, replay/crash and
  regression tests. Final reviewed selection: 179 passed / 430 warnings.
- [x] M2 historical canonical bridge: COMPLETE_WITH_RECORDED_INCIDENT, accepted
  by the human owner on 2026-09-10. Review commit f32eb2b proves unchanged stored
  database contents and tested isolation; unmeasured access-time effects accepted.
  Incident evidence remains in Audits/P1-M2-OPERATOR-DB-IMPACT-REVIEW.md.
- [x] Human disposition received; no operator database repair authorized or needed.
- [x] M3: existing five P1 exit criteria verified; no additional implementation
  needed. Broad guarded suite 218 passed / 1010 warnings; focused P1 suite
  94 passed / 754 warnings. Evidence: Audits/P1-M3-EXIT-GATE.md.

M1 alone was not full P1 completion. M2 human acceptance and M3 verification now
close P1. See `Components/P1-LIFECYCLE-MAP.md` for exact scope and historical
evidence. Passing fixture infrastructure is not broker qualification.

## P1 Exit Criteria

- [x] Canonical source/signal/intent lifecycle wired into active app without broker execution.
- [x] Exact IDs survive restart/replay.
- [x] Provenance/account identity preserved.
- [x] Duplicate same-symbol signals remain distinct.
- [x] Negative/replay/crash tests pass.

Verified against existing source and fixture tests at f32eb2b; no application,
test, migration, policy or dependency changes were needed for M3. Exact criterion
to source/test mapping and limitations: `Audits/P1-M3-EXIT-GATE.md`.
Trading remains HALTED / NOT QUALIFIED. P2 is recommended next, not started.

## P2 Exit Criteria

- [x] One authoritative pre-execution gate.
- [x] Direction-aware geometry + approved R:R policy.
- [x] Finite/action validation.
- [x] Persistent HALT enforced at economic boundary.
- [x] Risk reservations prevent concurrent over-allocation.
- [x] Compliance cannot race execution.
- [x] Approved risk/freshness ADRs implemented and tested.

P2 closeout: 79 focused P2 tests, 94 P1 regression tests, 297 broad fixture-safe
tests passed. Exact mapping and limitations: `Components/P2-SAFETY-ENGINE.md`.
No broker submission/connection or operator migration is qualified. P3 not started.

## P3 Exit Criteria

### Current Split Under ADR-012

**P3 ENGINEERING = VERIFIED_COMPLETE** within non-operational/fixture/native-
normalization scope. Durable identities, crash/retry/ambiguity handling, partial
fills, revision-aware evidence, native-shaped projection and duplicate prevention
retain their existing bounded proof. See TESTING.md and P3 component/audit notes.

**P3 OPERATOR DEMO VERIFICATION = DEFERRED / PENDING.** Actual demo attestation,
machine/account isolation and broker-verified end-to-end execution remain unproven.
The unchecked demo criterion below is retained and mandatory, not moved into the
engineering completion claim. P3 must not be presented as fully verified.

Broker execution remains HARD DISABLED for normal application and P4-P9 paths:
`Signal -> Canonical lifecycle -> P2 Safety -> ExecutionRequest -> BROKER EXECUTION DISABLED`.
No component may bypass this block or invoke the separate operator tooling.
Operator verification must complete before ordinary MT5 demo execution, P10,
or any live-readiness work. The separately authorized isolated verification step
retains every original gate; this task neither authorizes nor runs it.

### Preserved Earlier Exit Evidence

The dated statements below retain the original combined-P3/P4-blocked checkpoints.
Their scheduling status is superseded by ADR-012, not their test evidence or limits.

2026-09-13 update: concrete host/connector/native P2 providers and mandatory
pre-flight implemented; 604 broad guarded tests passed. Metadata pre-flight FAIL:
configuration, risk-basis and cost-basis files missing. No broker connection/action.
Native DEMO exit evidence remains missing; no checkbox or later phase is unlocked.
Audit: Audits/P3-NATIVE-OPERATOR-QUALIFICATION.md. Statements below are prior evidence.

- [ ] MT5 demo-only account attestation.
- [x] Durable client request identity (fixture/process-crash verified).
- [x] Retry/crash/ambiguous-result reconciliation tests (fixture verified).
- [x] Partial fill/order/deal/position reconciliation (canonical/native-shaped fixtures; operator demo unverified).
- [x] No duplicate economic action in controlled fault tests (fake broker; not native exactly-once proof).

Owner-authorized P3 is PARTIAL: 104 focused / 401 broad tests pass, but native
snapshot normalization, operator isolation and actual demo end-to-end evidence
remain outstanding. Default application cannot dispatch to native MT5; explicit
app execution is FIXTURE-only. P4 remains BLOCKED. See
Components/P3-EXECUTION-RECONCILIATION.md and TESTING.md. Earlier phase statements
above are preserved as dated history, not current P3 status.
Verified implementation commit: 87229215534c00ae5f16997af7bff16df1e512fb; not pushed.

2026-09-12 P3 follow-up: native implementation stopped at the owner's explicit
semantic-conflict gate. Existing immutable deals safely reject native-style
same-ID revisions, but cannot represent them as current broker truth. Five added
characterization tests do not qualify a native normalizer. Resolve the human
disposition in Audits/P3-NATIVE-EVIDENCE-COMPATIBILITY.md before continuing the
reader; no P3 exit checkbox or later-phase authorization changed.

2026-09-12 subsequent ADR-011 work supersedes the decision-pending native stop above.
Append-only revision evidence and native normalization are now implemented; exact
fixture results are in TESTING.md and Components/P3-NATIVE-EVIDENCE.md. No actual
demo attestation/smoke proof was obtained. The unchecked P3 demo exit gate and P4
block remain; no broad native exactly-once or operational qualification is claimed.

2026-09-12 final demo preflight: the owner explicitly authorized a CONDITIONAL
operator test. Operational prerequisites were not proven; no connection or order
was attempted. See Audits/P3-DEMO-OPERATOR-PREFLIGHT.md for all ten gates and exact
remaining qualification work. Fixture regressions were rerun; results in
TESTING.md. P3 remains PARTIAL and the demo exit checkbox stays unchecked.

2026-09-12 subsequent operator-tooling work adds a fixed-location isolated ledger,
deferred connection gate, persistent one-test budget and exact minimum-volume
MANUAL/MARKET wrapper around existing P2/P3. No ordinary-app dispatch or policy
change. Machine isolation/native connector and actual safety-context qualification
remain missing; diagnostic NOT_QUALIFIED, no broker connection or trade. See
Components/P3-OPERATOR-VERIFICATION.md and TESTING.md. Demo checkbox remains open.

## Later phases

P4 VERIFIED_COMPLETE; P5 IN_PROGRESS, P6 follows P5, P7 follows P6, P8 follows P7 and P9 follows
P8, all NON-EXECUTING. P10 requires P3 OPERATOR VERIFICATION + P9. Readiness is
not completion or permission to start a phase within this amendment task.
Existing phase-specific semantics/quality gates still apply; ADR-005/006 remain
DEFERRED and must be resolved before dependent semantics are implemented.
No speculative expansion, broker activation or live-readiness authorization.

## P4 Exit Evidence (2026-09-13)

Existing source-phase requirements and the owner's P4 task are satisfied in the
explicitly allowed authenticated-adapter/non-executing scope:

- [x] MANUAL structured MARKET/LIMIT, explicit SL/TP, identity/provenance and authentication.
- [x] WHATSAPP_HUMAN trusted message boundary, raw/time/sender/group preservation,
  configured allowlists, deterministic parsing and configurable 600-second freshness.
- [x] NEXUSAI_STRATEGY contract with explicit ID/version, UNQUALIFIED and non-executing.
- [x] Existing P1-M2 archive/review lineage and historical economic firewall retained.
- [x] SCREENSHOT evidence reference/extracted signal boundary remains research-only.
- [x] Versioned common registry; unknown live sources reject; research cannot be enabled.
- [x] Lower-layer canonical, source, P2 and request checks; no safety bypass.
- [x] Replay/conflict/concurrency/restart and distinct-source lineage tests.
- [x] Approved requests cannot bypass persistent app/engine/SQL broker block.
- [x] Focused P4 and broad P3/P2/P1 fixture-safe regressions pass; evidence in TESTING.md.

P3 operator verification is unchanged: DEFERRED / PENDING. Live WhatsApp transport,
actual demo trading and operational deployment are NOT PROVEN and are not claimed
by this P4 source-adapter closeout. P5 is next, not implemented here.

## P5 Alternative-Provider Exit Evidence (2026-09-15, ADR-017)

P5 VERIFIED_COMPLETE. HistData is preserved, not forced through looser rules.
EV Trading Labs is the primary single-provider research dataset family.

- [x] Real public source exports for XAUUSD, XAGUSD and WTI, all years 2021-2025.
- [x] All six instrument/timeframe combinations have a common qualified range,
  2025-09-02T00:00Z to 2025-11-27T20:00Z, with zero unknown bins inside the range.
- [x] Native H1/H4 access and bid/ask aggregation consistency; no synthetic repair.
- [x] Deterministic dataset/qualification/calendar identity, complete raw receipts.
- [x] Bounded provider-specific session model; unknown/holiday uncertainty still
  breaks queries; no execution-calendar claim or HistData policy relaxation.
- [x] Version-pinned provider-independent research reader and replay/reopen proof.
- [x] Statistical HistData comparison recorded, including seasonal timing mismatch;
  no source merging, timestamp alteration or contract-equivalence assertion.
- [x] Kronos K-line representability/lineage verified; runtime remains P8.
- [x] 165 focused P5 / 849 broad guarded tests pass; no broker/operator access.

Full five-year uninterrupted qualification, exact oil roll construction, validated
volume semantics and independent tick completeness are NOT claimed. These bounded
limitations do not prevent the owner's minimum multi-month native-bar P5 gate.
Evidence: Audits/P5-ALTERNATIVE-PROVIDER-CLOSEOUT.md. P6 READY; implementation not
started. P3 operator gate and HARD DISABLED broker execution remain unchanged.

## Preserved P5 HistData-First Follow-up (2026-09-14, ADR-014)

Latest 2026-09-15 ADR-016 empirical follow-up supersedes the official-calendar
dependency below. All three calendars are derived from 51 complete observed weeks;
six calendar-bound 1H/4H datasets are rebuilt with 100% expected-minute completeness.
Longest ranges remain ~29/~5/~3 days for gold/silver/WTI, not multi-month. P5 remains
PARTIAL and P6 BLOCKED. Exact residual gaps: Audits/P5-EMPIRICAL-FEED-CALENDAR.md.
No unknown-gap tolerance or trading-session eligibility rule was changed.


Subsequent ADR-015 session follow-up: Saturday-core market inference applied to
all nine datasets with zero observed closure conflicts. Session-aware query/replay
works but longest 1H/4H ranges remain 23h/20h for each instrument. No multi-month
exit gate passes. Daily/holiday/Friday-Sunday edge applicability and complete-bin
coverage remain unresolved. Exact blockers: Audits/P5-SESSION-QUALIFICATION.md.
P5 stays PARTIAL; P6 NOT_AUTHORIZED/BLOCKED. Broker execution HARD DISABLED.


All 36 instrument/month combinations are present in the raw archives. Zero parser
rejections; 60 identical duplicate rows per instrument are coalesced. Corrected
over-exclusion retains all canonical bars; new qualification versions preserve
old evidence. Annual M1 plus rebuilt 1H/4H and 117 annual/monthly coverage reports
are recorded in Audits/P5-HISTDATA-FIRST.md. Focused 99 / broad 783 tests pass.

Remaining P5 gate: verified applicable session/holiday classification and
session-aware multi-month qualification. No numerical gap budget or closure is
invented; existing complete-bin aggregation remains conservative. P6 BLOCKED.
The earlier second-provider/credential prerequisite is superseded, not required.

## Preserved P5 Closeout (2026-09-14, ADR-013)

Follow-up: coverage metrics are now persisted for all 15 existing datasets. No new
continuous range qualifies. Dukascopy bulk retrieval needs a permitted export or
scoped AWS Requester Pays authorization/budget; bucket instrument availability and
historical calendar/roll evidence still require verification. No source merging or
flag-clearing. See Audits/P5-PROVIDER-ACCESS-AND-COVERAGE.md. P5 remains IN_PROGRESS.

P5 remains PARTIAL, P6 BLOCKED. Strategy replay is now a P6 exit gate, not P5.
No strategy is implemented or authorized by this data task.

- [x] Precise canonical data, immutable storage/identity and research proxy provenance.
- [x] Deterministic quality classification, append-only qualification and bounded exclusions.
- [x] Exact version/range 1H/4H interface; ordered candles, provenance and quality metadata.
- [x] Preserved REAL annual 2021 archives processed for all three instruments; no synthetic candles.
- [x] Re-ingestion/reopen/repeated queries; contiguous-gap rejection and explicit segmented acceptance.
- [ ] Meaningful continuous multi-month qualified coverage for every instrument/timeframe.
  Six annual views qualify ONLY for their retained segments, not full-range replay.
  USOIL 4H retains 26 bars across nine months; longest segment is two bars.
- [ ] Resolve source/session/discontinuity evidence or acquire corroborated replacement
  history without weakening quality controls. Latest-period coverage also unproven.

Exact coverage and query results: Audits/P5-CLOSEOUT.md. P3 operator verification
remains DEFERRED; broker execution HARD DISABLED. P6 remains blocked on P5.

## P6 Additional Exit Gate (ADR-013)

- [x] Known strategies produce reproducible replay results from pinned qualified
  real datasets: 360 study cells / 4,556 research trades; exact repeat/reopen proof.

### P6 Owner-Authorized Research Closeout (2026-09-22)

- [x] Deterministic strategy contract and precise versioned definitions.
- [x] Qualified P5 pins; chronological features, splits and closed-only H4 context.
- [x] BID/ASK/cost-aware admission; valid explicit geometry and R>=1.5.
- [x] ADR-004 reconstruction, uncertainty/exclusion accounting and honest metrics.
- [x] Immutable atomic research ledger and stable P7 artifact interface.
- [x] All 30 concepts classified: 20 ready, 6 experimental, 3 underdefined,
  1 volume-disabled. No fabricated definitions or volume interpretation.
- [x] Focused 86 and broad 935 tests pass; execution remains HARD DISABLED.

The owner explicitly allowed limited/negative/zero samples and underdefined
concepts to remain documented rather than inventing statistical qualification.
Thus this satisfies P6 research engineering, not an unapproved minimum-trade or
profitability gate. ADR-006 stays deferred, to be resolved before P7 qualification.
No P7 code was implemented. Full evidence: Audits/P6-CLOSEOUT.md,
Audits/P6-RESEARCH-RESULTS.json and Components/P6-STRATEGY-RESEARCH.md.

## Preserved P5 Data Foundation Checkpoint (Before ADR-013)

Prior P4-closeout P5 READY wording is historical. Current P5 is IN_PROGRESS,
not VERIFIED_COMPLETE. This data-only task does not authorize strategy work.

- [x] Canonical precise data, versioned mappings, raw provenance and immutable store.
- [x] Dataset identity, ordered range interface, retry/correction/restart behavior.
- [x] M1 to UTC 1H/4H complete-bin resampling; explicit gaps/questionable evidence.
- [x] Bounded real sample for all three instruments; fixtures and Kronos source note.
- [ ] Resolve/validate discontinuity flags before research qualification.
- [ ] Establish required broader history and session/contract-basis evidence.
- [ ] Original specification gate: known strategy produces reproducible replay
  from an immutable real dataset. Not authorized under current no-strategy scope;
  explicit bounded authorization or governance disposition required.

No accepted ADR was amended. P6 stays BLOCKED; P3 operator verification remains
DEFERRED. Exact evidence/limits: Components/P5-MARKET-DATA.md,
Components/P5-REAL-DATA-EVIDENCE.md and TESTING.md.
