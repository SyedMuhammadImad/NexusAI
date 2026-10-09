# ADR-015 - Versioned Session-Aware Research Qualification

Status: **ACCEPTED**. Authority: explicit owner session-qualification task,
2026-09-14. This implements the requested abstraction, not a new gap budget.

Separate versioned calendar evidence from immutable candles. Classify missing
intervals as expected session/holiday/maintenance closure, provider gap or unknown.
Only completely covered expected closures may bridge a research range; unknown
and provider gaps break it. Explicit evidence, UTC bounds and source fixed EST are
part of calendar identity. Contradictory overlapping windows reject; observed bars
inside closures reject qualification. No bar is fabricated or removed.

For current 2021 HistData, the narrow Saturday 00:00-24:00 UTC core is explicitly
a MARKET_INFERENCE based on related Sunday-Friday market schedules, not a proven
HistData contract calendar. Preserve that limitation in every qualification. It
must not be labelled full provider-session proof. Daily hours, Friday/Sunday edges,
holidays and early closes remain UNKNOWN until their feed applicability is shown.
Calendar coincidence or data absence alone is not the evidence basis.

The owner permits trustworthy market evidence when exact provider rules cannot
be proven. This supplements ADR-014 accordingly without changing its bar-retention
rule. ADR-013's prohibition on silent unresolved-gap crossing remains intact.
No acceptable numerical gap tolerance is inferred. Calendar engine verification
and dataset/phase qualification remain distinct. P6 is not authorized here.
