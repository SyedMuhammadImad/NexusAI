# P7 Research Tournament

Authority: accepted ADR-006, P7-RESEARCH-1.0. This module has no broker, account,
credential, lifecycle execution or ML dependency. Research qualification is not
execution qualification. BROKER EXECUTION remains HARD DISABLED.

## Contracts

`backend/core/rebuild/tournament.py` consumes the existing P5/P6 ResearchData and
ResearchLedger contracts. `scripts/p7_tournament.py` verifies the committed P5
evidence identity, pins all six dataset/qualification IDs, and loads each through
ResearchData.load. That loader rechecks the source content hash, qualification,
range, provenance and separate BID/ASK data. No provider-specific strategy logic.

The exact qualified UTC range is [2025-09-02 00:00, 2025-11-27 20:00).
The nominal elapsed-time 70/30 boundary is rounded down to 2025-11-01 16:00 UTC,
the common complete 4H boundary. Actual fractions are recorded. It is not a
70/30 randomized trade split or a bar-count split over sessions of unequal length.
Development and OOS replay independently with P6 flat-start/right-censor rules.
Features may warm up on earlier observations, never later observations.

Thirty catalogue concepts produce 180 instrument/timeframe records. Only the
20 frozen TOURNAMENT_READY strategies are admitted on supported frames: 114
evaluated cells. Sixty cells from the other ten concepts and six unsupported
H4 session cells remain EXCLUDED. Every admitted cell has independent development,
OOS, early-OOS, late-OOS and 10%-slippage stress replays. Each replay is computed
twice, validated, stored atomically in the P6 ledger and reread identically.

## Gates And Aggregation

All ten gates are explicit: SAMPLE, EXPECTANCY, PROFIT_FACTOR, WIN_RATE,
DRAWDOWN, AMBIGUITY, DEGRADATION, DATA_QUALITY, LEAKAGE, COST_ASSUMPTION.
Exact formulas/status precedence are in ADR-006. Data/cost/leakage integrity must
pass; no caller string or missing flag substitutes for verified true evidence.
Sample counts must be nonnegative integers; nonfinite performance values cannot
qualify; impossible finite fractions/ranges abort instead of becoming a winner.

Resolved sample and win-rate denominator exclude TIMEOUT. P6 priced expectancy,
PF and drawdown include priced TIMEOUT. UNKNOWN/AMBIGUOUS are excluded from PnL,
not assigned zero. Full denominators, reasons, dispositions and outcome counts
remain in each replay's metrics. Drawdown is sequential additive trade R, not
account drawdown. Sharpe is unavailable with an explicit reason, never a gate.

Statuses attach to strategy/instrument/timeframe cells, not a pooled portfolio.
By-strategy aggregation counts those statuses; no pooled trades rescue samples.
Qualified cells sort by OOS expectancy, PF and stable cell ID only for display.
No winners are required to close P7 engineering.

## Robustness And Diversification

OOS halves are independently replayed with the boundary rounded down to complete
4H. Removing the best/worst priced trade recomputes metrics in original order,
using the first chronological occurrence for ties. Cost stress doubles adverse
slippage from 5% to 10% of stop distance per side through the supported P6 model;
rejected admissions are retained. There is no parameter optimization or tuning.

Only qualified cells enter correlation. UTC daily realized trade-R is aligned;
dates with feed observations but no realized result may be zero, closure-only
dates are absent, and unresolved holding dates are excluded, not fabricated zero.
At least two common dates and nonzero variance are necessary for Pearson; counts
and insufficiency remain visible. Absolute correlation >=0.80 forms connected
clusters, including negative correlations. This is descriptive, short-sample
evidence, not statistical independence or shared-capital portfolio analysis.

## Persistence And Reproduction

