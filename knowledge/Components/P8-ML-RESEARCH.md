# P8 Advanced Intelligence Research

Status: **VERIFIED_COMPLETE within research-only scope**, 2026-10-01.
Authority: accepted/locked ADR-005, owner's P8 Advanced Intelligence Research task.
No model, human archive or forecast has execution authority. Broker execution
remains HARD_DISABLED; P3 operator/demo verification remains outstanding.

## Inputs And Lineage

The read-only adapter opens the owned `research/p5-market-data/market-data.sqlite3`
with SQLite URI `mode=ro` and `PRAGMA query_only=ON`. It never instantiates the
schema-writing P5/P6 constructors. It verifies P7 result/configuration identities,
P6 artifact/configuration pins, P5 dataset/qualification/provenance/selected-bar
hashes, provider semantics and qualified segments. No P5/P6/P7 research is rerun.

Only the 228 primary development/OOS replay references from 114 eligible P7 cells
are consumed. Original P6 runs, early/late replays and cost-stress repetitions are
not pooled as new labels. These are distinct research trades, NOT independent
market events or economically shared-capital positions.

3,447 trades: WIN655 / LOSS1,844 / TIMEOUT836 / UNKNOWN108 / AMBIGUOUS4.
WIN/LOSS labels: **2,499**. Excluded:948. No broker-close or parser-acceptance labels.
Lineage retains research_trade_id, signal_id, run_id, dataset/qualification IDs,
strategy version, instrument/timeframe/family, signal time, conservative resolution
time, outcome evidence hash, label-policy version and feature-schema ID.

Full labelled rows and OOS predictions are content-addressed in the ignored owned
P8 root. Public audit publishes counts by instrument/timeframe/strategy/family/month,
class balance, hashes and evaluation, not raw human messages or credentials.

## Feature Contract

`p8-signal-features-v1`: 15 numerical columns and five categorical columns.
Numeric: RSI14/RSI2, P6 rolling ADX/DI difference, stochastic, Williams, CCI,
ATR/reference, EMA20/50 distance/reference, MACD/reference, closed-bar bid/ask
spread/reference, intended reward R, UTC signal hour and weekday.
Categories: instrument, timeframe, direction, family, strategy ID.

Closed-bar P6 feature snapshots are reconstructed causally and compared exactly
with the frozen source signals. Signal content hashes and source identity are
checked. Next-bar execution entry, exit, realized R, outcome, holding time,
resolution, P7 ranking/gates and future candles are not predictor columns.
Unknown/non-finite/extra feature fields fail validation. Closed H4 context cannot
postdate the signal. Missing numerical values use train-only median imputation
plus missing indicators, with all-missing columns retained; scaling and one-hot
categories fit TRAIN ONLY. Unknown test categories do not refit encoders.

The schema is hashed and persisted. Label policy `p8-resolved-win-loss-v1` means
WIN=1, LOSS=0; all five other ADR-004 outcomes are excluded. Exact terminal times
are used only when evidenced; otherwise the interval END is the availability time.
Labels unavailable at a fold cutoff cannot train that fold.

## Chronological Design

Pinned common P5 period: 2025-09-02 00:00 through 2025-11-27 20:00 UTC exclusive.
Three expanding elapsed-time folds: initial40%, then20% each, boundaries floored
to four-hour UTC alignment, final boundary exact. No shuffle or parameter tuning.

| Fold | Training cutoff UTC | Test end UTC | Train rows | Resolved test rows | Crossing train exclusions |
|---|---|---|---:|---:|---:|
| 0 | 2025-10-06 16:00 | 2025-10-24 00:00 | 1,022 | 552 | 14 |
| 1 | 2025-10-24 00:00 | 2025-11-10 08:00 | 1,588 | 341 | 25 |
| 2 | 2025-11-10 08:00 | 2025-11-27 20:00 | 1,954 | 510 | 35 |

Train signals are strictly before cutoff; resolution equality passes. Test
signals are in the half-open test range AND resolved by its endpoint. Labels
crossing test end are censored, not supplied early. Test rows never overlap folds.
The elapsed-time split is not a randomly stratified split or the P7 70/30 split.

Metric-computation minimums: train100 /20 per class; test50 /10 per class.
These fixed engineering guards do NOT establish statistical independence or add
qualification thresholds. Single-class rank metrics are null/NOT_APPLICABLE.
The short reused P6/P7 period cannot become a fresh unseen holdout by renaming it.

## Baselines And Results

