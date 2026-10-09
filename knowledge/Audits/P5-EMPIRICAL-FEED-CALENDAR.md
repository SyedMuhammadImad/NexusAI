# P5 Empirical Feed Calendar Audit

Policy: HISTDATA_FEED_CALENDAR_2021_V1. Research only; execution HARD DISABLED.
Derivation is retrospective. No official exchange/broker hours are inferred.
Complete models, confidence arrays, exceptions and residual intervals: `research/p5-market-data/feed-audit-975bde0e35066714b7e9137ce728b9f2f57cb7c8f446add8ee838024ea2a7fc4.json`.

| Instrument | Comparable weeks | Weekly closed minute slots | Special days | Residual M1 minutes |
|---|---:|---:|---|---:|
| XAUUSD | 51 | 2880 | 2021-01-01, 2021-04-02, 2021-12-24 | 10514 |
| XAGUSD | 51 | 2880 | 2021-01-01, 2021-04-02, 2021-12-24 | 13016 |
| USOIL | 51 | 2880 | 2021-01-01, 2021-04-02, 2021-12-24 | 17005 |

## Longest Strictly Continuous Ranges

These ranges cross expected feed closures, never UNKNOWN_GAP. Range unknown count is zero.
Expected M1 completeness is 100%; fully closed bins emit no candle.

| Instrument/frame | Start UTC | End UTC | Actual range bars | Range closure bins | Annual unknown bins |
|---|---|---|---:|---:|---:|
| XAUUSD/1H | 2021-07-05T23:00:00+00:00 | 2021-08-03T21:00:00+00:00 | 482 | 212 | 205 |
| XAUUSD/4H | 2021-07-06T00:00:00+00:00 | 2021-08-03T20:00:00+00:00 | 129 | 44 | 166 |
| XAGUSD/1H | 2021-06-16T11:00:00+00:00 | 2021-06-21T21:00:00+00:00 | 79 | 51 | 1121 |
| XAGUSD/4H | 2021-06-16T12:00:00+00:00 | 2021-06-21T20:00:00+00:00 | 21 | 11 | 680 |
| USOIL/1H | 2021-12-02T23:00:00+00:00 | 2021-12-05T22:00:00+00:00 | 23 | 48 | 1685 |
| USOIL/4H | 2021-12-03T00:00:00+00:00 | 2021-12-05T20:00:00+00:00 | 6 | 11 | 818 |

## Identity and Residual Examples

### XAUUSD 1H
Dataset `8da10378a01d71d99c14d719700649aaf490f265e3443a2ef1c3c890e99c14d4`; calendar `93d0ac76e2f8b75e1a64b2ae7009c23b131f1faf1bfb8d9723a76024b3dd5c42`;
qualification `6ca0aacbb1e76186f086a4bc5c5b24b83a8befd4c7e07dc3ff1cc41ca9b5c521`.

First ten unresolved aggregate intervals (all intervals and source M1 gaps are in the hashed JSON):
- 2021-01-03T22:00:00+00:00 to 2021-01-03T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-04T22:00:00+00:00 to 2021-01-04T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-05T22:00:00+00:00 to 2021-01-05T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-06T22:00:00+00:00 to 2021-01-06T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-07T22:00:00+00:00 to 2021-01-07T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-10T22:00:00+00:00 to 2021-01-10T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-11T22:00:00+00:00 to 2021-01-11T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-12T22:00:00+00:00 to 2021-01-12T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-13T22:00:00+00:00 to 2021-01-13T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-14T21:00:00+00:00 to 2021-01-14T22:00:00+00:00: 1/60 expected minutes missing.

### XAUUSD 4H
Dataset `6cf46ac1c0d840fab72ffc766acb09e1bf95185bbe564e7fb8689e10322fa955`; calendar `93d0ac76e2f8b75e1a64b2ae7009c23b131f1faf1bfb8d9723a76024b3dd5c42`;
qualification `30c4f4a5eecf73214326fd98abc4347652facdc1f77dd9d1ce973d568932ce87`.

