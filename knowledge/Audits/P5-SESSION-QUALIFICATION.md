# P5 Session Qualification Audit

Status: PARTIAL. P6 BLOCKED. Broker execution HARD DISABLED.

Full classified gap intervals: `research/p5-market-data/session-audit-ea12b455e805a17ca4b525ddd403c5267aac8fe9f46eeef3321543fb5e866ed5.json`.
Policy: histdata-2021-saturday-core-v1; engine: p5-session-continuity-v1.
Calendar certainty: PARTIAL; Saturday exemptions are explicit market inference.
No calendar conflicts, duplicate ingestion or fabricated candles are permitted.
Reported ranges are longest usable segments, NOT qualified multi-month histories.

| Instrument/frame | Start UTC | End UTC | Actual/expected bars in range | Closure bars in range | Annual unknown bars | Annual closure bars |
|---|---|---|---:|---:|---:|---:|
| XAUUSD/1M | 2021-01-03T23:00:00+00:00 | 2021-01-04T22:00:00+00:00 | 1380 | 0 | 97334 | 74880 |
| XAUUSD/1H | 2021-01-03T23:00:00+00:00 | 2021-01-04T22:00:00+00:00 | 23 | 0 | 1652 | 1248 |
| XAUUSD/4H | 2021-01-04T00:00:00+00:00 | 2021-01-04T20:00:00+00:00 | 5 | 0 | 611 | 312 |
| XAGUSD/1M | 2021-01-04T23:00:00+00:00 | 2021-01-05T22:00:00+00:00 | 1380 | 0 | 100044 | 74880 |
| XAGUSD/1H | 2021-01-04T23:00:00+00:00 | 2021-01-05T22:00:00+00:00 | 23 | 0 | 2573 | 1248 |
| XAGUSD/4H | 2021-01-05T00:00:00+00:00 | 2021-01-05T20:00:00+00:00 | 5 | 0 | 982 | 312 |
| USOIL/1M | 2021-03-07T23:00:00+00:00 | 2021-03-08T22:00:00+00:00 | 1380 | 0 | 103929 | 74880 |
| USOIL/1H | 2021-03-07T23:00:00+00:00 | 2021-03-08T22:00:00+00:00 | 23 | 0 | 3136 | 1248 |
| USOIL/4H | 2021-03-04T00:00:00+00:00 | 2021-03-04T20:00:00+00:00 | 5 | 0 | 1116 | 312 |

Every longest segment above has zero unexplained missing bars. None is multi-month.
Annual unknown counts include unverified daily breaks, weekend edges and holidays.
PROVIDER_GAP is reserved for supported provider-unavailability evidence; no such
assertion is invented from absence alone. All non-exempt real gaps remain UNKNOWN_GAP.
Exact expected closures/gaps, timestamps, counts, policy and dataset IDs are in the hashed JSON.

## Exact Boundary Blockers

First ten non-exempt intervals per aggregate dataset follow; the JSON preserves ALL intervals.
These examples prevent silent cross-gap qualification, not proof of corrupted provider data.

### XAUUSD 1H
Dataset `c254adbcd70038ee533d04ea01486eb0620af2a6826f1b0e231146a627b106d7`; qualification `3ffe218d27fe1c326580bab64f85ca66ed9987386354c06580db7f7774bac857`.

- 2021-01-01T00:00:00+00:00 to 2021-01-02T00:00:00+00:00: UNKNOWN_GAP, 24 bars.
- 2021-01-03T00:00:00+00:00 to 2021-01-03T23:00:00+00:00: UNKNOWN_GAP, 23 bars.
- 2021-01-04T22:00:00+00:00 to 2021-01-04T23:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-05T22:00:00+00:00 to 2021-01-05T23:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-06T22:00:00+00:00 to 2021-01-06T23:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-07T22:00:00+00:00 to 2021-01-07T23:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-08T22:00:00+00:00 to 2021-01-09T00:00:00+00:00: UNKNOWN_GAP, 2 bars.
- 2021-01-10T00:00:00+00:00 to 2021-01-10T23:00:00+00:00: UNKNOWN_GAP, 23 bars.
- 2021-01-11T22:00:00+00:00 to 2021-01-11T23:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-12T22:00:00+00:00 to 2021-01-12T23:00:00+00:00: UNKNOWN_GAP, 1 bars.

