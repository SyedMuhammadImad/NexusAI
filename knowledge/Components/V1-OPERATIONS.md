# V1 Non-Executing Operations Integration

2026-10-02 source follow-up: actual linked account/state, approved sender PN/LID
and REDACTED_SOURCE announcement membership/admin verified; exact IDs private.
32 connector tests pass. Source details are now evidenced, but connector/source
registry binding, live message delivery and economic composition remain off.
See V1-WHATSAPP-SOURCE-IDENTITY.md; no phase or broker qualification follows.

2026-10-02 setup update: login-first pair.mjs reached actual WhatsApp client ready,
without forwarding messages or connecting brokers. Group/sender authorization,
reconnect/delivery and operational composition remain unverified. Current
dependency audit0 known vulnerabilities;13 connector tests pass. This supersedes
dated advisory counts below, not the non-executing limits or retained history.
Owner-reported USD100, unchanged risk limits and strategy2R target clarification:
V1-DEMO-100-SETUP.md. No automated weekly strategy replacement is enabled.

Checkpoint: 2026-09-28. Status: PARTIAL. Authority: ADR-018.
No broker or WhatsApp session was opened. No protected operator state was read.

## Implemented Modules

- `backend/core/rebuild/operations.py`: durable manual/WhatsApp admission, source
  identity/replay guard, existing P1/P2 calls, audit controls, disabled deployments,
  worker health, alert acknowledgment and read-only export.
- `monitoring.py`: fresh persisted P2 input projections, per-source/instrument
  decision counts and explicitly separate retained reservation totals.
- `operations_routes.py`: authenticated workspace API; no submission/unhalt route.
- `migrations/009_v1_operations.sql`: additive stores; audit records immutable.
- `connectors/whatsapp/bridge.mjs`: deterministic authorized text envelopes,
  private durable outbox, uncertain delivery retry with the same message identity.
- `connectors/whatsapp/operator.mjs`: operator-only WhatsApp Web bootstrap. NOT RUN.
- `frontend/src/OperationsWorkspace.jsx`: seven views, manual P2 proposal form,
  unavailable-value states, disabled controls/registrations, alert ack and export.
  Arena and historical review retain their existing separate hash routes.

## Contracts And Limits

Manual/WhatsApp ingestion never invokes ExecutionEngine. P2 supplies the actual
allocation; the legacy intent volume mirror is not authoritative sizing.
Persisted decisions and request IDs remain linked to the source event/signal.
Concurrent duplicate envelopes reuse one intent/decision/request. A changed payload
with the same identity is rejected. Incomplete/ambiguous input cannot become an
intent. Some parser failures share QUARANTINED_AMBIGUOUS rather than the requested
finer REJECTED_MISSING_FIELDS taxonomy; this is a remaining classification gap.

The backend currently accepts FIXTURE accounts only. SourceConfiguration and
migration 008 continue to prohibit broker composition. Controls default off;
attempts to enable any source reject. Disabled registry IDs map to unchanged
P6 EMA9/21, EMA20/50, MACD, Supertrend and Donchian definitions. There is no live
strategy worker, no deployment performance, and no native-bar ingestion here.

Monitoring uses one read transaction. Report identity hashes the complete payload,
including observation time; deterministic for identical state/time/window, not a
promise that separate real-time snapshots share an ID. The UTC activity window
does not retroactively filter current economic state. Account equity requires fresh
complete reconciled P2 input; absent/stale values are null. Quotes carry timestamps
and age status. Exposure conversion/metadata must be fresh. Report has no broker
callbacks. Export is JSON, read-only, omits raw texts/native blobs/comments/secrets.
Opaque lifecycle IDs remain inspectable. It is not a tamper-signed external archive.
Existing deal rows and observation heads remain separate; no revision counts as
another economic fill. Do not treat first persisted deal fields as corrected P&L.

## WhatsApp Operator Setup (Later, Not An Activation Instruction)

Example: `backend/examples/v1-whatsapp-connector.example.json`, placeholders only.
Operator configuration belongs ONLY at `backend/private/whatsapp/v1/connector.json`.

