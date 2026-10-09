# P7 Closeout - 2026-09-22

Verdict: **VERIFIED_COMPLETE**, research tournament AND owner-added Arena.
Baseline: `d058a64b57db16a53f6240e778842d0e58505ab9`, branch `core-rebuild`.
Implementation/evidence commit: the separate P7 commit containing this audit
(resolve with `git log -1 --format=%H -- knowledge/Audits/P7-CLOSEOUT.md`). No push.

## Exact Evidence

- Policy P7-RESEARCH-1.0, accepted ADR-006; frozen P6 versions/parameters.
- Policy hash: `3fdea357ff50c87af5bc54627dfc930bb2e29bc6208f10b9a31c09380b7011b7`.
- Run ID: `08e66bc00fecfcd8e670c2cae0d6ffce1cecf25d347e8c079378a77e4b9efede`.
- Result ID: `52964b443363f546d6e7f8fc93e90a03d74bc4a6c113056cbdd84f7a53c964d5`.
- Projection ID: `9b0ac820953bd6f812576784a6eda7047ecbee8dea564741c6b59a5444d9c7cf`.
- Exact six dataset/qualification/content/provenance IDs are in the result's
  configuration, not a floating latest-provider lookup.
- Qualified range [2025-09-02T00:00Z, 2025-11-27T20:00Z); split2025-11-01T16:00Z.
  Nominal70/30 rounded down to common4H; actual development fraction
  0.6986564299424184261036468330134357005758. OOS halves use the recorded4H boundary.

## Results

20 eligible strategies, 114 supported cells, 570 development/OOS/robustness
replay configurations. Each replay was recomputed identically, persisted and read
back. Final study rerun used the final tournament module; the earlier pre-review
study remains immutable but is not this closeout's result identity.

| Status | Cells |
|---|---:|
| RESEARCH_QUALIFIED | 0 |
| REJECTED | 1 |
| INSUFFICIENT_EVIDENCE | 113 |
| EXCLUDED | 66 |

**NO_STRATEGY_RESEARCH_QUALIFIED.** Excluded = ten non-ready concepts across six
views plus six unsupported H4 session cells. These are cell counts, not 180
strategies. No sample pooling, optimization, reset or threshold adjustment.

The one sample-sufficient cell: p6-15 / Bollinger outer touch / XAGUSD / 1H.
66 resolved total,20 OOS. OOS expectancy -0.711582R; PF0.140911; win rate5%;
DD17.789540R; PF degradation79.7041%. It fails EXPECTANCY, PROFIT_FACTOR, WIN_RATE,
DRAWDOWN and DEGRADATION. All other evaluated cells remain insufficient rather
than being promoted on attractive but too-small samples. Individual failed gates
are retained even when final status is insufficient evidence.

## Requirement Proof

| Requirement | Result / evidence |
|---|---|
| Locked versioned methodology | PASS: ADR-006, hashed policy/configuration |
| P5 qualification, P6 eligibility/frozen parameters | PASS: guarded reader, full content hash, exact replay configuration checks |
| Chronology / no look-ahead | PASS within P6 reconstruction scope: closed features, interval checks, boundary censoring, future-mutation/prefix regression |
| Explicit ten gates and boundaries | PASS:61 focused tests include equality, strict-zero expectancy, invalid/nonfinite metrics, degradation and integrity precedence |
| Full eligible cell metrics/classification | PASS:114 cells, independent denominators, reproducible status |
| Robustness | PASS:five replay cases plus deterministic best/worst removal per eligible cell |
| Correlation | PASS implementation, including absolute0.80 boundary and negative cluster; actual analysis NOT_APPLICABLE because no qualifying pair |
| Identity, immutability/restart | PASS:570 rereads, repeated P7 publication, new-store reread, conflict rejection, fixture immutability tests |
| Deterministic Arena projection | PASS:two equal builds;89 snapshots,8174 events; final metric/gate equality with authoritative result |
| Read-only API | PASS:authentication, bounds, no early robustness disclosure, write denial, unchanged projection, fixture app has no executor |
| Frontend integration | PASS:existing router/navigation, real backend data, no browser qualification logic |
| Browser experience | PASS:nine grouped checks, screenshots desktop1440x1000/mobile390x844, no horizontal page overflow or browser errors |
| Regressions | PASS:996 tests, build pass, no broker/operator access in guarded runs |

## Commands And Test Evidence

All Python research/test commands use the normalized P1-M2 incident-review guard
in TESTING.md: Python -B, scrubbed environment, no plugin autoload, protected-path
audit hooks, six synthetic self-tests. Focused selection is test_p7_tournament.py;
broad is the prior27-module allowlist plus P7, no unrestricted discovery.

- Final focused: **61 passed /102 warnings /20.61s**, exit0.
- Final broad including Arena integration: **996 passed /1681 warnings /152.59s**,
  exit0. Existing framework warnings remain visible; no failures waived.
- Each guarded research/test run: SENSITIVE_OR_OPERATOR_ACCESS_ATTEMPTS0,
  FORBIDDEN_RUNTIME_MODULES[]. No actual MT5, credentials, operator DB or network
  market acquisition was needed. Native normalization regressions use fixtures.
- Real final tournament: scripts/p7_tournament.py, exit0,570 verified replays.
- Projection: scripts/p7_arena.py, exit0,27,012,105 bytes, bounded local artifact.
- Frontend: npm install lucide-react,0 audit vulnerabilities; final npm run build
  exit0,175.22kB JS /56.29kB gzip,27.85kB CSS. No unrelated dependency upgrade.
- Real-data browser check: node tests/tournament-arena.mjs using bundled
  Playwright via P7_PLAYWRIGHT, fresh headless Edge. PASS all nine grouped checks,
  zero console errors. Local screenshots and ui-result.json under the ignored
  research/p5-market-data/p7-ui-check directory. No synthetic UI market values.

Failure history preserved: first focused run54pass/1fail because a test omitted
MarketStore's required fixture flag; corrected test, boundary not weakened.
Arena integration first60pass/1fail because the fixture app correctly required an
explicit synthetic account; supplied fixture identity, no operator fallback.
Subsequent final focused/broad/browser runs all passed.

## Boundaries And Remaining Work

SHORT_SAMPLE_RESEARCH_ONLY. Commission NOT_INCLUDED. The qualified period was
selected retrospectively and was already seen by P6; this is chronological
research, not an untouched holdout or prospective profitability proof. Unknown
outcomes are not fabricated zero; priced TIMEOUT and resolved-trade denominators
remain distinct. R curves are independent experiments, not shared-capital PnL.
WTI mapping/provider timing limits persist. No actual qualified cluster exists.

The Arena shows reversible interim warnings. Final statuses only occur at OOS end;
earlier elimination would invent a policy and was not implemented for animation.
Result/projection JSON is authoritative; UI interactions are read-only. The local
preview is separately bound to synthetic access and a fresh temporary fixture DB;
normal operator startup/state is untouched. No execution controls are exposed.

P7 blockers: NONE. P8 implementation NOT_STARTED; ADR-005 responsibility and
label/sample policy still require human disposition. Broker execution remains
HARD_DISABLED; P3 operator demo qualification remains DEFERRED.