Frozen seed314159. Constant training WIN prior, logistic regression(C1,max_iter2000),
and shallow tree(depth3,min_leaf20). Both learners are evaluated with and without
strategy ID. No major explanation dependency, grid search or final-test tuning.
Thresholds .50(primary), .60/.70(diagnostics) fixed BEFORE evaluation.
Versions: CPython3.14, numpy2.5.2, scipy1.18.1, scikit-learn1.9.1.
Optional research-only dependency pins: `backend/requirements-p8.txt`.

| Model | Pooled OOS AUC | Average precision | Brier | Retained at .50 |
|---|---:|---:|---:|---:|
| Logistic without strategy ID | .527548 | .280869 | .205022 | 125 |
| Logistic with strategy ID | .523220 | .276715 | .207004 | 128 |
| Shallow tree with/without ID | .511392 | .303553 | .210994 | 152 |

1,403 resolved test rows; class prevalence .255167. Prior Brier is lower than
each learned model in every fold. Logistic without ID AUC by fold:
.612790 / .423244 / .497856. Prediction does not collapse without strategy ID,
but neither variant establishes qualifying predictive power. Family, direction
and indicators can still encode rule membership: this is not a complete proof
against implicit strategy memorization. Pooled AUC is diagnostic only; fold
prevalence/calibration changes can distort pooled rankings.

Full ROC-AUC, AP, log loss, Brier, balanced accuracy, precision/recall/F1, confusion
matrices, calibration bins/ECE, prevalence and group slices are in
`../Audits/P8-RESEARCH-RESULTS.json`. Coefficients/association signs, native tree
importance and complete portable preprocessing/tree state are registered artifacts.
Associations/importance are NOT causal explanations.

At .50, the descriptive best learned AUC model retains125/1,403(8.91%).
Expectancy: -.303037R before vs -.009300R after; totalR:-425.160227 vs -1.162507.
Drawdown:425.160227R vs35.462683R; PF:.594305 vs.985595.
These are resolution-ordered INDEPENDENT research-trade sums, NOT account equity
or a realizable concurrent portfolio. Both comparisons exclude all censored/
non-WIN/LOSS outcomes equally; they do not characterize the full strategy universe.
Each fold and every fixed threshold remain visible, including tiny retained sets.

**PASS_THROUGH / ML_NO_MEASURABLE_VALUE** means no QUALIFYING incremental value
established, not proof that all possible ML is useless. AUC fails .58, baseline
proper scores are worse, calibration/coverage/independence are not qualified and
performance is inconsistent. No threshold/model is activated from test results.
Commission remains NOT_INCLUDED; unchanged P6 bid/ask plus modeled slippage applies.

## Other Tracks And Observer Integration

Track B: historical user-supplied ZIP,784 messages,42 candidates,16 usable shapes;
descriptive conditional behavior only. UTC/context/outcomes unqualified:
**INSUFFICIENT_DATA / HUMAN_IMITATION_PARTIAL**. See P8-HUMAN-IMITATION.md.
Track C: source and anonymous public metadata audited; actual torch import fails,
source pins incompatible with backend3.14; isolated3.12 core stack exceeds the
bounded optional128MiB download budget. **KRONOS_RUNTIME_BLOCKED**, not negative
forecast evidence. See P8-KRONOS-RESEARCH.md.

Persistent append-only research registry and restart/replay/tamper safeguards:
P8-MODEL-REGISTRY.md. Separate tasks/labels/statuses, no merged model verdict.
P9 reads only a bounded checksum-validated public result projection. Existing
Monitoring -> Intelligence research exposes status/schema/policy/model references.
No new model-serving endpoint or automatic training task was added.

## Reproduction And Limits

Run `scripts/p8_research.py` ONLY through TESTING.md's normalized audit guard.
`--audit-only` audits before fitting. Normal run fits twice and requires exact
artifact, result and prediction equality; portable JSON inference must match
sklearn at1e-12. Registry reads/retries/restart are verified. The P5 database's
SHA256,size and mtime are identical before/after; access-time effects are not claimed.
No production/operator store, `.env`, broker or live WhatsApp is accessed.
Negative outcomes, failed early checks and their fixes are retained in TESTING.md.

No prospective validity, broker costs, independent-power proof, human cloning,
Kronos inference, serving, retraining, strategy promotion or forward qualification.
Next: remaining P9 observer requirements under the V1 acceptance matrix; do not
start P10 or any economic execution before their existing operator gates.
