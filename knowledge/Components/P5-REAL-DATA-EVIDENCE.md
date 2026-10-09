# P5 Real-Data Evidence - Bounded Sample

This is the preserved initial sample checkpoint. The subsequent annual 2021
expansion, classifications, exact IDs and remaining continuity blocker are in
`../Audits/P5-CLOSEOUT.md`. No original raw data, flags or identities were rewritten.

Verified 2026-09-14 with HistData public ASCII/M1 archives. No broker, credentials
or operator stores. Exact UTC interval: **[2021-01-04T12:00:00+00:00,
2021-01-04T20:00:00+00:00)**. Per instrument: 480 M1 observations, 8 complete
UTC 1H bars, 2 complete UTC 4H bars. No missing timestamps within this window.
Last opens: M1 19:59, 1H 19:00, 4H 16:00; all complete by 20:00.

Final validator: strict-shape-completeness-discontinuity-v3. All nine datasets
are REVIEW_REQUIRED, NOT qualified backtest inputs: 6 gold, 3 silver and 7 oil
adjacent disjoint price ranges are flagged, retained and propagated to aggregates.
These may be legitimate moves, not proven corruption. Default research queries
reject them; diagnostic reads retain every valid-shaped candle and quality flag.

## Dataset IDs

| Instrument | Frame | Immutable dataset ID |
|---|---|---|
| XAUUSD | 1M | `0a6d9c2913d25ff05fd5522473719805e268660f896bc5ff567531f20f46ab1b` |
| XAUUSD | 1H | `ccb44d9a8cfd370eb912b872543c2cb773342d3a76565897026b6b7bcc3397d6` |
| XAUUSD | 4H | `8d8f0474381f7816b8e68c3b7e6a782195f526f3c16781acf62d1d3fce3191d2` |
| XAGUSD | 1M | `2857acef7541aa99dacdcace2bc15d981aef01c498f0821604d1237f62ffa281` |
| XAGUSD | 1H | `6149ac24c2c891d46d3e319f2bc755ea22cb344614798f9bbd92ac986bf57725` |
| XAGUSD | 4H | `5a0e248586861761719bd4301e1de05ded5e8055ce24a54f1ff93a720e9ffab2` |
| USOIL | 1M | `a81094063960d7eab6efe4913df7309af1bbd5ac9a694ad169e82c0959e5971c` |
| USOIL | 1H | `fc47e161bd9ae334c2b0364a6376e208052786660a286bd7915232ea24924b60` |
| USOIL | 4H | `47982817e5a76a634b3a1d1e38cc50e923f0038844d9e3babac92f5cba92ab91` |

All nine reproduce on unchanged re-ingestion and store reopen. No duplicate bars
or receipts. This proves deterministic local data replay, not strategy replay.

## Raw Evidence

Annual 2021 ZIP files were explicitly identified through the provider's annual
form and archive member name. Full raw bytes are retained in the ignored research
store; only the January window above is verified, not a full year.

| Source | Bytes | Download SHA256 |
|---|---|---|
| XAUUSD | 4252073 | `312229c9db5b39138c41b1e488d00ed32e158a0d1fc3f23a225b223c3271c0a4` |
| XAGUSD | 3248260 | `7ccccc89c592339ce3ca7712c1ee3758bd15fe6cbc398ef8473a3fbf840d97a3` |
| WTIUSD | 3134351 | `d808a19ff0129ced92ca0de1d6c67dc073f271abee520338a7956ef39814e29d` |

Receipts retain URLs, raw hashes and ingestion times, not public form markers.
Raw data are not committed or pushed. `research/p5-market-data/smoke-report.json`
is a replaceable diagnostic snapshot; the underlying evidence is append-only.

## Failures and Limits

- Initial January 2025 smoke failed on missing WTI download form. Previously
  stored gold/silver draft versions remain; this was not a complete smoke run.
- Probes did not establish recent WTI availability for the checked 2024/2025
  annual or January 2026 links. Website period listings did not prove downloads.
- A valid 2021 annual form was found and explicit annual handling added/tested.
  No oil substitute or invented price was used.
- Draft validation accepted gap-free samples before discontinuity checks. Old
  immutable versions remain, but default queries reject superseded validators.
- A resumed shell invocation lost an in-memory helper and exited before running
  the smoke script. It was reconstructed; no data result is inferred from that failure.
- Full 2021-present coverage, provider session/holiday calendars, actual volume,
  spreads, contract rolls and exact Exness equivalence remain unverified.
- No strategy replay, labels, Kronos runtime, training or profitability proof.

Reproduction: guarded scripts/p5_real_smoke.py. Test results/guard limits: TESTING.md.
