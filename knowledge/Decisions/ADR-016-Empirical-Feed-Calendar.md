# ADR-016 - Empirical Research Feed Calendar

Status: **ACCEPTED**. Explicit owner approval, 2026-09-15.

Empirical, versioned HistData availability inference is permitted for research
qualification. This supplements ADR-013/014/015: recurring feed absence can now
be evidence without exchange/broker session attestation. It is never evidence of
official market hours. Execution eligibility MUST NOT use this calendar. P2/P3
continue to require live validated broker evidence; execution stays HARD DISABLED.

The owner authorizes conservative deterministic confidence thresholds. Initial
2021 policy requires 100% absence of a weekly UTC minute slot, at least 48 complete
observed weeks and at least 12 complete observed weeks per quarter. Whole-year
slots require no observation anywhere in 2021. Additionally, quarter-specific slots
require no observation anywhere in that quarter, with at least 12 complete observed
weeks of support. Calendar quarters are fixed UTC partitions, not inferred DST
dates. Any observation vetoes closure for its corresponding comparison period.
This is deliberately stricter than a 99% rule and cannot hide isolated gaps.
Full 2021 provides 51 complete Monday-based
weeks; the actual observed-week/quarter counts are persisted and must pass.
The first annual-only diagnostic found 2880 always-absent weekly minutes for each
feed, insufficient to represent seasonal recurring breaks. The quarter comparison
is explicit derivation version v2, not a silent weakening of unknown-gap tolerance.

Full UTC days absent across all three independently indexed instruments may be
described as EMPIRICALLY_OBSERVED_HOLIDAY_OR_SPECIAL_CLOSURE, retaining each source
dataset identity. This does not distinguish holiday from shared provider outage.
Partial-day/isolated missing intervals remain UNKNOWN unless separately evidenced.

UTC-anchored 1H/4H aggregation requires 100% of EXPECTED M1 constituents. No candle
is emitted for a fully closed bin. A partly closed bin aggregates only its complete
observed expected constituents, preserving calendar/source identity and expected
minute counts. No missing intra-session price is invented; unknown gaps still
break continuous queries. Old complete-only datasets remain immutable.

Model, dataset and qualification IDs bind source/version/provenance. Derivation
uses the full year and is explicitly retrospective, not out-of-sample validation
or permission to use future information in P6 trading research. Reuse beyond 2021
requires a new derived version. No numerical unknown-gap tolerance is approved.
P5 completion still requires real multi-month coverage for all six combinations.