First ten unresolved aggregate intervals (all intervals and source M1 gaps are in the hashed JSON):
- 2021-01-03T20:00:00+00:00 to 2021-01-04T00:00:00+00:00: 60/120 expected minutes missing.
- 2021-01-04T20:00:00+00:00 to 2021-01-05T00:00:00+00:00: 60/240 expected minutes missing.
- 2021-01-05T20:00:00+00:00 to 2021-01-06T00:00:00+00:00: 60/240 expected minutes missing.
- 2021-01-06T20:00:00+00:00 to 2021-01-07T00:00:00+00:00: 60/240 expected minutes missing.
- 2021-01-07T20:00:00+00:00 to 2021-01-08T00:00:00+00:00: 60/240 expected minutes missing.
- 2021-01-10T20:00:00+00:00 to 2021-01-11T00:00:00+00:00: 60/120 expected minutes missing.
- 2021-01-11T20:00:00+00:00 to 2021-01-12T00:00:00+00:00: 60/240 expected minutes missing.
- 2021-01-12T20:00:00+00:00 to 2021-01-13T00:00:00+00:00: 60/240 expected minutes missing.
- 2021-01-13T20:00:00+00:00 to 2021-01-14T00:00:00+00:00: 60/240 expected minutes missing.
- 2021-01-14T20:00:00+00:00 to 2021-01-15T00:00:00+00:00: 61/240 expected minutes missing.

### XAGUSD 1H
Dataset `95d19c3a8390e213204e331cf0d7b9c77f9b1c7c565e9928ce3338695449a625`; calendar `ce28cd970294235c956125dabecb1836d76259d7307c6768c132b1e8d973f7e3`;
qualification `40b87d678ccf6fcd48d7ccb4f32002f8dd974686e9c2ae214c8974248373f77a`.

First ten unresolved aggregate intervals (all intervals and source M1 gaps are in the hashed JSON):
- 2021-01-03T22:00:00+00:00 to 2021-01-03T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-04T04:00:00+00:00 to 2021-01-04T05:00:00+00:00: 1/60 expected minutes missing.
- 2021-01-04T21:00:00+00:00 to 2021-01-04T22:00:00+00:00: 2/60 expected minutes missing.
- 2021-01-04T22:00:00+00:00 to 2021-01-04T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-05T22:00:00+00:00 to 2021-01-05T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-06T22:00:00+00:00 to 2021-01-06T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-07T21:00:00+00:00 to 2021-01-07T22:00:00+00:00: 1/60 expected minutes missing.
- 2021-01-07T22:00:00+00:00 to 2021-01-07T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-10T22:00:00+00:00 to 2021-01-10T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-11T21:00:00+00:00 to 2021-01-11T22:00:00+00:00: 1/60 expected minutes missing.

### XAGUSD 4H
Dataset `ec9759fb4263e428461d0b79bc8373582bb55b7df19cb9bf41581e5d2d4471c4`; calendar `ce28cd970294235c956125dabecb1836d76259d7307c6768c132b1e8d973f7e3`;
qualification `3479384dc24d5cc4fb4cffafa97451e37b476afa68b8b86e6b2e158bf6f7e11b`.

First ten unresolved aggregate intervals (all intervals and source M1 gaps are in the hashed JSON):
- 2021-01-03T20:00:00+00:00 to 2021-01-04T00:00:00+00:00: 60/120 expected minutes missing.
- 2021-01-04T04:00:00+00:00 to 2021-01-04T08:00:00+00:00: 1/240 expected minutes missing.
- 2021-01-04T20:00:00+00:00 to 2021-01-05T00:00:00+00:00: 62/240 expected minutes missing.
- 2021-01-05T20:00:00+00:00 to 2021-01-06T00:00:00+00:00: 60/240 expected minutes missing.
- 2021-01-06T20:00:00+00:00 to 2021-01-07T00:00:00+00:00: 60/240 expected minutes missing.
- 2021-01-07T20:00:00+00:00 to 2021-01-08T00:00:00+00:00: 61/240 expected minutes missing.
- 2021-01-10T20:00:00+00:00 to 2021-01-11T00:00:00+00:00: 60/120 expected minutes missing.
- 2021-01-11T20:00:00+00:00 to 2021-01-12T00:00:00+00:00: 61/240 expected minutes missing.
- 2021-01-12T20:00:00+00:00 to 2021-01-13T00:00:00+00:00: 60/240 expected minutes missing.
- 2021-01-13T20:00:00+00:00 to 2021-01-14T00:00:00+00:00: 61/240 expected minutes missing.

