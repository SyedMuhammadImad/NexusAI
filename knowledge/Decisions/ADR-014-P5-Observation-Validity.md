# ADR-014 - Separate Observation Validity and Continuity

Status: **ACCEPTED**. Authority: owner's HistData-first remediation request,
2026-09-14, explicitly requiring valid-bar retention across neighboring gaps.

This supplements ADR-013: non-overlapping adjacent OHLC ranges alone are not
invalid observations. Preserve their flags as informational, zero-width price-gap
observations; do not exclude either otherwise valid bar. No price-jump tolerance
is invented. Missing timestamps, contradictory duplicates and malformed evidence
retain fail-closed treatment. Raw records and prior qualification versions remain
immutable. New qualification/coverage rule IDs prevent silent reuse of old reports.

Expected closures still require applicable evidence. Calendar coincidence alone
does not prove a feed closure; distinguish weekend candidates from exemptions.
No synthetic candles, strategy, ML, broker action or P6 authorization follows.
