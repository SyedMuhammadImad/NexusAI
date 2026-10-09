# ADR-017 - Alternative Provider and Native-Bar Research Qualification

Status: **ACCEPTED** for the explicit owner's alternative-provider P5 task,
2026-09-15. This records that authorization, not a new numerical gap tolerance.

## Decision

HistData need not be the sole P6 research source. Preserve its raw archives,
canonical versions, ADR-016 calendars and all prior qualifications unchanged.
One dataset has one primary provider. Never splice providers to conceal gaps.

The task explicitly permits trustworthy native 1H/4H bars instead of local M1
resampling. EV Trading Labs public closed-year exports are admitted as a distinct
distributor/provider, not relabelled direct Dukascopy downloads. Preserve BID
OHLC, separate ASK OHLC, Unix UTC bar-open timestamps and unknown-unit volume.
Upstream attribution is a distributor assertion; research mappings are not
broker-symbol or futures-contract equivalence.

ADR-015's explicit documentary market inference applies to a separately versioned
2021-2025 regular-hours model, checked against every distributor hourly observation.
Use pinned New York timezone rules for the documented upstream daily/weekend
schedule; any observed hour contradicting the model rejects qualification.
Unconfirmed holiday/early-close/provider absences remain UNKNOWN and split ranges.
No empirical threshold from HistData is reused or relaxed. No execution calendar
or numerical missing-data allowance is authorized.

Native 4H bars may span closed hours, but must match the bid AND ask OHLC of their
observed hourly constituents. Every expected open hourly constituent must exist.
A completely closed bin emits no research observation. A missing expected hour
withholds the affected 4H research interval, even if a native 4H bar exists.
Preserve the original native bar; do not overwrite or manufacture a replacement.
This is native-hourly qualification, NOT independently verified tick/M1 coverage.

## Consequences

Qualification IDs pin provider, dataset, hourly reference, calendar, normalizer
and validation rule. Only proven segments may be queried; full five-year presence
is not full five-year contiguous qualification. Public-export qualification uses
an additive immutable research-store table/schema marker 6, not an operator DB.

HistData retains its earlier identity and rules. Cross-provider differences are
diagnostics, not permission to alter either source. Research selection/calendar
checks are retrospective and do not prove out-of-sample performance.

P5 may close when its existing data exit gates pass for all three instruments and
both timeframes. P6 remains unimplemented in this task. Broker execution stays
HARD DISABLED; P3 operator verification remains DEFERRED. No change to ADR-010.

Evidence and sources: Components/P5-ALTERNATIVE-PROVIDER.md and
Audits/P5-ALTERNATIVE-PROVIDER-CLOSEOUT.md.
