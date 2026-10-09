# NexusAI

NexusAI is a controlled trading-system rebuild with an authenticated historical-review workspace, a typed lifecycle ledger, safety and source-ingestion contracts, offline research, and a tournament dashboard.

**The default application is halted and non-executing. This repository does not establish broker connectivity, profitable trading, or production readiness.** Native operator work and live account/session data stay local. The previous simulator implementation is retained as inactive source; its startup is blocked.

## Requirements

- Windows with Python 3.14 for the backend and fixture verification.
- Node.js 24 LTS with npm for the React/Vite frontend.
- Optional connector dependencies are separate from the default app.

## Install and run locally

From the repository root in PowerShell:

```powershell
py -3.14 -m venv backend/.venv
./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
npm --prefix frontend ci --ignore-scripts
./scripts/start_local.ps1
```

Open http://127.0.0.1:5173. The launcher creates a fresh local access token at `backend/private/control_token.txt`; enter that token in the workspace. Its value is never committed. Reloading locks the frontend again. Services bind to loopback. Do not expose this local prototype to the internet.

The repository includes a placeholder-only `backend/.env.example`. Do not copy someone else's credentials, broker configuration, session folders, or databases. The normal review app does not need an API key or broker login. On a fresh clone, archive review starts without personal historical records; import your own permitted archive locally if desired.

To stop the services, stop the Python and npm processes started by the launcher, or use separate terminals with `uvicorn main:app --host 127.0.0.1 --port 8000` from `backend` and `npm run dev` from `frontend` after generating the local token with `scripts/setup_local_access.py`.

## Verify without credentials

The full fixture selection includes optional offline research tests. The publication lockfile records the tested Windows/Python dependency set, including those packages; installing it does not activate training in the application.

```powershell
./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt
./backend/.venv/Scripts/python.exe -B scripts/verify_public_snapshot.py
npm --prefix frontend run build
npm --prefix connectors/whatsapp ci --ignore-scripts
node --test connectors/whatsapp/bridge.test.mjs connectors/whatsapp/identity.test.mjs connectors/whatsapp/compatibility.test.mjs connectors/whatsapp/pair.test.mjs
```

The backend verification uses explicitly reviewed fixture modules, scrubs caller environment variables, blocks protected runtime paths and forbidden native imports, and reports guard results. Do not substitute unrestricted discovery or start native/operator helpers for routine checks. Some Windows-specific fixtures require PowerShell. Fixture success does not qualify a broker, real session, or strategy. The guard is not an operating-system sandbox.

## Included files

- `backend/`: application, services, inactive agents, ledger/safety/research modules, all SQL migrations, dependency manifests and fixture tests.
- `frontend/`: React source, styles, build configuration and dependency lockfile.
- `connectors/whatsapp/`: optional connector source, placeholder contracts, dependency lockfile and mocked tests. Real pairing is an operator-only action.
- `scripts/`: local setup, guarded verification, isolated previews and operator tooling. Publication does not authorize operator actions.
- `knowledge/`: project charter, architecture, risk register, roadmap, engineering specification references, accepted decisions and sanitized evidence notes.
- `docs/`: design, rebuild status and historical documentation.

Private `.env` files, access tokens, session stores, broker/account details, databases, raw private chats, local logs, installed packages, media, model binaries and previous Git history are excluded. Missing private evidence referenced by historical notes is not recreated or claimed verified by this snapshot.

## Evidence and limits

The frontend dependency audit currently reports eight advisories (six high, two moderate) in the retained dependency tree. The CI security job preserves this failure; successful builds and credential scans do not erase it. No dependency migration or production-security qualification is claimed by this publication.

See [publication checks](PUBLICATION_CHECKS.json), [known limitations](KNOWN_LIMITATIONS.md), [engineering specification](NEXUSAI_V2_SPECIFICATION.md), [current-state history](knowledge/CURRENT-STATE.md) and [testing gates](knowledge/TESTING.md). Historical state notes are dated records; public publication checks describe this source snapshot only. Results that depend on local research artifacts or native operator evidence may be unavailable on a fresh clone.

This fresh repository is a sanitized snapshot of Syed Muhammad Imad's local NexusAI workspace. Source-level attribution and third-party package authorship remain intact. No software license is invented by publication.
