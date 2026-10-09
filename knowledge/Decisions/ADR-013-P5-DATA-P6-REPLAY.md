# ADR-013 - P5 Data Qualification / P6 Strategy Replay

Status: **ACCEPTED**. Authority: explicit owner decision, 2026-09-14.

P5 owns qualified, immutable REAL datasets and their deterministic research query
interface, not trading strategies. Move the known-strategy replay exit gate from
P5 to P6. P6 is not authorized here. P5 requires meaningful real history for each
instrument, qualified 1H/4H datasets, stable identity/provenance, classified quality,
gap-aware queries and no synthetic candles. Download success is not qualification.

The owner permits qualified-with-known-limitations only with explicitly bounded
uncertainty. Preserve raw data/flags. Unresolved intervals remain unavailable to
ordinary contiguous research queries. Explicit segmented queries return only
validated segments plus exclusions/boundaries, never artificial continuity.
Unbounded corruption or missing provenance stays REVIEW_REQUIRED/REJECTED.
No numerical gap budget or price-jump tolerance is approved or invented.

Session closures need evidence, not calendar guesses. Instrument/broker mappings
remain research proxies; volume/spread absence stays visible. Kronos runtime is
optional. No strategy/model/broker activation. ADR-008/010/012 execution locks and
P3 operator deferral are unchanged.
