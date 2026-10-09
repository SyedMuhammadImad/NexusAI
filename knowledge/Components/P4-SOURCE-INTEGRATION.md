# P4 - Non-Executing Source Integration

Authority: ADR-001/002/003/008/010/012 and the owner's P4 implementation request.
Scope: authenticated, fixture-verified source integration. No native broker,
operator database, credentials, live WhatsApp session, strategy or ML activation.

## Contracts and Entry Point

`POST /api/core/sources/ingest` uses the existing `X-Control-Token` authentication.
The shared domain service is `SourceIngestion.ingest(SourceSubmission)`.
Required common fields: `source_type`, `source_id`, `message_id` (idempotency key),
`original_timestamp`, `timezone_evidence`, and nonempty string-map `provenance`.
Unknown fields, conflicting raw/structured inputs and reserved provenance keys
reject. HTTP validation errors do not echo submitted values; the adapter does not
log request bodies. This is a trusted authenticated adapter boundary, not proof
that a caller-supplied WhatsApp identity was cryptographically verified by WhatsApp.

| Source | Additional input | Result / eligibility |
|---|---|---|
| MANUAL | Structured `signal` | Canonical signal; P2_ONLY when configured |
| WHATSAPP_HUMAN | `raw_text`, allowlisted `sender_id`, exact `group_id` | Deterministic parse; P2_ONLY only while fresh |
| NEXUSAI_STRATEGY | Structured `signal`, `strategy_id`, `strategy_version` | UNQUALIFIED; NONE |
| HISTORICAL_WHATSAPP | `raw_text`; existing P1-M2 archive bridge also retained | Review/research; NONE |
| SCREENSHOT | `evidence_ref`, optional structured `signal` or raw extraction | Review/research; NONE, including extracted signals |

Structured fields: `instrument`, `direction` (BUY/SELL), `entry_type`
(MARKET/LIMIT), optional positive `entry`, positive `stop_loss`, one to three
positive `take_profit` values, optional `requested_risk_pct` in percent units.
LIMIT requires entry. Finite values and direction-aware geometry are validated.
MARKET without source entry remains absent, not filled with a guessed quote.
Existing deterministic_v3_p2 parsing produces signal.v2; broker eligibility and
the exact P2 instrument allowlist still belong to P2, not to parser acceptance.

Example synthetic MANUAL body (not a trading recommendation):

```json
{
  "source_type": "MANUAL", "source_id": "manual-fixture",
  "message_id": "example-001",
  "original_timestamp": "2026-09-13T12:00:00+00:00",
  "timezone_evidence": "UTC", "provenance": {"origin": "fixture"},
  "signal": {"instrument": "XAUUSDm", "direction": "BUY",
    "entry_type": "MARKET", "stop_loss": 90, "take_profit": [130]}
}
```

## Registry and Time Policy

Trusted app composition injects `SourceConfiguration(revision, sources)`;
there is no external registry-edit endpoint. Each `SourceRule` contains identity,
type, strict enabled flag, NONE/P2_ONLY eligibility, provenance requirements,
sender/group restrictions, freshness_seconds (default 600), adapter/parser
versions and UNQUALIFIED state. Research sources cannot be configured P2_ONLY.
Strategy qualification is not user-assertable. Numeric P2 limits are unchanged.

Migration 008 appends immutable configuration revisions and payload hashes.
Changed configuration requires an increasing revision. Replaying the identical
configuration is harmless. New P2 decisions retain the source-policy revision/hash;
an unused approval cannot create a request under a different registry revision.

The ordinary unbound app installs/reloads a deny-by-default registry. Unknown live
identities reject. Existing explicitly injected P1-P3 synthetic-account fixture
compositions without P4 configuration retain their prior test-only behavior.
Installing P4 into a ledger with existing P3 attempts rejects, rather than hiding
economic history. No existing operator store was opened or migrated in this task.

The existing archive bridge has a fixed HISTORICAL_WHATSAPP review-only default
rule for unprovisioned archive identities. It cannot authorize a live source.
An explicit disabled or mismatched identity still rejects. This preserves archive
dedup/review linkage without rewriting P1-M2 or confusing review with safety approval.

UTC normalization requires an explicit ISO offset and matching timezone evidence
(`UTC`/`Z` for zero offset, numeric offset, or `ISO_OFFSET`). Unresolved time is
stored as evidence with REVIEW_REQUIRED and no canonical signal. No timezone is
guessed. Existing P1/P2 zero-future admission semantics are retained; P4 introduces
no future tolerance. Exactly 600 seconds is fresh by default; greater age is
review-only. Freshness is rechecked at intent creation, P2 evaluation and request
eligibility, not only on receipt. Original timestamp and first receipt survive replay.

## Lifecycle, Replay and Lower-Layer Enforcement

Identity derives from source type + identity + message ID. The complete submitted
body hash detects conflicting reuse. Same text under distinct legitimate message
identities remains independent. Source and signal persistence use the existing
serialized transactions as restartable checkpoints: a crash after source commit
does not require another source identity. Parsing retry produces the same signal ID.

Raw text, structured-input provenance, sender/group, timestamp/timezone, adapter and
parser versions, registry revision and evidence references remain in SourceEvent.
Screenshot reference-only input does not manufacture extracted signal fields.
Malformed parser input is retained with REVIEW_REQUIRED / PARSER_REJECTED.

Ingestion returns IDs, validation/review status and source eligibility. It does not
automatically choose volume, create a safety approval or submit an order. Eligible
callers use existing authenticated lifecycle intent/evaluate/request endpoints;
P2 requires trusted account/risk evidence and independently sizes and rejects.
The normal unbound application cannot create account-bound economic intents.

`LifecycleService.save_source` enforces source authorization. `Ledger.save_signal`
checks canonical source/time/parser linkage and reparses raw evidence to reject
forged signal fields. `Ledger.create_intent`, `SafetyEngine._calculate` and
`eligible_request` enforce source restrictions below HTTP. Historical/screenshot
P1 firewalls remain in place; strategy execution is blocked pending later phases.

## Persistent Broker Block

`Source -> SourceEvent -> CanonicalSignal -> eligible TradeIntent -> P2 ->
ExecutionRequest -> HARD BROKER BLOCK`.

P4 app configuration cannot be paired with an execution adapter. Submission writes
are not enabled in its HTTP allowlist. ExecutionEngine rejects a P4 ledger;
snapshot access rechecks the block, including an older engine object. Migration
008 forbids insertion of P3 attempts whenever a P4 registry exists. Configuration
rows cannot be updated/deleted to clear this block. P2 reset/approval and process
restart do not enable execution. This is application/storage enforcement, not an
OS sandbox against an administrator modifying code or schema.

## Verification and Limits

Evidence: `tests/test_p4_sources.py` plus P1 historical, P2, P3 and guarded broad
regressions recorded in TESTING.md. Includes authenticated API composition,
malformed fields, timestamps/boundaries, raw preservation, unauthorized/disabled
identities, five-source replay, concurrent retry, checkpoint restart, exact lineage,
source-policy invalidation, HALT/P2 veto and persistent broker-block bypass tests.

Not proven: live WhatsApp delivery/sender attestation, native demo execution,
operator qualification, OCR accuracy, strategy qualification, profitability,
production deployment or hostile-process isolation. P3 operator verification stays
DEFERRED. P5-P9 remain non-executing; this work does not start them.
