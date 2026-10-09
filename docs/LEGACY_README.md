# Archived Pre-Rebuild README

Historical documentation only. These architecture and feature claims do not describe the current application.
The default application is the review-only controlled rebuild described in ../README.md.

A paper-trading multi-agent simulation with a real-time React dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              React Dashboard (Vite local port 5173)              │
│              Real-time WebSocket ← FastAPI (Port 8000)          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │     Master Orchestrator  │  ← Weighted signal aggregation
              │  (Conflict Resolution)   │    Vote-based decision making
              └────┬───────────────┬────┘    Agent weight auto-tuning
                   │               │
        ┌──────────▼───┐   ┌───────▼──────────┐
        │  Event Bus   │   │  Agent Weights   │
        │ (asyncio Q)  │   │ (Learning Agent) │
        └──────┬───────┘   └──────────────────┘
               │
    ┌──────────┼─────────────────────────────────────────┐
    │          │                                         │
    ▼          ▼          ▼          ▼          ▼        ▼
Strategy   Risk Mgmt   Sentiment  Execution  Portfolio  Regime
 Agent      Agent       Agent      Agent     Manager   Detector
    │          │
    ▼          ▼
Broker Momentum  Backtesting  Learning  Compliance
Confirmation      Agent       Agent     Agent
    │
    ▼
Market Data Pipeline
(GBM Simulator / Real WebSocket)
```

---

## Agents

| Agent | Role | Veto Power |
|---|---|---|
| **Master Orchestrator** | Signal aggregation, final decisions | — |
| **Strategy Agent** | Technical analysis, 4 strategies | No |
| **Risk Management** | Position sizing, stop-loss, kill switch | YES |
| **Execution Agent** | Order lifecycle, slippage control | No |
| **Sentiment Agent** | NLP news scoring, exponential decay | No |
| **Broker Momentum Confirmation** | Independent broker-tick confirmation for Exness symbols | No |
| **Portfolio Manager** | P&L tracking, performance metrics | No |
| **Regime Detection** | Market classification (Bull/Bear/Crisis) | No |
| **Compliance Agent** | PDT, wash sale, restricted lists | YES |
| **Backtesting Agent** | Historical simulation, Monte Carlo | No |
| **Learning Agent** | Online weight updates from outcomes | No |
| **Trader Learning / Imitation Agent** | Observation-only learner for private provider signal patterns | No |

---

## Quick Start

```bash
# Option 1: Shell script
chmod +x start.sh
./start.sh

