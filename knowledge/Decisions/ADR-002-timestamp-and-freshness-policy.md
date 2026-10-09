# ADR-002 — Timestamp and Freshness Policy

Status: **ACCEPTED**  
Accepted during P0 governance review.

## Decision

Live source events preserve their original timestamp and timezone evidence and normalize an authoritative timestamp to UTC.

For live WhatsApp signals:

- preserve the original timestamp and source evidence;
- normalize to UTC;
- reject ambiguous/unparseable timestamps rather than guessing;
- reject materially future-dated signals;
- calculate signal age at the actual action boundary;
- use a configurable freshness policy;
- initial default freshness window: **10 minutes**;
- expired signals may be stored/reviewed but cannot execute.

Historical sources are explicitly tagged historical, are exempt from live freshness eligibility, and are never execution-capable.

## Invariants

- The 10-minute value is an initial policy value, not a hard-coded architectural truth.
- Timezone must never be silently assumed when evidence is ambiguous.
- Freshness must be re-evaluated where economic action is authorized, not only when parsing occurs.
- Policy changes require configuration/version evidence and must not silently alter historical records.

## Deferred detail

Exact tolerance for “materially future-dated” is configuration/policy detail to be specified and tested before P4 execution eligibility.