Run identity hashes policy/version, all dataset identities, frozen catalogue,
engine versions, costs and split configuration. Result identity additionally
hashes all cell gates/metrics and replay artifact IDs. Additive research schema 8
adds immutable `p7_runs` only under the owned research root. Existing P5/P6 history
is untouched. Identical publication is idempotent; conflicting publication fails.
Fixture-labelled studies cannot enter the real research store.

Use the normalized protected-path audit guard in TESTING.md, replacing only its
pytest call with `import runpy; runpy.run_path("scripts/p7_tournament.py",
run_name="__main__"); code=0`. Never start the application or operator tooling.
The generated index is Audits/P7-TOURNAMENT-RESULTS.json. Its P6 replay IDs resolve
to full immutable signal/trade evidence in the research ledger. An interrupted
study can leave valid individual replays, but publishes no partial final index.

## Limits

SHORT_SAMPLE_RESEARCH_ONLY is mandatory. Commission is NOT_INCLUDED (P6 internal
EXCLUDED_UNKNOWN); financing, impact, swaps and executable broker sizing remain
unmodeled. These retrospectively selected dates were already used by P6, so this
is not a newly unseen prospective holdout. Canonical parameters were not tuned
on P7 OOS. Provider timing and WTI mapping limitations remain unchanged.
No result permits execution, P8 training, Kronos signals or broker qualification.

## Tournament Arena

The owner explicitly added the integrated Arena as a second P7 exit gate.
`tournament_projection.py` builds 89 UTC snapshots (daily plus exact split/end)
and 8,174 chronological events from persisted development/OOS replay trades.
No raw market bars are transmitted. Full projection is 27,012,105 bytes, stored
immutably by projection hash under the owned research root; a current manifest
and committed audit manifest bind it to the final P7 result. Retrying generation
recomputes identically and preserves old versions; publication uses atomic rename.

Only outcomes observed by a snapshot's timestamp enter its metrics. Intrabar
outcomes use their conservative interval end when exact time is unknown;
right-censored UNKNOWN arrives at the period boundary. No future label is moved
back to entry time. Intermediate gates are PENDING or advisory PASS/FAIL;
ACTIVE/AT_RISK are reversible research display states. Final elimination/status
occurs only at OOS completion, because ADR-006 does not authorize early stopping.

The app exposes authenticated GET-only `/api/core/tournament/summary`, `/snapshot`
and `/inspector`. Bounds: six fixed views, at most128 snapshots, latest40 events,
20 current strategy rows; no arbitrary file/run query. Source/result and projection
hashes are verified; missing/stale/corrupt evidence is unavailable, never synthesized.
The read path does not open an operator or research database. Trade/state computation
happens offline; the browser only renders backend metrics, gates, ranks and curves.

`frontend/src/TournamentArena.jsx` integrates with the existing authenticated
RebuildWorkspace hash router and both navigation bars. All20 eligible strategy
names remain visible initially; unsupported H4 cells are explicitly excluded.
Counts are for the selected instrument/frame, with a separate global final cell
summary. STRUCTURE correctly has zero tournament-ready entrants. No pooled winner.
Failed/insufficient records remain in the field/history. Correlation has an explicit
no-qualified-pair state instead of an invented visualization.

Reproduce projection with the TESTING.md guard replacing pytest with
`import runpy; runpy.run_path("scripts/p7_arena.py",run_name="__main__"); code=0`.
For local visual verification only, `backend/.venv/Scripts/python.exe -B
scripts/p7_preview.py` reuses that guard and starts a loopback read-only app on8000,
synthetic token `p7-research-preview`, new temporary fixture DB, no operator state.
Normal app authorization is unchanged. Start the existing Vite dev server on5173
and open `http://127.0.0.1:5173/#/tournament`. Never substitute real credentials.

The browser test `frontend/tests/tournament-arena.mjs` uses Playwright (bundled
runtime via P7_PLAYWRIGHT or an installed package) and a fresh headless Edge profile.
It never reads the user's browser profile. Outputs/screenshots are local ignored
research evidence. No UI/API action writes tournament results or submits an order.
