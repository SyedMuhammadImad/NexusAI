# Known Limitations

> SUPERSEDED: this is preserved pre-rebuild documentation, not current behavior.
> The current application is authenticated historical review only, with execution and training disabled.
> See `../KNOWN_LIMITATIONS.md` and `../docs/REBUILD_STATUS.md`.

This system is not production-ready trading infrastructure. Current verified use is local paper trading plus guarded Exness MT5 demo trading.

## Trading Scope

- Exness support is demo-account only. The broker adapter rejects non-demo accounts.
- Private signal ingestion is screenshot-upload based and requires `DEEPSEEK_API_KEY`.
- Uploaded image execution still goes through deterministic validation, risk checks, and the execution agent.
- Non-market uploaded entries are rejected. Limit/range entry execution is not implemented yet.
- Per-symbol close/exit messages are not implemented yet. Emergency `CLOSE_ALL_POSITIONS` exists through the kill switch path.

## Security

- `.env` files, broker credentials, private journals, uploaded signal images, checkpoints, and trade history must remain local and private.
- Control endpoints require `CONTROL_TOKEN` only in production-like `APP_ENV` values. Local development is intentionally frictionless.
- Read endpoints still expose portfolio and system status without user authentication.
- No TLS, rate limiting, user accounts, or role-based permissions are implemented.

## Data And Models

- Sentiment uses NewsAPI only when `NEWS_API_KEY` is configured; otherwise it uses simulated headlines.
- The learning, compliance, and backtest agents are still lightweight local modules, not institutional-grade learning or compliance systems.
- No model checkpoint lifecycle, walk-forward validation, or live retraining approval flow exists.
- Docker validation was not performed on this machine because Docker is unavailable.

## Reliability

- Order history combines in-memory state with persisted order lifecycle events, but a full trade-decision audit UI is still missing.
- Broker reconciliation updates open-position state, but detailed mismatch/orphan-order escalation still needs a stronger alert workflow.
- Long soak testing across restarts, network failures, MT5 disconnects, and provider outages is still required before increasing risk.
