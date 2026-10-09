# P6 Research Closeout

Date: 2026-09-22. Branch: core-rebuild.
Baseline: fc344088572da4e8319bc1a28de1d1da583b052c (verified P5).
Scope: deterministic research only; no P7, broker, strategy execution or ML.
Unrelated untracked README_SETUP.md is untouched and excluded from the commit.

## Verification Matrix

| Owner exit criterion | Evidence |
|---|---|
| Deterministic replay | 360 study configurations, each recomputed identically; configuration/result content hashes |
| Qualified P5 consumption | exact dataset/qualification IDs, full content-hash validation, bounded ResearchDatasetReader queries |
| Explicit strategy classification | 30 catalogue concepts: 20 technically ready, 6 experimental, 3 underdefined, 1 volume-disabled |
| Deterministic ready definitions | versioned feature/rule parameters and positive BUY/SELL tests for all 26 implementations |
| Outcome reconstruction | ADR-004 barrier/gap/ambiguous/timeout/unknown cases, H1 refinement with both-side reconstruction |
| Cost-aware research | BID/ASK entry/exit, adverse slippage, inclusive1.5 reward/risk, explicit commission exclusion |
| Leakage protection | prefix/future mutation tests, closed context only, chronological flat-start/right-censored splits |
| Reproducible metrics | denominators/exclusions/zero runs/PF/drawdown tested; exact portable study index |
| Non-execution | no runtime wiring; P4 fixture denies mapped strategy admission and has zero P3 attempts |
| P7 result interface | ResearchLedger.read(run_id), immutable JSON result IDs, reopened equality and crash/retry proof |

Focused tests: **86 passed / 14.85s**. Broad P6/P5/P4/P3/P2/P1 plus preservation
regressions: **935 passed / 1447 warnings / 294.60s**. Both exit0; guard six
self-tests, zero protected/operator attempts and forbidden runtime modules[].
Failure history and exact reproduction procedure are in TESTING.md.

## Dataset Pins

UTC half-open range for every row: **2025-09-02 00:00 through 2025-11-27 20:00**.
Split: **2025-10-15 00:00**. H1 count1,445; H4 count389 per instrument.
Primary EV Trading Labs, BID with separate ASK. QUALIFIED_WITH_KNOWN_LIMITATIONS.

| Instrument / frame | Dataset ID |
|---|---|
| XAUUSD 1H | fbc58e02da92f01faf51d03b62515b06f1fc5f3a7b8c5bcfa0c0605f6674220e |
| XAUUSD 4H | c475e55d548f51300bbd4fe5ab502d2bcbc2f9ac606a317513ac38bc66198918 |
| XAGUSD 1H | 1f4d67a2ed1f7db36a60577d51f6203fe17b4ea8230113dfc1705782a6a6a908 |
| XAGUSD 4H | 827f905b9a22a76cb0635c73c9b3c22a41c435c4c6c826dc8b40dabf9933f8b6 |
| USOIL 1H | 1889257a8e67cf363dd2bdd67ee25ff9482b227ec2c89e13c30d2bbadd317d70 |
| USOIL 4H | e1c28463fcdc28055fd2ef203f8297c8e853ccf7f6c196bf331c261f13069612 |

Full qualification IDs, row/provenance hashes and per-run artifact IDs are in
P6-RESEARCH-RESULTS.json. HistData remains separate/preserved; no source splice.
Only actual P5 observations were used in this study; synthetic tests stay temporary.

## Research Interpretation

This is 360 independent strategy/instrument/timeframe/window experiments, NOT
a portfolio. Counts include the zero/disabled/unsupported combinations. No
parameter sweep or tournament selection. A high cell R total is not promotion.
Unknown commission is excluded; no broker lot sizing, swaps or account PnL.

The final-engine study measured 4,556 research trades: 878 WIN, 2,435 LOSS,
zero BREAKEVEN, 1,103 TIMEOUT, six AMBIGUOUS and 134 UNKNOWN. There are 77 zero-trade
cells and 80 negative-total-R OOS cells. Final metadata verification is below.
Exclusions are not assigned zero. Counts across overlapping experiments are not
independent real trades and must not be used as live trade-frequency evidence.

Illustrative OOS technically-ready cells, commission excluded:

| Cell | Trades | Priced | Total R |
|---|---:|---:|---:|
| Bollinger re-entry / USOIL H4 | 7 | 7 | +10.2693 |
| RSI2 / USOIL H4 | 10 | 10 | +9.1635 |
| MACD / XAUUSD H1 | 28 | 28 | +7.5899 |
| Outer Bollinger touch / XAGUSD H1 | 42 | 42 | -23.0662 |
| NY UTC breakout / USOIL H1 | 21 | 21 | -13.1517 |

Small samples and retrospective range selection prohibit durable-profitability
claims. Stochastic/Williams are redundant target concepts; 30 names are not 30
independent sources of information. Research variant definitions and all remaining
limits are in Components/P6-STRATEGY-RESEARCH.md and RISKS.md.

## Remaining Boundaries

ADR-006 remains DEFERRED: ranking/tie-break/degradation/minimum-trade/reset policy
must be resolved before P7 qualification implementation. No such policy is
invented by P6 technical readiness. P3 operator verification remains DEFERRED;
BROKER EXECUTION HARD DISABLED. No broker, secrets or operator DB access; no push.

## Final Evidence and Verdict

Final offline study exited0 with six guard self-tests, zero protected/operator
attempts and forbidden modules[]. Engine p6-replay-v3; explicit qualification
status and dual-sided price basis are in each run configuration and study pin.
360 recomputations matched exactly; all 360 persisted/reopened results matched.
Study report hash:
`fb3b794969e92554f35b8f85562446365b21442df5851ffb334a9a7567dd82d1`.

Earlier v1/v2 and pre-final-metadata v3 results remain append-only in the research
store and are not selected by the final index. v2 preserved known open-gap/timeout
timestamps; v3 also verifies full source content and explicit unsupported-frame
status. No prior research observation or P5 history was overwritten to improve
the result. No count derives from synthetic qualification or a failed test run.

**P6 VERIFIED_COMPLETE** in the owner's bounded research-engineering scope.
All ten requested exit criteria PASS. No unresolved P6 implementation blocker.
P7 qualification requires the ADR-006 human policy decision; P7 was not started.
The bounded P6 commit is the commit containing this audit (parent shown above);
the final response records its exact Git identity. No push is authorized/performed.
