# ADR-005 — ML Responsibility

Status: **ACCEPTED / LOCKED**, 2026-10-01. Policy: **P8-RESEARCH-1.0**.

## Authority And Scope

The owner's NEXUSAI P8 Advanced Intelligence Research task explicitly authorizes
three separate research tracks. This supersedes ADR-018's P8 deferral ONLY;
P5/P6/P7 remain frozen, P9's independent obligations remain, P3 operator
qualification is not advanced and all broker/live permissions are unchanged.
No ML execution responsibility was authorized during P0-P7 and none is granted here.

Separate responsibilities are now locked:

- A: profitability / trade quality from qualified P6 research WIN/LOSS outcomes.
- B: conditional historical human behavior, not parser acceptance or bot outcomes.
- C: Kronos forecast research with separately evidenced runtime and evaluation.

Labels, evaluations and qualification claims MUST NOT be conflated.

## Temporal Policy

- Feature availability <= signal time, using only completed bars and closed context.
- Future outcomes are labels only; entry realized on the next bar, exits, realized R,
  duration, resolution time, P7 rank/gates and future indicators are forbidden inputs.
- WIN=1 and LOSS=0 only. Exclude AMBIGUOUS, UNKNOWN, CANCELLED, BREAKEVEN, TIMEOUT.
- A training row requires resolution <= cutoff AND signal < cutoff.
- Exact broker/barrier timestamps are retained where supported. Otherwise use the
  conservative terminal interval END, never an invented intrabar timestamp.
- Expanding chronological folds; no shuffle, no OOS tuning. Preprocessing fits
  training only. Outcomes unresolved by the train/test window endpoint are censored.
- Primary probability threshold .50; .60/.70 predeclared diagnostics, not tuned on
  held-out profits. Immutable feature/label/model versions and complete lineage.
- Reused short research history and overlapping strategy events do not become
  independent observations merely because trade IDs differ.

## Qualification

The owner's AUC >= .58 requirement is necessary, not sufficient. Meaningful sample,
baseline improvement, multi-fold consistency, usable coverage, calibration, trading
comparison and no leakage must all be supported. No invented numeric qualifying
coverage/sample floor. Technical minimums for computing baseline fold metrics are
versioned engineering guards, not new qualification policy. PASS_THROUGH/DISABLED
are correct when any qualification requirement is unproven. Positive ML results,
successful imitation and operational Kronos inference are not P8 exit prerequisites.

Human behavior is conditional on an issued signal. Never fabricate no-signal
negatives or verified outcomes. Unqualified date/UTC/context remains insufficient
for predictive evaluation. SL/TP geometry must not be used to trivially reveal
the direction label. Historical sources cannot execute.

Kronos requires an isolated compatible runtime/checkpoint pair, known context and
horizon, chronological simple-baseline comparison, explicit missing-volume handling
and dataset identity. Missing dependencies/unsupported pins or bounded resource
limits must be recorded as KRONOS_RUNTIME_BLOCKED, not a negative forecast result.

## Current safe default

Profitability/imitation ML remains disabled for execution. Parser/acceptance labels are not profitability labels.

## Registry And Boundary

Persistent registry is research-only, separate from lifecycle/operator databases.
Artifacts are hash-verified JSON, not executable pickle. No automatic retraining,
serving, activation or economic request generation. P9 reads a bounded evidence
projection only. Future use would still require the canonical P1 -> P2 -> P3 route
and separate authorization; no such route is enabled here.

Implementation/evidence: ../Components/P8-ML-RESEARCH.md.