### XAUUSD 4H
Dataset `b3380bcd815f49594fc3db3b4ecb89b1165841fa6066104a0d36e0fbb90732a0`; qualification `fb4daa8c1d460f0964654ba276e6e77a4c71b0423ba5293117cc7e58a5841b51`.

- 2021-01-01T00:00:00+00:00 to 2021-01-02T00:00:00+00:00: UNKNOWN_GAP, 6 bars.
- 2021-01-03T00:00:00+00:00 to 2021-01-04T00:00:00+00:00: UNKNOWN_GAP, 6 bars.
- 2021-01-04T20:00:00+00:00 to 2021-01-05T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-05T20:00:00+00:00 to 2021-01-06T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-06T20:00:00+00:00 to 2021-01-07T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-07T20:00:00+00:00 to 2021-01-08T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-08T20:00:00+00:00 to 2021-01-09T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-10T00:00:00+00:00 to 2021-01-11T00:00:00+00:00: UNKNOWN_GAP, 6 bars.
- 2021-01-11T20:00:00+00:00 to 2021-01-12T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-12T20:00:00+00:00 to 2021-01-13T00:00:00+00:00: UNKNOWN_GAP, 1 bars.

### XAGUSD 1H
Dataset `a596229b6024ae23313e703177fa054946b6fa4e0f08a9721847781b4410787b`; qualification `d633978021caae3f500e2d51ac202d0da01b8b401b7984043b078e83352aaf11`.

- 2021-01-01T00:00:00+00:00 to 2021-01-02T00:00:00+00:00: UNKNOWN_GAP, 24 bars.
- 2021-01-03T00:00:00+00:00 to 2021-01-03T23:00:00+00:00: UNKNOWN_GAP, 23 bars.
- 2021-01-04T04:00:00+00:00 to 2021-01-04T05:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-04T21:00:00+00:00 to 2021-01-04T23:00:00+00:00: UNKNOWN_GAP, 2 bars.
- 2021-01-05T22:00:00+00:00 to 2021-01-05T23:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-06T22:00:00+00:00 to 2021-01-06T23:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-07T21:00:00+00:00 to 2021-01-07T23:00:00+00:00: UNKNOWN_GAP, 2 bars.
- 2021-01-08T22:00:00+00:00 to 2021-01-09T00:00:00+00:00: UNKNOWN_GAP, 2 bars.
- 2021-01-10T00:00:00+00:00 to 2021-01-10T23:00:00+00:00: UNKNOWN_GAP, 23 bars.
- 2021-01-11T21:00:00+00:00 to 2021-01-11T23:00:00+00:00: UNKNOWN_GAP, 2 bars.

### XAGUSD 4H
Dataset `6f3490df13b6c3c2ee6a23726e45a0ba67df8d2f1b38f14db7be565099705924`; qualification `20d09d8813282fc11172a17b14bf718dd3ebf9482d210db6ea5eeff139d124b4`.

- 2021-01-01T00:00:00+00:00 to 2021-01-02T00:00:00+00:00: UNKNOWN_GAP, 6 bars.
- 2021-01-03T00:00:00+00:00 to 2021-01-04T00:00:00+00:00: UNKNOWN_GAP, 6 bars.
- 2021-01-04T04:00:00+00:00 to 2021-01-04T08:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-04T20:00:00+00:00 to 2021-01-05T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-05T20:00:00+00:00 to 2021-01-06T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-06T20:00:00+00:00 to 2021-01-07T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-07T20:00:00+00:00 to 2021-01-08T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-08T20:00:00+00:00 to 2021-01-09T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-10T00:00:00+00:00 to 2021-01-11T00:00:00+00:00: UNKNOWN_GAP, 6 bars.
- 2021-01-11T20:00:00+00:00 to 2021-01-12T00:00:00+00:00: UNKNOWN_GAP, 1 bars.