| Field | Type / units | Source / sensitivity | Validation |
|---|---|---|---|
| backend_url | string, URL | Qualified local API endpoint; not secret | HTTP 127.0.0.1, root path, no userinfo/query/fragment |
| connector_token | string | Operator-generated scoped secret | At least 32 characters; exact match to backend connector-only binding |
| source_id | string | Trusted SourceConfiguration identity; private metadata | Must match enabled WHATSAPP_HUMAN source |
| group_id | string | Authenticated provider group ID; private metadata | Exact group including @g.us; display name not sufficient |
| sender_ids | nonempty string array | Authenticated authorized sender IDs; private metadata | Exact IDs required at connector AND P4; no suffix guessing |
| browser_executable | string, absolute path | Installed browser binary; not a password | Explicit operator path, dedicated new session directory |

The operator must supply secrets/linking and authorize the current sender/group.
Display names and old chat credentials are NOT used. Source admission configuration
and the factory's `whatsapp_connector_token` must be bound separately by a future
approved runtime composition. This example alone does not start a functioning
system. Backend ordinary control tokens are refused at the connector endpoint;
connector tokens cannot inspect or control the workspace.

Session/auth/outbox/QR files stay under that ignored private boundary. QR is not
printed in logs. Startup rejects links/hardlinked files; logs use fixed status
codes. LocalAuth persists reconnect state. Changed content for the same identity
is retained as conflict, never silently redelivered as a new signal. Retry after
uncertain HTTP response is at-least-once intake, not retry of a broker order.
Unsupported media is ignored; there is no OCR or inferred trading fields.

This is the unofficial whatsapp-web.js adapter, not official WhatsApp business
API. Upstream documents message.author as group sender, from as group, serialized
message ID, and timestamp in Unix seconds:
https://docs.wwebjs.dev/Message.html
https://github.com/wwebjs/whatsapp-web.js/
No live compatibility, QR link, reconnect or account-policy acceptance is claimed.
Dependency audit currently reports five high findings through the browser archive
extraction chain. This is a pre-link blocker, not a clean security audit. Install
only with PUPPETEER_SKIP_DOWNLOAD=true and --ignore-scripts while reviewing this
prototype; do not run a browser download or blindly apply npm audit's downgrade.
Known upstream advisory: https://github.com/advisories/GHSA-7pqw-9j4j-h8q3

## Safe Preview / Verification

From repository root:

```powershell
.\backend\.venv\Scripts\python.exe -B scripts/v1_preview.py --port 8001
```

This installs the existing normalized TESTING guard, fresh temporary SQLite store,
synthetic fixture account, manual source and persistent HALT. It cannot use any
native adapter. Synthetic preview token: `v1-fixture-preview` (not a real secret).
Vite uses `NEXUSAI_PREVIEW_BACKEND=http://127.0.0.1:8001`; default remains port8000.
Preview exposes only workspace/status/HALT and read-only Arena routes, not private
historical stores. Close the preview when no longer needed; no auto-start service.

`scripts/v1_ui_check.mjs` uses Playwright supplied through PLAYWRIGHT_ROOT and a
fresh headless browser context. It must only target the separate fixture preview.
Connector fixture verification: `node --test connectors/whatsapp/bridge.test.mjs`.
Backend verification uses the allowlisted guarded suite in TESTING.md, never broad
test discovery, default application startup, or private session inspection.

## Remaining Engineering (Not Just Credentials)

1. Qualify existing P3 isolated operator environment and minimum-volume real demo
   evidence using actual recorded risk history. No balances invented from history.
2. Implement/test conditional operational P4/P3 composition and enable controls,
   preserve safety revalidation, never replay old approvals into native submissions.
   Existing native P2 context is minimum-lot/empty-account smoke scope, not a proven
   general-volume/multiple-position account adapter.
3. Current closed broker candle contract, validated session/timeframe semantics,
   selected frozen strategies, deterministic candidate identity and P2 routing.
   Native BID bars must not be relabeled as historical provider or fabricated ASK.
4. Full P9 worker heartbeat/supervision, source duplicate/execution counters,
   revised broker projection, spread/slippage/latency, portfolio attribution,
   source/strategy realized/unrealized performance, uptime and P10 aggregates.
5. Actual authorized WhatsApp session/source proof, refined rejection taxonomy,
   reconnect/backfill proof and final A-H real-demo acceptance.

None of these items is completed merely by entering credentials or flipping a UI
switch. They remain explicit in the roadmap and acceptance report.