# Option 2: Manual
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install && npm run dev
```

**Dashboard:** http://localhost:5173  
**API Docs (Swagger):** http://localhost:8000/docs  
**WebSocket:** ws://localhost:8000/ws

---

## Configuration (Environment Variables)

The backend reads configuration from a `.env` file in `backend/` at startup. Copy
`backend/.env.example` to `backend/.env` and adjust values locally. The `.env` file is
git-ignored and should never be committed.

| Variable | Default | Description |
|---|---|---|
| `TRADING_MODE` | `paper` | `paper` = simulated fills only; `exness_demo` = MT5 demo broker execution |
| `INITIAL_CAPITAL` | `100000` | Starting paper capital |
| `MAX_PORTFOLIO_RISK_PCT` | `0.02` | Max capital at risk per trade |
| `MAX_DAILY_LOSS_PCT` | `0.05` | Kill-switch trigger (5%) |
| `MAX_DRAWDOWN_PCT` | `0.15` | Kill-switch trigger (15%) |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Server bind address |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Allowed CORS origins |
| `APP_ENV` | `development` | Set `production`, `prod`, or `staging` to require a control token |
| `CONTROL_TOKEN` | _(unset)_ | Required as `X-Control-Token` for `/api/controls/*` in production-like environments |
| `ORCHESTRATOR_MIN_FINAL_CONFIDENCE` | `0.60` | Minimum normalized confidence before a BUY/SELL can be dispatched |
| `ORCHESTRATOR_MIN_STRATEGY_CONFIDENCE` | `0.55` | Minimum Strategy Agent confidence required by the strict gate |
| `ORCHESTRATOR_MIN_CONFIRMATION_CONFIDENCE` | `0.52` | Minimum independent confirmation confidence required by the strict gate |
| `ORCHESTRATOR_COOLDOWN_SECONDS` | `120.0` | Minimum seconds between trade decisions for the same symbol |
| `NEWS_API_KEY` | _(unset)_ | **NewsAPI.org key for real news sentiment** |
| `DEEPSEEK_API_KEY` | _(unset)_ | Optional DeepSeek key for private screenshot signal extraction |
| `DEEPSEEK_VISION_MODEL` | `deepseek-v4-flash-vision-exp` | Vision model used by execution-upload screenshot parsing |
| `BROKER` | _(unset)_ | Set `exness_mt5` to use the Exness MT5 demo adapter |
| `EXNESS_DEMO_LOGIN` | _(unset)_ | Exness MT5 demo account number |
| `EXNESS_DEMO_PASSWORD` | _(unset)_ | Exness MT5 demo password; never commit this |
| `EXNESS_DEMO_SERVER` | _(unset)_ | Exness MT5 demo server name |
| `EXNESS_MT5_PATH` | _(unset)_ | Optional path to `terminal64.exe` |
| `EXNESS_SYMBOLS` | `XAUUSDm,EURUSDm,BTCUSDm,USOILm` | Symbols streamed from MT5 into the agents and dashboard |
| `EXNESS_TRADE_SYMBOLS` | `EURUSDm,USOILm,XAUUSDm` | Broker symbols allowed to receive demo orders |
| `EXNESS_ENABLE_DEMO_TRADING` | `false` | Must be `true` before MT5 demo orders are sent |
| `EXNESS_ALLOW_MIN_VOLUME_ROUND_UP` | `false` | Demo-only option to round tiny risk-sized orders up to broker minimum lot |
| `EXNESS_MAX_ORDER_VOLUME` | `0.01` | Hard cap on MT5 lot size per demo order |
| `EXNESS_MAX_ORDER_RISK_USD` | `2.0` | Hard cap on estimated stop-loss risk after broker lot rounding |
| `EXNESS_MARKET_DATA_INTERVAL` | `2.0` | MT5 quote polling interval in seconds |
| `EXNESS_RECONCILE_INTERVAL` | `5.0` | MT5 account/position reconciliation interval in seconds |
| `TRADE_JOURNAL_DB` | _(unset)_ | Optional private SQLite journal path; defaults under `backend/data/` |
| `PRIVATE_ID_HASH_SALT` | _(unset)_ | Local salt for hashing private signal identifiers |
| `IMAGE_SIGNAL_MIN_RISK_REWARD_RATIO` | `1.5` | Minimum R/R for private uploaded image signals |

**News sentiment (optional):**
By default the Sentiment Agent uses **simulated** news headlines. To have it react to
**real** headlines, set a NewsAPI key:

```
# in backend/.env
NEWS_API_KEY=your_newsapi_key_here
```

When the key is present, the agent polls NewsAPI for each tracked symbol (AAPL, MSFT,
TSLA, BTC-USD, ETH-USD, SPY) and scores the real headlines with the built-in VADER NLP
engine. Check status via `GET /api/stats` → `sentiment_nlp.real_news`.
Note: NewsAPI's free tier is limited (~100 requests/day); with 6 polled symbols you may
hit the daily cap if the process runs continuously all day.

**Exness MT5 demo link (optional):**
The Exness adapter connects through the local MetaTrader 5 terminal. By default it reads
account status and quotes only. Demo order execution requires both `TRADING_MODE=exness_demo`
and `EXNESS_ENABLE_DEMO_TRADING=true`.

```bash
cd backend
python -m pip install MetaTrader5==5.0.6147
```

Then set the Exness demo variables in `backend/.env` and restart the backend. Check:

```
GET  /api/broker/exness
POST /api/broker/exness/connect
GET  /api/broker/exness/account
GET  /api/broker/exness/positions
GET  /api/broker/exness/quote/XAUUSDm
```

To allow demo orders, use a small allowlist and a hard volume cap:

```env
TRADING_MODE=exness_demo
EXNESS_ENABLE_DEMO_TRADING=true
EXNESS_TRADE_SYMBOLS=EURUSDm,USOILm,XAUUSDm
EXNESS_MAX_ORDER_VOLUME=0.01
EXNESS_MAX_ORDER_RISK_USD=2.0
EXNESS_ALLOW_MIN_VOLUME_ROUND_UP=true
```

In Exness demo mode the system:
- connects MT5 on startup
- syncs risk/portfolio capital from demo account equity
- streams configured Exness quotes into the agents and does not run simulated market-data trading at the same time
- attaches MT5 M1 OHLCV candles when available, so broker-symbol indicators use recent candle history instead of random or flat fallbacks
- reconciles local portfolio, risk exposure, and execution state from MT5 account/open-position snapshots
- lets the Sentiment Agent emit broker-symbol news signals for `EURUSDm`, `USOILm`, `XAUUSDm`, and `BTCUSDm`
- adds a Broker Momentum Confirmation Agent for configured Exness feed symbols
- sends approved risk-cleared orders through `order_check` and `order_send`
- records broker/risk rejections in `/api/orders` so blocked trades are visible
- rejects non-demo accounts and symbols outside `EXNESS_TRADE_SYMBOLS`
- rejects broker-minimum lot rounding if it exceeds the approved stop-loss risk

Learning endpoints:

```
GET  /api/private/trader-learning/summary
POST /api/private/trader-learning/import
```

Trader learning is observation-only. It records private examples locally for future
analysis and does not place trades or bypass the risk/execution agents.

Private screenshot execution upload:

```
POST /api/private/signals/image/parse
POST /api/private/signals/image/submit
GET  /api/private/signals/image/recent
```

This path uses DeepSeek Vision only to extract a structured signal from an uploaded
image. Submission still goes through deterministic validation, risk agent, and
execution agent.

Check readiness and local audit trail:

```
GET /api/private/readiness
GET /api/private/journal/signals
GET /api/private/journal/alerts
```

Never publish `.env`, uploaded signal images, private journals, broker credentials, model
checkpoints, or private trade history.

---

## Going Live — Production Checklist

### 1. Real Market Data
```python
# Replace data/pipeline.py MockDataSource with:
# Alpaca WebSocket (equities + crypto)
from alpaca.data.live import StockDataStream
stream = StockDataStream(API_KEY, SECRET_KEY)

# Binance WebSocket (crypto)
from binance import AsyncClient, BinanceSocketManager

# Polygon.io (paid market-data provider)
from polygon import WebSocketClient
```

### 2. Real Broker Integration
```python
# execution_agent.py — set_live_broker()
from alpaca.trading.client import TradingClient
broker = TradingClient(api_key=API_KEY, secret_key=SECRET_KEY, paper=False)
execution_agent.set_live_broker(broker)
```

### 3. Real NLP for Sentiment
```python
# Replace mock in sentiment_agent.py with:
from transformers import pipeline
finbert = pipeline("sentiment-analysis", model="ProsusAI/finbert")
result = finbert(headline)[0]  # {"label": "positive", "score": 0.94}
```

### 4. Real Technical Indicators
```bash
pip install TA-Lib
```
```python
import talib
rsi = talib.RSI(close_prices, timeperiod=14)
macd, signal, _ = talib.MACD(close_prices)
```

### 5. Database (TimescaleDB)
```python
# Replace in-memory storage with TimescaleDB
# Best for time-series trade data
import asyncpg
conn = await asyncpg.connect("postgresql://trader:pw@localhost/hedgefund")
await conn.execute("INSERT INTO trades VALUES ($1, $2, $3)", ...)
```

### 6. Security
- Add JWT auth to all endpoints (fastapi-users)
- Rotate API keys via environment variables (never hardcode)
- CORS: replace `*` with your domain
- Rate limiting: `pip install slowapi`
- TLS: put FastAPI behind nginx with Let's Encrypt

---

## API Reference

### WebSocket Events
Connect to `ws://localhost:8000/ws` — receives all system events in real-time.

Event types:
- `strategy.signal` — Trading signal from Strategy Agent
- `sentiment.signal` — NLP sentiment signal
- `order.filled` — Order execution confirmation
- `risk.breach` — Risk limit violation
- `risk.kill_switch` — Emergency stop activated
- `market.regime.change` — Bull/Bear/Crisis regime change
- `system.agent_status` — Agent heartbeat/health

### REST Endpoints

```
GET  /api/health          System health + pipeline stats
GET  /api/portfolio       Portfolio state + performance metrics  
GET  /api/agents          All agent health checks
GET  /api/signals         Recent trading signals
GET  /api/orders          Order history + open orders
GET  /api/risk            Risk parameters + exposure
GET  /api/sentiment       NLP sentiment by symbol
GET  /api/decisions       Orchestrator decision log
GET  /api/events          Persisted event audit log
GET  /api/broker/exness   Exness MT5 demo connection/status
GET  /api/broker/exness/account  Sanitized Exness demo account snapshot
GET  /api/broker/exness/positions  Sanitized Exness demo open positions
GET  /api/broker/exness/quote/{symbol}  Exness MT5 bid/ask quote

POST /api/controls/agent          Pause/resume any agent
POST /api/controls/kill-switch    Emergency stop (closes all)
POST /api/controls/reset-kill-switch  Re-enable trading
POST /api/controls/risk           Hot-reload risk parameters
POST /api/controls/watchlist      Add/remove symbols
POST /api/controls/inject-shock   Stress test: inject price shock
POST /api/controls/inject-test-signals  Dev-only paired signal injection
POST /api/broker/exness/connect   Connect Exness MT5 demo adapter
POST /api/broker/exness/disconnect  Disconnect Exness MT5 adapter
```

Control endpoints are open only in local/development mode. For `APP_ENV=production`,
`APP_ENV=prod`, or `APP_ENV=staging`, send `X-Control-Token: <CONTROL_TOKEN>`.

---

## Test Suite

```bash
cd backend
python -m pytest
```

Current regression coverage checks:
- flat `price` propagation into risk sizing, no silent `$100` fallback
- invalid price rejection
- broker-tick indicator warmup and observed-history calculations without random strategy inputs
- MT5 M1 OHLCV payload ingestion for broker-symbol indicators
- strict strategy-plus-confirmation orchestration before a trade can reach risk
- confidence-gate rejection for weak strategy/confirmation agreement
- JSON-safe portfolio metrics when profit factor is undefined
- hard loss threshold kill-switch activation
- kill-switch blocking in the orchestrator
- live-mode broker rejection without fake fills and broker fill event publishing
- rejected orders remain visible in order history
- stop-loss and kill-switch portfolio closure
- production control-token enforcement
- persisted audit event reads
- Exness MT5 adapter status, sanitized account output, open positions, quote reads, and demo order handoff

CI is defined in `.github/workflows/ci.yml` and runs backend install, compile, tests,
frontend install, `npm audit`, and production build.

---

## Risk Parameters (Default)

| Parameter | Default | Description |
|---|---|---|
| `max_portfolio_risk_pct` | 2% | Max capital at risk per trade |
| `max_total_exposure_pct` | 20% | Max total capital deployed |
| `max_single_position_pct` | 5% | Max in any single name |
| `max_daily_loss_pct` | 5% | Kill switch trigger |
| `max_drawdown_pct` | 15% | Kill switch trigger |
| `min_risk_reward_ratio` | 1.5 | Minimum R/R to trade |

---

## What's NOT Included (v2 roadmap)

1. **Arbitrage Agent** — Requires multi-exchange connectivity + co-location
2. **Macro/Economic Agent** — FRED API integration, needs real macro data
3. **Shadow Trading Agent** — Parallel paper track alongside live
4. **Explainability Agent** — SHAP values for each trade decision
5. **Market Rotation Agent** — Cross-asset capital reallocation
6. **Real RL** — Requires 100k+ episodes; use after 6 months of paper data

---

## Disclaimer

⚠️ **This is for educational and research purposes only.**  
⚠️ **Paper trading only in default configuration; Exness execution is demo-account only.**  
⚠️ **Not financial advice. Trading involves substantial risk of loss.**  
⚠️ **Never deploy to live trading without extensive testing and professional review.**

---

## Known Limitations

- Paper mode only by default; Exness execution is limited to MT5 demo accounts.
- Simulated market data remains available in paper mode; Exness demo mode streams configured MT5 quotes into the agents and avoids mixed simulator/broker execution.
- No full authentication, user authorization, rate limiting, TLS, or production CORS policy.
- Control endpoints require `CONTROL_TOKEN` in production-like environments, but this is not a replacement for full auth.
- Risk controls are internal simulation guardrails and still require stress testing before any live use.
- Broker-symbol indicators use MT5 M1 OHLCV candles when available, with observed tick history as a fallback.
- Exness integration requires a local Windows MT5 terminal and demo credentials in `backend/.env`.
- Broker minimum lots can exceed the simulator's desired risk size on very small demo balances.