### USOIL 1H
Dataset `fb1ff343f833a36a73cd9af75cf4268ac17336c0b2843dd4b593278c93b1efbe`; qualification `c3c926b2438ae0a116cf560f3925d890973cd6d43efb64a3582ac4c924c83c2a`.

- 2021-01-01T00:00:00+00:00 to 2021-01-02T00:00:00+00:00: UNKNOWN_GAP, 24 bars.
- 2021-01-03T00:00:00+00:00 to 2021-01-03T23:00:00+00:00: UNKNOWN_GAP, 23 bars.
- 2021-01-04T00:00:00+00:00 to 2021-01-04T01:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-04T03:00:00+00:00 to 2021-01-04T06:00:00+00:00: UNKNOWN_GAP, 3 bars.
- 2021-01-04T21:00:00+00:00 to 2021-01-05T01:00:00+00:00: UNKNOWN_GAP, 4 bars.
- 2021-01-05T02:00:00+00:00 to 2021-01-05T06:00:00+00:00: UNKNOWN_GAP, 4 bars.
- 2021-01-05T22:00:00+00:00 to 2021-01-06T01:00:00+00:00: UNKNOWN_GAP, 3 bars.
- 2021-01-06T05:00:00+00:00 to 2021-01-06T06:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-06T22:00:00+00:00 to 2021-01-07T01:00:00+00:00: UNKNOWN_GAP, 3 bars.
- 2021-01-07T04:00:00+00:00 to 2021-01-07T05:00:00+00:00: UNKNOWN_GAP, 1 bars.

### USOIL 4H
Dataset `49c05f00d973a7d85d293d388e37a173ba7602a23b8472e921cc684d2089a767`; qualification `049ffdb2b05f44ca0bf256909cc6809916dfbe1cc2dcf9a15275aa571cdef50c`.

- 2021-01-01T00:00:00+00:00 to 2021-01-02T00:00:00+00:00: UNKNOWN_GAP, 6 bars.
- 2021-01-03T00:00:00+00:00 to 2021-01-04T08:00:00+00:00: UNKNOWN_GAP, 8 bars.
- 2021-01-04T20:00:00+00:00 to 2021-01-05T08:00:00+00:00: UNKNOWN_GAP, 3 bars.
- 2021-01-05T20:00:00+00:00 to 2021-01-06T08:00:00+00:00: UNKNOWN_GAP, 3 bars.
- 2021-01-06T20:00:00+00:00 to 2021-01-07T08:00:00+00:00: UNKNOWN_GAP, 3 bars.
- 2021-01-07T20:00:00+00:00 to 2021-01-08T08:00:00+00:00: UNKNOWN_GAP, 3 bars.
- 2021-01-08T20:00:00+00:00 to 2021-01-09T00:00:00+00:00: UNKNOWN_GAP, 1 bars.
- 2021-01-10T00:00:00+00:00 to 2021-01-11T12:00:00+00:00: UNKNOWN_GAP, 9 bars.
- 2021-01-11T20:00:00+00:00 to 2021-01-12T08:00:00+00:00: UNKNOWN_GAP, 3 bars.
- 2021-01-12T20:00:00+00:00 to 2021-01-13T08:00:00+00:00: UNKNOWN_GAP, 3 bars.

## Remaining Work

Establish applicable daily/edge/holiday evidence, then re-assess these pinned
datasets. Complete-only 4H aggregation still omits partly observed bins; changing
that contract would require explicit session-aware resampling evidence, not fills.
No second provider credentials, strategy, ML or broker action was requested or used.
