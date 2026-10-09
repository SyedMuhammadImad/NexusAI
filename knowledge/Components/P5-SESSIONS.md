# P5 Session-Aware Continuity

Status: engine implemented; real-feed calendar certainty PARTIAL. No P6.
Authority: ADR-015 and the owner's session-qualification task.

Verification closeout 2026-09-15: 113 focused / 797 broad tests passed; all nine
real versions reclassified with repeat/reopen equality and no closure conflicts.
See TESTING.md and Audits/P5-SESSION-QUALIFICATION.md. P5 remains PARTIAL.

## Evidence and Scope

`histdata-2021-saturday-core-v1` exempts only Saturday 00:00-24:00 UTC in 2021.
It is an explicit **MARKET_INFERENCE**, not HistData attestation. Related markets
have Sunday-Friday schedules in the primary sources below. Saturday UTC is a
narrow interior subset, avoiding Friday and Sunday opening/closing edges and
their DST complications. Applying this subset to the HistData research proxies is
an inference, checked against actual observations, not proof of contract equality.

- Gold/silver: [CME London Spot Gold/Silver contract fact sheet, copyright 2016,
  page 2](https://www.cmegroup.com/trading/metals/precious/files/precious-metals-spot-spread.pdf).
- WTI: [CME SER-8782R, June 9 2021, page 1](https://www.cmegroup.com/notices/ser/2021/06/SER-8782R.pdf),
  a related micro-contract launched July 2021. It is not proof of HistData's
  full-year feed hours or contract construction.
- [HistData ASCII specification](https://www.histdata.com/f-a-q/data-files-detailed-specification/):
  source fixed EST without DST. Calendar evaluation uses explicit UTC; never
  local-machine time or an implicit America/New_York conversion.
- [CME 2021 holiday processing notice](https://www.cmegroup.com/notices/market-regulation/2021/01/MSN01-14-21.html)
  concerns reporting/processing, not proof of HistData's complete trading closures.
  It is not used to exempt candles.

No real daily maintenance, holiday or shortened-session exemption is asserted.
Their contracts are implemented and fixture-tested, but applicability remains
unproven. Current CME hours are not retroactively asserted as exact 2021 HistData
hours. This calendar deliberately leaves Friday/Sunday edges and uncertain daily
and holiday gaps unexplained; it is not a blind 24/5 expectation model.

## Contracts

`Window` has aware minute-aligned UTC start/end, classification, evidence reference,
preserved evidence note and basis (PROVIDER_CONFIRMED / MARKET_INFERENCE / FIXTURE).
`Calendar` binds provider, instrument, policy version, validity range, source timezone
and canonical sorted windows. Duplicate identical windows coalesce; overlap, wrong
provider/instrument, naive time, out-of-range or unbounded requests fail closed.
Exceptions are explicit windows, not mutable row exclusions. Changed evidence or
policy changes the SHA256 calendar identity. There is no implicit live update.

`Calendar.at(provider,instrument,timestamp)` returns EXPECTED (`expected=true`)
unless an evidenced closure covers the instant. Default EXPECTED is conservative
counting, not a claim that the market was certainly open; its missing-bar
classification is UNKNOWN_GAP. Explicit provider unavailability remains PROVIDER_GAP
and still counts against continuity. Missing windows classify as the five owner
categories. Observed candles are never removed or synthesized.

Only a single fully covering closure window exempts an aggregate slot. Partial
coverage or adjacent differently classified windows conservatively leave the
aggregate unresolved. The existing complete-only resampler is unchanged. No
partly observed 4H OHLC is presented as a complete 4H candle.

## Qualification and Query

`SessionResearch` adds P5 research schema 4 and immutable
`p5_session_qualification`. It requires existing provenance/observation qualification,
zero withheld observations and no observed bars conflicting with closure windows.
Fixture-priced datasets and explicitly fixture-based calendars reject.
Calendar references are trusted caller assertions, not cryptographic authenticity
proof; this class is not exposed as an untrusted public approval API.

Reports pin dataset, prior observation qualification, calendar ID/full policy,
classification intervals, expected/actual/closure/unexplained counts, longest gap,
maximal usable segments, state and limitations. No operator schema is touched.
Repeated assessment and reopen produce identical identity. SQL UPDATE/DELETE reject.
Session queries require an explicit qualification and range within one usable
segment; they may skip expected closures but never UNKNOWN_GAP/PROVIDER_GAP.
Closure-only/no-observation queries reject. Calendar conflicts reject all queries.
QUALIFIED_SEGMENTS_ONLY is not a multi-month or phase-completion claim.

`scripts/p5_session_audit.py` assesses all nine pinned 2021 M1/1H/4H datasets,
checks repeated qualification and reopen/query equality, and records every exact
gap plus longest segments in a hashed ignored research report. Run through the
normalized TESTING.md guard. Summary: Audits/P5-SESSION-QUALIFICATION.md.