### USOIL 1H
Dataset `86de3ea9347383075ab16d373ed802bda2f93537b100f10792bff031958834a6`; calendar `e6bdae72523e7ddc66eeae459c28d08bf12b984b48e08301ec486915334d82af`;
qualification `3ee8cbe7a1f2a4dd9f22449362cfe92b5af289a3dd7ae0e7f06b861ada3bc057`.

First ten unresolved aggregate intervals (all intervals and source M1 gaps are in the hashed JSON):
- 2021-01-03T22:00:00+00:00 to 2021-01-03T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-04T00:00:00+00:00 to 2021-01-04T01:00:00+00:00: 1/60 expected minutes missing.
- 2021-01-04T03:00:00+00:00 to 2021-01-04T04:00:00+00:00: 2/60 expected minutes missing.
- 2021-01-04T04:00:00+00:00 to 2021-01-04T05:00:00+00:00: 9/60 expected minutes missing.
- 2021-01-04T05:00:00+00:00 to 2021-01-04T06:00:00+00:00: 1/60 expected minutes missing.
- 2021-01-04T21:00:00+00:00 to 2021-01-04T22:00:00+00:00: 5/60 expected minutes missing.
- 2021-01-04T22:00:00+00:00 to 2021-01-04T23:00:00+00:00: 60/60 expected minutes missing.
- 2021-01-04T23:00:00+00:00 to 2021-01-05T00:00:00+00:00: 3/60 expected minutes missing.
- 2021-01-05T00:00:00+00:00 to 2021-01-05T01:00:00+00:00: 1/60 expected minutes missing.
- 2021-01-05T02:00:00+00:00 to 2021-01-05T03:00:00+00:00: 2/60 expected minutes missing.

### USOIL 4H
Dataset `c7f0ac316759222d57f3902c0196fc1338a3ea2b0b15f13544cfe0d399000fd8`; calendar `e6bdae72523e7ddc66eeae459c28d08bf12b984b48e08301ec486915334d82af`;
qualification `a8f7b5d315ff316663855604ddd1fe33578fd3289ed6d7d6a79e370ccf9c02b1`.

First ten unresolved aggregate intervals (all intervals and source M1 gaps are in the hashed JSON):
- 2021-01-03T20:00:00+00:00 to 2021-01-04T00:00:00+00:00: 60/120 expected minutes missing.
- 2021-01-04T00:00:00+00:00 to 2021-01-04T04:00:00+00:00: 3/240 expected minutes missing.
- 2021-01-04T04:00:00+00:00 to 2021-01-04T08:00:00+00:00: 10/240 expected minutes missing.
- 2021-01-04T20:00:00+00:00 to 2021-01-05T00:00:00+00:00: 68/240 expected minutes missing.
- 2021-01-05T00:00:00+00:00 to 2021-01-05T04:00:00+00:00: 4/240 expected minutes missing.
- 2021-01-05T04:00:00+00:00 to 2021-01-05T08:00:00+00:00: 12/240 expected minutes missing.
- 2021-01-05T20:00:00+00:00 to 2021-01-06T00:00:00+00:00: 64/240 expected minutes missing.
- 2021-01-06T00:00:00+00:00 to 2021-01-06T04:00:00+00:00: 2/240 expected minutes missing.
- 2021-01-06T04:00:00+00:00 to 2021-01-06T08:00:00+00:00: 1/240 expected minutes missing.
- 2021-01-06T20:00:00+00:00 to 2021-01-07T00:00:00+00:00: 66/239 expected minutes missing.

## Verification Scope

Repeated derivation, re-ingestion and reopen/query equality passed for every instrument/frame.
Source versions and old datasets are preserved. No synthetic repair or broker action.
Full-day shared absence is descriptive, not official holiday attribution. Irregular and
partial-day gaps remain UNKNOWN. See TESTING.md for fixture regression results.
