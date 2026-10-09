# P8 Research Closeout - 2026-10-01

Verdict: **VERIFIED_COMPLETE**, bounded to the owner's fourteen research exit
criteria. Positive models, qualified imitation and operational Kronos are expressly
not required. V1_PARTIAL / P3 operator NOT_RUN / broker HARD_DISABLED are unchanged.

## Exit Evidence

| Criterion | Disposition | Evidence |
|---|---|---|
| ADR-005 temporal policy locked | PASS | Accepted P8-RESEARCH-1.0; decision index and explicit ADR-018 supersession |
| Track A dataset/label pipeline | PASS | 228 pinned primary runs;3,447 trades;2,499 WIN/LOSS;948 excluded |
| Track A evaluated | PASS | Three expanding folds,1,403 resolved tests, full model/threshold/slice metrics |
| Leakage tests | PASS | Closed-bar reconstruction, strict feature schema, future/outcome/P7-gate rejection |
| Chronological validation | PASS | Resolution<=cutoff, crossing labels censored, test sets nonoverlap |
| Baselines evaluated | PASS | Prior/logistic/shallow tree, with/without ID, portable JSON inference replay |
| Historical human audit | PASS | Owner's ZIP784 records;42 candidates;16 usable shapes; no private DB |
| Human evaluation/disposition | PASS | Descriptive conditional behavior; predictive INSUFFICIENT_DATA |
| No fabricated human negatives | PASS | negatives0; no trade/no-trade classifier or claimed verified outcomes |
| Kronos tested OR exact blocker | PASS(BLOCKED_RUNTIME) | Actual missing torch; source/pin/public metadata and bounded resource evidence |
| Model registry | PASS | Hash-bound inert JSON, immutable SQLite, crash/retry/restart/concurrency tests |
| Reproducibility | PASS | Exact repeated fit/artifact/prediction equality; safe persistent/restart reads |
| Research-only models | PASS | Registry/projection execution_eligible=false; no execution composition |
| Relevant regressions | PASS | Final1,101 passed;75 focused P8 cases included; guarded allowlist |

## Identities And Preservation

Public result: `P8-RESEARCH-RESULTS.json`.
Result ID:2e0a2c49a77b6fbb4d2ce0dcc4faa0cec034569a80e8f2bb63bed3dbc3335563.
Feature schema:c6538e904d270972b6fe4ecc31b339993a5a5bae1f8dcd96fa9d4b979b362a43.
Evaluation policy:949dfb51be094c3c27482e3ec7059d2d7c5e127de8255d01970937e448816083.
Labelled input rows:d4eb9f113b418cbac671a2c5a2a8426c69753aa9e1532b015593f3c4b4b4d955.
Prediction identity:045708f2a009c93fc63ce31e7dbb80e68d581a82a3b69ceaf2fbe23978fd484f.
P5/P6/P7 owned DB SHA256 before/after:
8a155ca5dca4b66472a6ce626236213e893e958bef943eebab0c639cd6dba2ae.
Runtime assertions compare SHA256,size,mtime before/after; no net change detected.
This does not assert filesystem access time is unchanged or OS-level isolation.
Frozen P5/P6/P7 source/results are not modified. No operator database is opened.

The17 referenced current registry entries are15 fold models and two track audits;
earlier/interrupted artifacts and aggregate evidence remain append-only history.
No deletion was used to erase the initial failed checks. No trained artifact or raw
human data is staged; owned research root is ignored. Public result carries only
audited statistical evidence and inert references, no phone/sender/credential data.

## Negative Outcomes

No RESEARCH_QUALIFIED_FILTER. Logistic without ID(descriptive best learned AUC)
.527548 AUC / .280869 AP / .205022 Brier; baseline Brier lower in every fold.
At the predeclared .50 threshold,125/1,403 retained(8.91%); expectancy remains
negative(-.009300R). Lower resolution-order research drawdown is not a portfolio
qualification and retaining very few observations does not establish usefulness.
PASS_THROUGH is deliberate; no threshold was selected from test profitability.

Human predictive context is absent and UTC semantics unqualified. No supervised
imitation was trained and no negative signal/no-signal examples were invented.
Kronos forecast/baseline comparison did not run. Public mini availability is proven,
not checkpoint loading; source pins and bounded dependency budget block runtime.

## Verification And Remaining Scope

TESTING.md records final backend/frontend/browser evidence and intermediate failed
checks. Browser desktop1440x1000/mobile390x844 passed seven-page navigation,
P8 projection, no horizontal overflow, manual HALT rejection, zero attempts,
disabled registration, export, preserved Arena and lock; page errors0.
This uses a fresh temporary fixture account/database and public P8 research,
not a normal operator store. Temporary preview processes are stopped afterward.

No MT5, economic action, credentials, live WhatsApp, new strategies/providers,
tournament policy changes, ML serving/retraining/deployment, P10/RL or Git push.
Next: remaining original P9 observer obligations. P3 machine/account/risk-history/
cost qualification remains a separate operator gate; P8 does not resolve it.

Git: bounded P8 implementation/evidence is committed separately from the prior
V1 checkpoint. The closeout commit is identifiable by this audit's Git history;
do not insert a circular self-hash into its own contents. README_SETUP.md remains
untracked/untouched.
