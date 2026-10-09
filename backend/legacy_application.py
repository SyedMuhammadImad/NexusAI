"""
FastAPI Application — REST + WebSocket API layer.

Exposes:
- /ws — Real-time event stream via WebSocket
- /api/portfolio — Portfolio state and metrics
- /api/agents — Agent health and status
- /api/signals — Recent trading signals
- /api/orders — Order history
- /api/risk — Risk parameters and current exposure
- /api/controls — Manual overrides (pause/resume/kill)

Security note: In production, add:
- JWT authentication on all endpoints
- Rate limiting (slowapi)
- CORS whitelist (not *)
- TLS/HTTPS
- API key rotation
"""

import asyncio
import hmac
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Header, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env before anything else
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# Import all system components
from core.event_bus import Event, EventType, get_event_bus
from core.orchestrator import MasterOrchestrator
from core.database import (init_db, save_trade, save_equity_snapshot,
    save_agent_weights, load_agent_weights, get_trade_history, get_performance_stats,
    save_event, get_event_history)
from agents.strategy_agent import StrategyAgent
from agents.risk_agent import RiskManagementAgent, RiskParameters
from agents.execution_agent import ExecutionAgent, TradingMode
from agents.sentiment_agent import SentimentAgent
from agents.broker_confirmation_agent import BrokerMomentumConfirmationAgent
from agents.portfolio_regime_agents import PortfolioManagerAgent, RegimeDetectionAgent
from agents.advanced_agents import ComplianceAgent, BacktestingAgent, LearningAgent
from agents.setup_learning_agent import SetupLearningAgent
from agents.trader_learning_agent import TraderLearningAgent
from brokers.exness_mt5 import ExnessMT5DemoBroker
from data.pipeline import MarketDataPipeline
from services.setup_learning_store import SetupLearningStore
from services.deepseek_vision_client import DeepSeekVisionError
from services.image_signal_service import ImageSignalService
from services.signal_parser import SignalParser
from services.trader_imitation_model import TraderImitationModelService
from services.trader_learning_store import TraderLearningStore
from services.trade_journal import TradeJournal
from services.chat_import_routes import chat_import_router

logger = logging.getLogger(__name__)
APP_ENV = os.getenv("APP_ENV", "development").lower()
CONTROL_TOKEN = os.getenv("CONTROL_TOKEN", "")
CONTROL_TOKEN_REQUIRED_ENVS = {"production", "prod", "staging"}
TRADING_MODE_ENV = os.getenv("TRADING_MODE", "paper").strip().lower()
EXNESS_MARKET_DATA_INTERVAL = float(os.getenv("EXNESS_MARKET_DATA_INTERVAL", "2.0"))
EXNESS_RECONCILE_INTERVAL = float(os.getenv("EXNESS_RECONCILE_INTERVAL", "5.0"))
ORCHESTRATOR_MIN_FINAL_CONFIDENCE = float(os.getenv("ORCHESTRATOR_MIN_FINAL_CONFIDENCE", "0.60"))
ORCHESTRATOR_MIN_STRATEGY_CONFIDENCE = float(os.getenv("ORCHESTRATOR_MIN_STRATEGY_CONFIDENCE", "0.55"))
ORCHESTRATOR_MIN_CONFIRMATION_CONFIDENCE = float(os.getenv("ORCHESTRATOR_MIN_CONFIRMATION_CONFIDENCE", "0.52"))
ORCHESTRATOR_COOLDOWN_SECONDS = float(os.getenv("ORCHESTRATOR_COOLDOWN_SECONDS", "120.0"))
IMAGE_SIGNAL_MIN_RISK_REWARD_RATIO = float(os.getenv("IMAGE_SIGNAL_MIN_RISK_REWARD_RATIO", "1.5"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")
    if origin.strip()
]

# ─── System singleton ─────────────────────────────────────────────────────────
class TradingSystem:
    orchestrator: Optional[MasterOrchestrator] = None
    strategy_agent: Optional[StrategyAgent] = None
    risk_agent: Optional[RiskManagementAgent] = None
    execution_agent: Optional[ExecutionAgent] = None
    sentiment_agent: Optional[SentimentAgent] = None
    broker_confirmation_agent: Optional[BrokerMomentumConfirmationAgent] = None
    portfolio_manager: Optional[PortfolioManagerAgent] = None
    regime_agent: Optional[RegimeDetectionAgent] = None
    compliance_agent: Optional[ComplianceAgent] = None
    backtest_agent: Optional[BacktestingAgent] = None
    learning_agent: Optional[LearningAgent] = None
    setup_learning_agent: Optional[SetupLearningAgent] = None
    trader_learning_agent: Optional[TraderLearningAgent] = None
    exness_broker: Optional[ExnessMT5DemoBroker] = None
    data_pipeline: Optional[MarketDataPipeline] = None
    trade_journal: Optional[TradeJournal] = None
    image_signal_service: Optional[ImageSignalService] = None
    trader_imitation_model: Optional[TraderImitationModelService] = None
    initialized: bool = False

system = TradingSystem()


def _execution_mode_from_env() -> TradingMode:
    if TRADING_MODE_ENV in {"live", "exness_demo", "demo"}:
        return TradingMode.LIVE
    return TradingMode.PAPER


def _exness_demo_mode_requested() -> bool:
    return TRADING_MODE_ENV in {"exness_demo", "demo"} and os.getenv(
        "EXNESS_ENABLE_DEMO_TRADING", ""
    ).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip()
    if system.exness_broker:
        resolved = system.exness_broker.resolve_symbol(cleaned)
        if resolved != cleaned or any(
            configured.casefold() == cleaned.casefold()
            for configured in system.exness_broker.config.symbols
        ):
            return resolved
    return cleaned.upper()


def require_control_access(x_control_token: Optional[str] = Header(default=None)) -> None:
    """
    Keep dangerous control endpoints local/dev by default.

    In production-like environments, set CONTROL_TOKEN and send it as
    X-Control-Token. Development stays frictionless for the dashboard.
    """
    if CONTROL_TOKEN and hmac.compare_digest(x_control_token or "", CONTROL_TOKEN):
        return
    raise HTTPException(403, "Control endpoint access denied")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the entire trading system on startup."""
    raise RuntimeError("Legacy trading lifecycle retired by the controlled rebuild")
    logger.info("Initializing trading system...")
    
    # Initialize all agents
    system.orchestrator = MasterOrchestrator(
        min_final_confidence=ORCHESTRATOR_MIN_FINAL_CONFIDENCE,
        min_strategy_confidence=ORCHESTRATOR_MIN_STRATEGY_CONFIDENCE,
        min_confirmation_confidence=ORCHESTRATOR_MIN_CONFIRMATION_CONFIDENCE,
        cooldown_seconds=ORCHESTRATOR_COOLDOWN_SECONDS,
    )
    system.strategy_agent = StrategyAgent()
    system.risk_agent = RiskManagementAgent(initial_capital=100_000.0)
    system.execution_agent = ExecutionAgent(mode=_execution_mode_from_env())
    system.sentiment_agent = SentimentAgent()
    system.broker_confirmation_agent = None
    system.portfolio_manager = PortfolioManagerAgent(initial_capital=100_000.0)
    system.regime_agent = RegimeDetectionAgent()
    system.data_pipeline = MarketDataPipeline()
    system.compliance_agent = ComplianceAgent()
    system.backtest_agent = BacktestingAgent()
    system.learning_agent = LearningAgent(orchestrator=system.orchestrator)
    system.setup_learning_agent = SetupLearningAgent(store=SetupLearningStore())
    system.trader_learning_agent = TraderLearningAgent(store=TraderLearningStore())
    system.exness_broker = ExnessMT5DemoBroker()
    system.trade_journal = TradeJournal()
    system.image_signal_service = ImageSignalService(symbol_resolver=_normalize_symbol)
    system.trader_imitation_model = TraderImitationModelService(store=system.trader_learning_agent.store)
    if _exness_demo_mode_requested():
        confirmation_symbols = list(system.exness_broker.config.symbols)
        system.broker_confirmation_agent = BrokerMomentumConfirmationAgent(
            symbols=confirmation_symbols
        )
    if system.execution_agent.mode == TradingMode.LIVE:
        system.execution_agent.set_live_broker(system.exness_broker)

    # Initialize database
    await init_db()

    # Load persisted agent weights (survive restarts)
    saved_weights = await load_agent_weights()
    if saved_weights:
        for agent_id, weight in saved_weights.items():
            system.orchestrator.update_agent_weight(agent_id, weight)
        logger.info(f"Restored agent weights: {saved_weights}")

    # Start all agents
    agents = [
        system.orchestrator,
        system.strategy_agent,
        system.risk_agent,
        system.execution_agent,
        system.sentiment_agent,
        system.broker_confirmation_agent,
        system.portfolio_manager,
        system.regime_agent,
        system.compliance_agent,
        system.backtest_agent,
        system.learning_agent,
        system.setup_learning_agent,
        system.trader_learning_agent,
    ]
    agents = [agent for agent in agents if agent is not None]
    
    for agent in agents:
        await agent.start()

    if _exness_demo_mode_requested():
        _configure_exness_agent_inputs()
        _sync_exness_demo_capital()

    # Start event bus and the correct data source for the selected trading mode.
    bus = get_event_bus()
    asyncio.create_task(bus.start())
    if not _exness_demo_mode_requested():
        asyncio.create_task(system.data_pipeline.start())
    
    # Hook database persistence to event bus
    bus = get_event_bus()

    async def _persist_event(event):
        if event.event_type in {
            EventType.AGENT_STATUS,
            EventType.MARKET_DATA_UPDATE,
            EventType.SYSTEM_HEARTBEAT,
        }:
            return
        await save_event(
            event.event_type.value,
            event.source_agent,
            {
                **event.payload,
                "event_id": event.event_id,
                "priority": event.priority,
                "correlation_id": event.correlation_id,
            },
        )

    async def _persist_closed_trade(event):
        try:
            trade = event.payload.get("trade", {})
            if trade:
                await save_trade(trade)
                await save_equity_snapshot(
                    system.risk_agent.portfolio_state.get("total_capital", 100000),
                    daily_pnl=system.risk_agent.portfolio_state.get("daily_pnl", 0)
                )
                # Persist updated agent weights after each trade
                if system.orchestrator:
                    await save_agent_weights(system.orchestrator.agent_weights)
        except Exception as e:
            logger.error(f"DB persistence error: {e}")

    bus.subscribe_all(_persist_event)
    bus.subscribe(EventType.POSITION_CLOSED, _persist_closed_trade)

    system.initialized = True
    if _exness_demo_mode_requested():
        asyncio.create_task(_stream_exness_market_data())
        asyncio.create_task(_reconcile_exness_broker_state())
    logger.info("✅ Trading system fully initialized — all agents running")

    yield  # Application runs here

    # Shutdown
    logger.info("Shutting down trading system...")
    await system.data_pipeline.stop()
    for agent in agents:
        await agent.stop()
    await bus.stop()
    logger.info("Trading system shutdown complete")


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Multi-Agent Trading Simulator",
    description="Multi-agent paper-trading simulation. Not production ready.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(chat_import_router(require_control_access))

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── WebSocket connection manager ────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self._connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"WS client connected | total: {len(self._connections)}")

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)
        logger.info(f"WS client disconnected | remaining: {len(self._connections)}")

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


ws_manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time event stream.
    Clients receive all events from the event bus in real-time.
    """
    await ws_manager.connect(websocket)
    bus = get_event_bus()
    
    try:
        # Initial state snapshot
        if system.initialized:
            await websocket.send_json({
                "type": "snapshot",
                "data": await _get_full_snapshot(),
                "timestamp": time.time(),
            })

        # Stream events from broadcast queue
        while True:
            try:
                event_data = await asyncio.wait_for(
                    bus._broadcast_queue.get(), timeout=1.0
                )
                await websocket.send_json({
                    "type": "event",
                    "data": event_data,
                    "timestamp": time.time(),
                })
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                await websocket.send_json({"type": "heartbeat", "timestamp": time.time()})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# ─── REST API endpoints ───────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy" if system.initialized else "initializing",
        "timestamp": time.time(),
        "ws_connections": ws_manager.connection_count,
        "pipeline_stats": system.data_pipeline.stats if system.data_pipeline else {},
        "bus_stats": get_event_bus().stats,
    }


@app.get("/api/portfolio")
async def get_portfolio():
    if not system.portfolio_manager:
        raise HTTPException(503, "System not initialized")
    return {
        "portfolio": system.portfolio_manager.portfolio_summary,
        "metrics": system.portfolio_manager.performance_metrics,
        "risk_state": system.risk_agent.portfolio_state if system.risk_agent else {},
    }


@app.get("/api/agents")
async def get_agents():
    agents = []
    for agent in _get_all_agents():
        agents.append(agent.health_check())
    return {"agents": agents, "count": len(agents)}


@app.get("/api/signals")
async def get_signals():
    bus = get_event_bus()
    return {
        "strategy_signals": bus.get_history(EventType.STRATEGY_SIGNAL, limit=20),
        "sentiment_signals": bus.get_history(EventType.SENTIMENT_SIGNAL, limit=10),
        "risk_assessments": bus.get_history(EventType.RISK_ASSESSMENT, limit=10),
    }


@app.get("/api/orders")
async def get_orders():
    if not system.execution_agent:
        raise HTTPException(503, "System not initialized")
    return {
        "open_orders": system.execution_agent.open_orders,
        "order_history": await _durable_order_history(system.execution_agent.order_history),
        "mode": "exness_demo" if _exness_demo_mode_requested() else system.execution_agent.trading_mode,
    }


@app.get("/api/risk")
async def get_risk():
    if not system.risk_agent:
        raise HTTPException(503, "System not initialized")
    return {
        "portfolio": system.risk_agent.portfolio_state,
        "parameters": system.risk_agent.risk_parameters,
        "agent_weights": system.orchestrator.agent_weights if system.orchestrator else {},
        "kill_switch_active": system.orchestrator.kill_switch_active if system.orchestrator else False,
        "regime": system.regime_agent.current_regime if system.regime_agent else "UNKNOWN",
    }


@app.get("/api/sentiment")
async def get_sentiment():
    if not system.sentiment_agent:
        raise HTTPException(503, "System not initialized")
    return {
        "current_sentiment": system.sentiment_agent.current_sentiment,
        "recent_news": system.sentiment_agent.recent_news,
    }


@app.get("/api/decisions")
async def get_decisions():
    if not system.orchestrator:
        raise HTTPException(503, "System not initialized")
    return {
        "recent_decisions": system.orchestrator.recent_decisions,
        "agent_weights": system.orchestrator.agent_weights,
    }


@app.get("/api/broker/exness", dependencies=[Depends(require_control_access)])
async def get_exness_status():
    if not system.exness_broker:
        raise HTTPException(503, "Exness broker adapter not initialized")
    return system.exness_broker.status()


@app.post("/api/broker/exness/connect", dependencies=[Depends(require_control_access)])
async def connect_exness():
    if not system.exness_broker:
        raise HTTPException(503, "Exness broker adapter not initialized")
    return system.exness_broker.connect()


@app.post("/api/broker/exness/disconnect", dependencies=[Depends(require_control_access)])
async def disconnect_exness():
    if not system.exness_broker:
        raise HTTPException(503, "Exness broker adapter not initialized")
    return system.exness_broker.shutdown()


@app.get("/api/broker/exness/account", dependencies=[Depends(require_control_access)])
async def get_exness_account():
    if not system.exness_broker:
        raise HTTPException(503, "Exness broker adapter not initialized")
    return system.exness_broker.account_info()


@app.get("/api/broker/exness/positions", dependencies=[Depends(require_control_access)])
async def get_exness_positions():
    if not system.exness_broker:
        raise HTTPException(503, "Exness broker adapter not initialized")
    return system.exness_broker.positions()


@app.get("/api/broker/exness/quote/{symbol}", dependencies=[Depends(require_control_access)])
async def get_exness_quote(symbol: str):
    if not system.exness_broker:
        raise HTTPException(503, "Exness broker adapter not initialized")
    return system.exness_broker.quote(symbol)


# ─── Control endpoints ────────────────────────────────────────────────────────

class AgentControlRequest(BaseModel):
    agent_id: str
    action: str  # pause | resume | restart


class RiskUpdateRequest(BaseModel):
    max_portfolio_risk_pct: Optional[float] = None
    max_daily_loss_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_total_exposure_pct: Optional[float] = None


class SymbolWatchlistRequest(BaseModel):
    symbol: str
    action: str  # add | remove


class TestSignalRequest(BaseModel):
    symbol: str
    direction: str  # BUY | SELL
    price: float
    confidence: float = 0.9


class PositionLevelsRequest(BaseModel):
    symbol: str
    stop_loss: float
    take_profit: float
    direction: Optional[str] = None
    ticket: Optional[int] = None
    source_signal_id: Optional[str] = None


class TraderLearningImportItem(BaseModel):
    text: str
    message_id: Optional[str] = None
    message_timestamp: Optional[float] = None
    group_id: str = "historical-import"
    sender_id: str = "historical-provider"


class TraderLearningImportRequest(BaseModel):
    signals: List[TraderLearningImportItem]
    source: str = "historical_signal_import"


class ImageSignalSubmitRequest(BaseModel):
    image_id: str


@app.post("/api/controls/agent", dependencies=[Depends(require_control_access)])
async def control_agent(request: AgentControlRequest):
    agent = _find_agent(request.agent_id)
    if not agent:
        raise HTTPException(404, f"Agent {request.agent_id} not found")

    if request.action == "pause":
        agent.pause()
        return {"status": "paused", "agent_id": request.agent_id}
    elif request.action == "resume":
        agent.resume()
        return {"status": "resumed", "agent_id": request.agent_id}
    else:
        raise HTTPException(400, f"Unknown action: {request.action}")


@app.post("/api/broker/exness/positions/levels", dependencies=[Depends(require_control_access)])
async def modify_exness_position_levels(request: PositionLevelsRequest):
    if not system.exness_broker:
        raise HTTPException(503, "Exness broker adapter not initialized")
    result = system.exness_broker.modify_position_levels(
        symbol=request.symbol,
        direction=request.direction,
        ticket=request.ticket,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "position level modification failed"))
    payload = {
        **result,
        "signal_id": request.source_signal_id,
        "source_signal_id": request.source_signal_id,
        "source": "manual_position_level_update",
    }
    await get_event_bus().publish(Event(
        event_type=EventType.POSITION_MODIFIED,
        source_agent="manual_override",
        payload=payload,
        priority=2,
        correlation_id=request.source_signal_id,
    ))
    if system.trade_journal and request.source_signal_id:
        system.trade_journal.record_execution_event(
            request.source_signal_id,
            EventType.POSITION_MODIFIED.value,
            payload,
        )
    return result


@app.post("/api/controls/kill-switch", dependencies=[Depends(require_control_access)])
async def activate_kill_switch(authorized_by: str = "manual"):
    """
    Emergency kill switch — closes all positions and stops trading.
    IRREVERSIBLE until manually reset.
    """
    bus = get_event_bus()
    from core.event_bus import Event
    await bus.publish(Event(
        event_type=EventType.KILL_SWITCH_ACTIVATED,
        source_agent="manual_override",
        payload={"reason": f"Manual kill switch by {authorized_by}", "timestamp": time.time()},
        priority=1,
    ))
    logger.critical(f"MANUAL KILL SWITCH activated by {authorized_by}")
    return {"status": "kill_switch_activated", "authorized_by": authorized_by}


@app.post("/api/controls/reset-kill-switch", dependencies=[Depends(require_control_access)])
async def reset_kill_switch(authorized_by: str = "manual"):
    if system.orchestrator:
        system.orchestrator.deactivate_kill_switch(authorized_by)
    if system.risk_agent:
        system.risk_agent.deactivate_kill_switch()
    return {"status": "kill_switch_reset", "authorized_by": authorized_by}


@app.post("/api/controls/risk", dependencies=[Depends(require_control_access)])
async def update_risk_parameters(request: RiskUpdateRequest):
    if not system.risk_agent:
        raise HTTPException(503, "System not initialized")
    
    params = system.risk_agent.params
    if request.max_portfolio_risk_pct is not None:
        params.max_portfolio_risk_pct = request.max_portfolio_risk_pct
    if request.max_daily_loss_pct is not None:
        params.max_daily_loss_pct = request.max_daily_loss_pct
    if request.max_drawdown_pct is not None:
        params.max_drawdown_pct = request.max_drawdown_pct
    if request.max_total_exposure_pct is not None:
        params.max_total_exposure_pct = request.max_total_exposure_pct

    return {"status": "updated", "parameters": system.risk_agent.risk_parameters}


@app.post("/api/controls/watchlist", dependencies=[Depends(require_control_access)])
async def update_watchlist(request: SymbolWatchlistRequest):
    if not system.strategy_agent:
        raise HTTPException(503, "System not initialized")
    
    symbol = _normalize_symbol(request.symbol)
    if request.action == "add":
        system.strategy_agent.add_to_watchlist(symbol)
        system.sentiment_agent.add_symbol(symbol)
        if system.broker_confirmation_agent:
            system.broker_confirmation_agent.add_symbol(symbol)
        return {"status": "added", "symbol": symbol, "watchlist": system.strategy_agent.watchlist}
    elif request.action == "remove":
        system.strategy_agent.remove_from_watchlist(symbol)
        return {"status": "removed", "symbol": symbol, "watchlist": system.strategy_agent.watchlist}
    else:
        raise HTTPException(400, "action must be 'add' or 'remove'")


@app.post("/api/controls/inject-shock", dependencies=[Depends(require_control_access)])
async def inject_price_shock(symbol: str, shock_pct: float):
    """Stress test: inject a price shock for a symbol."""
    if not system.data_pipeline:
        raise HTTPException(503, "System not initialized")
    system.data_pipeline.inject_price_shock(symbol, shock_pct / 100)
    return {"status": "shock_injected", "symbol": symbol, "shock_pct": shock_pct}


@app.post("/api/controls/inject-test-signals", dependencies=[Depends(require_control_access)])
async def inject_test_signals(request: TestSignalRequest):
    """Stress test: inject agreeing strategy and sentiment signals."""
    symbol = _normalize_symbol(request.symbol)
    direction = request.direction.upper()
    if direction not in {"BUY", "SELL"}:
        raise HTTPException(400, "direction must be BUY or SELL")
    if request.price <= 0:
        raise HTTPException(400, "price must be positive")

    confidence = max(0.0, min(1.0, request.confidence))
    base_payload = {
        "symbol": symbol,
        "direction": direction,
        "confidence": confidence,
        "price": request.price,
        "ttl_seconds": 120.0,
    }

    bus = get_event_bus()
    from core.event_bus import Event
    await bus.publish(Event(
        event_type=EventType.STRATEGY_SIGNAL,
        source_agent="strategy_agent",
        payload={
            **base_payload,
            "reasoning": "Injected paired test strategy signal",
            "strategy_count": 1,
            "indicators": {"price": request.price, "rsi": 50.0},
        },
        priority=2,
    ))
    await bus.publish(Event(
        event_type=EventType.SENTIMENT_SIGNAL,
        source_agent="sentiment_agent",
        payload={
            **base_payload,
            "reasoning": "Injected paired test sentiment signal",
            "sentiment_data": {"symbol": symbol, "direction": direction},
        },
        priority=2,
    ))
    return {
        "status": "test_signals_injected",
        "symbol": symbol,
        "direction": direction,
        "price": request.price,
    }


@app.get("/api/private/journal/signals", dependencies=[Depends(require_control_access)])
async def get_private_trade_signals(limit: int = 50):
    if not system.trade_journal:
        raise HTTPException(503, "Private trade journal not initialized")
    return {
        "signals": system.trade_journal.recent_signals(limit=max(1, min(limit, 250))),
    }


@app.get("/api/private/journal/alerts", dependencies=[Depends(require_control_access)])
async def get_private_trade_alerts(limit: int = 50):
    if not system.trade_journal:
        raise HTTPException(503, "Private trade journal not initialized")
    return {
        "alerts": system.trade_journal.recent_alerts(limit=max(1, min(limit, 250))),
    }


@app.get("/api/private/readiness", dependencies=[Depends(require_control_access)])
async def get_private_live_readiness():
    return _private_readiness_report()


@app.get("/api/private/setup-learning/summary", dependencies=[Depends(require_control_access)])
async def get_private_setup_learning_summary(limit: int = 25):
    if not system.setup_learning_agent:
        raise HTTPException(503, "Provider setup learning agent not initialized")
    return system.setup_learning_agent.learning_summary(recent_limit=max(1, min(limit, 250)))


@app.get("/api/private/trader-learning/summary", dependencies=[Depends(require_control_access)])
async def get_private_trader_learning_summary(limit: int = 25):
    if not system.trader_learning_agent:
        raise HTTPException(503, "Trader learning agent not initialized")
    return system.trader_learning_agent.learning_summary(recent_limit=max(1, min(limit, 250)))


@app.get("/api/private/trader-learning/model", dependencies=[Depends(require_control_access)])
async def get_private_trader_imitation_model_status():
    if not system.trader_imitation_model:
        raise HTTPException(503, "Trader imitation model not initialized")
    return system.trader_imitation_model.status()


@app.post("/api/private/trader-learning/train", dependencies=[Depends(require_control_access)])
async def train_private_trader_imitation_model():
    if not system.trader_imitation_model:
        raise HTTPException(503, "Trader imitation model not initialized")
    return system.trader_imitation_model.train()


@app.post("/api/private/signals/image/parse", dependencies=[Depends(require_control_access)])
async def parse_private_signal_image(file: UploadFile = File(...)):
    if not system.image_signal_service:
        raise HTTPException(503, "Image signal service not initialized")
    try:
        image_bytes = await file.read()
        result = await system.image_signal_service.parse_upload(
            image_bytes=image_bytes,
            filename=file.filename or "signal-image",
            content_type=file.content_type,
            source="ui_execution_upload",
        )
    except DeepSeekVisionError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    _record_image_signal_for_learning(result)
    return result


@app.post("/api/private/signals/image/bulk-learning", dependencies=[Depends(require_control_access)])
async def bulk_parse_private_signal_images_for_learning(files: List[UploadFile] = File(...)):
    if not system.image_signal_service:
        raise HTTPException(503, "Image signal service not initialized")
    if not files:
        raise HTTPException(400, "upload at least one image")

    parsed: list[dict] = []
    rejected: list[dict] = []
    for file in files[:50]:
        try:
            image_bytes = await file.read()
            result = await system.image_signal_service.parse_upload(
                image_bytes=image_bytes,
                filename=file.filename or "signal-image",
                content_type=file.content_type,
                source="bulk_learning_upload",
            )
            _record_image_signal_for_learning(result, source="bulk_learning_upload")
            if result.get("status") == "PARSED":
                parsed.append(result)
            else:
                rejected.append(
                    {
                        "filename": result.get("filename"),
                        "image_id": result.get("image_id"),
                        "reasons": result.get("rejection_reasons") or [],
                    }
                )
        except DeepSeekVisionError as exc:
            rejected.append({"filename": file.filename, "reasons": [str(exc)]})
        except ValueError as exc:
            rejected.append({"filename": file.filename, "reasons": [str(exc)]})

    return {
        "status": "processed",
        "learning_mode": "observation_only",
        "execution_submitted": False,
        "processed": len(parsed) + len(rejected),
        "parsed_count": len(parsed),
        "rejected_count": len(rejected),
        "parsed": parsed,
        "rejected": rejected,
    }


@app.post("/api/private/signals/image/submit", dependencies=[Depends(require_control_access)])
async def submit_private_signal_image(request: ImageSignalSubmitRequest):
    if not system.image_signal_service:
        raise HTTPException(503, "Image signal service not initialized")
    try:
        stored = system.image_signal_service.stored_payload_for_submission(request.image_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    result = await _submit_image_signal_to_risk(
        image_id=request.image_id,
        message_id=stored["message_id"],
        text=stored["text"],
    )
    system.image_signal_service.mark_submitted(request.image_id, result)
    return result


@app.get("/api/private/signals/image/recent", dependencies=[Depends(require_control_access)])
async def get_private_signal_images(limit: int = 25):
    if not system.image_signal_service:
        raise HTTPException(503, "Image signal service not initialized")
    return {
        "images": system.image_signal_service.recent(limit=max(1, min(limit, 250))),
    }


@app.get("/api/private/trade-audit", dependencies=[Depends(require_control_access)])
async def get_private_trade_audit(limit: int = 25):
    if not system.image_signal_service or not system.trader_learning_agent:
        raise HTTPException(503, "Private audit services not initialized")
    rows = system.image_signal_service.store.recent(limit=max(1, min(limit, 250)))
    signal_ids = [f"image-{row.get('image_id')}" for row in rows if row.get("image_id")]
    learning_rows = {
        row.get("signal_id"): row
        for row in system.trader_learning_agent.store.training_examples(limit=1000)
        if row.get("signal_id") in set(signal_ids)
    }
    learning_events = system.trader_learning_agent.store.execution_events_by_signal_ids(signal_ids)
    durable_events = await get_event_history(limit=1000)
    durable_by_signal: dict[str, list[dict]] = {signal_id: [] for signal_id in signal_ids}
    for event in durable_events:
        payload = event.get("payload") or {}
        event_signal_id = (
            payload.get("signal_id")
            or payload.get("source_signal_id")
            or (payload.get("original_request") or {}).get("signal_id")
        )
        if event_signal_id in durable_by_signal:
            durable_by_signal[event_signal_id].append(event)

    audits = []
    for row in rows:
        image_id = row.get("image_id")
        signal_id = f"image-{image_id}"
        parsed_signal = row.get("parsed_signal_json") or {}
        learning_row = learning_rows.get(signal_id) or {}
        submit_result = row.get("submit_result_json") or {}
        audits.append(
            {
                "signal_id": signal_id,
                "image_id": image_id,
                "source": row.get("source"),
                "image_status": row.get("status"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "extraction": {
                    "has_raw_text": bool(row.get("raw_extracted_text")),
                    "normalized_text": row.get("normalized_text"),
                    "vision_confidence": (row.get("extracted_json") or {}).get("confidence"),
                },
                "parser": {
                    "status": parsed_signal.get("validation_status") or row.get("status"),
                    "instrument": parsed_signal.get("instrument"),
                    "direction": parsed_signal.get("direction"),
                    "entry_type": parsed_signal.get("entry_type"),
                    "stop_loss": parsed_signal.get("stop_loss"),
                    "take_profit": parsed_signal.get("take_profit_1"),
                    "parser_confidence": parsed_signal.get("parser_confidence"),
                    "rejection_reasons": row.get("rejection_reasons_json") or [],
                },
                "risk_submission": submit_result,
                "learning": {
                    "validation_status": learning_row.get("validation_status"),
                    "execution_status": learning_row.get("execution_status"),
                    "outcome_status": learning_row.get("outcome_status"),
                    "pnl": learning_row.get("pnl"),
                },
                "execution_events": learning_events.get(signal_id, []),
                "broker_events": durable_by_signal.get(signal_id, []),
            }
        )
    return {
        "mode": "private_local_audit",
        "count": len(audits),
        "audits": audits,
        "timestamp": time.time(),
    }


@app.post("/api/private/trader-learning/import", dependencies=[Depends(require_control_access)])
async def import_private_trader_learning_examples(request: TraderLearningImportRequest):
    if not system.trader_learning_agent:
        raise HTTPException(503, "Trader learning agent not initialized")
    parser = SignalParser()
    imported = 0
    rejected = []
    now = time.time()
    for index, item in enumerate(request.signals):
        message_id = item.message_id or f"historical-{int(now)}-{index}"
        signal = parser.parse(
            message_id=message_id,
            group_id=item.group_id,
            sender_id=item.sender_id,
            text=item.text,
            message_timestamp=item.message_timestamp or now,
            received_timestamp=now,
        )
        if signal.instrument:
            signal.instrument = _normalize_symbol(signal.instrument)
        reasons = []
        if not signal.instrument:
            reasons.append("missing instrument")
        if signal.direction not in {"BUY", "SELL"}:
            reasons.append("missing BUY/SELL direction")
        if signal.stop_loss is None:
            reasons.append("missing stop loss")
        if signal.primary_take_profit is None:
            reasons.append("missing take profit")
        status = "IMPORTED" if not reasons else "REJECTED"
        signal.validation_status = status
        signal.rejection_reasons = reasons
        system.trader_learning_agent.record_private_signal(
            signal,
            source=request.source,
            validation_status=status,
            rejection_reasons=reasons,
        )
        if reasons:
            rejected.append({"message_id": message_id, "reasons": reasons})
        else:
            imported += 1
    return {
        "status": "imported",
        "imported": imported,
        "rejected": rejected,
        "learning_mode": "observation_only",
    }


@app.get("/api/history")
async def get_trade_history_endpoint(limit: int = 50, symbol: str = None):
    trades = await get_trade_history(limit=limit, symbol=symbol)
    return {"trades": trades, "count": len(trades)}


@app.get("/api/stats")
async def get_performance_stats_endpoint():
    stats = await get_performance_stats()
    return {"performance": stats, "sentiment_nlp": system.sentiment_agent.nlp_status if system.sentiment_agent else {}}


@app.get("/api/events")
async def get_audit_events(event_type: Optional[str] = None, limit: int = 100):
    return {
        "events": await get_event_history(event_type=event_type, limit=limit),
        "limit": max(1, min(int(limit), 1000)),
    }


@app.post("/api/backtest")
async def run_backtest(strategy: str = "trend_following", symbol: str = "AAPL", days: int = 252):
    if not system.backtest_agent:
        raise HTTPException(503, "Backtest agent not initialized")
    result = await system.backtest_agent.run_backtest(strategy, symbol, days)
    if result:
        return result.to_dict()
    raise HTTPException(500, "Backtest failed")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_all_agents():
    return [
        a for a in [
            system.orchestrator,
            system.strategy_agent,
            system.risk_agent,
            system.execution_agent,
            system.sentiment_agent,
            system.broker_confirmation_agent,
            system.portfolio_manager,
            system.regime_agent,
            system.compliance_agent,
            system.backtest_agent,
            system.learning_agent,
            system.setup_learning_agent,
            system.trader_learning_agent,
        ] if a is not None
    ]


def _find_agent(agent_id: str):
    for agent in _get_all_agents():
        if agent.agent_id == agent_id:
            return agent
    return None


async def _submit_image_signal_to_risk(*, image_id: str, message_id: str, text: str) -> dict:
    signal = SignalParser().parse(
        message_id=message_id,
        group_id="ui-image-upload",
        sender_id="dashboard-user",
        text=text,
        message_timestamp=time.time(),
        received_timestamp=time.time(),
    )
    signal.signal_id = f"image-{image_id}"
    if signal.instrument:
        signal.instrument = _normalize_symbol(signal.instrument)

    reasons = _validate_image_signal_for_submission(signal)
    if reasons:
        signal.validation_status = "REJECTED"
        signal.rejection_reasons = reasons
        if system.trade_journal:
            system.trade_journal.record_signal(signal, source="image_execution_upload")
        if system.trader_learning_agent:
            system.trader_learning_agent.record_private_signal(
                signal,
                source="image_execution_upload",
                validation_status="REJECTED",
                rejection_reasons=reasons,
            )
        await _publish_image_signal_event(EventType.TRADE_SIGNAL_REJECTED, signal, reasons)
        return {
            "status": "rejected",
            "accepted": False,
            "signal": signal.to_dict(include_raw=False),
            "reasons": reasons,
        }

    signal.validation_status = "ACCEPTED"
    if system.trade_journal:
        system.trade_journal.record_signal(signal, source="image_execution_upload")
    if system.trader_learning_agent:
        system.trader_learning_agent.record_private_signal(
            signal,
            source="image_execution_upload",
            validation_status="ACCEPTED",
            rejection_reasons=[],
        )
    await _publish_image_signal_event(EventType.TRADE_SIGNAL_ACCEPTED, signal, [])

    quote = _current_broker_quote(signal.instrument or "")
    price = float(quote.get("price") or 0)
    payload = {
        "symbol": signal.instrument,
        "action": "EXECUTE_BUY" if signal.direction == "BUY" else "EXECUTE_SELL",
        "direction": signal.direction,
        "confidence": signal.parser_confidence,
        "price": price,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.primary_take_profit,
        "requested_risk_pct": signal.requested_risk_pct,
        "spread_bps": quote.get("spread_bps"),
        "source": "image_execution_upload",
        "signal_id": signal.signal_id,
        "parser_version": signal.parser_version,
        "reasoning": [
            "Private uploaded image signal accepted after vision extraction and deterministic validation",
            "Risk agent must size, validate, and veto before execution",
        ],
    }

    adoption = await _adopt_existing_position_for_signal(signal, payload)
    if adoption:
        status = "adopted_existing_position" if adoption.get("ok") else "adoption_blocked"
        return {
            "status": status,
            "accepted": True,
            "signal": signal.to_dict(include_raw=False),
            "adoption": adoption,
        }

    await get_event_bus().publish(Event(
        event_type=EventType.ORDER_REQUESTED,
        source_agent="image_signal_upload",
        payload=payload,
        priority=2,
        correlation_id=signal.signal_id,
    ))
    if system.trade_journal:
        system.trade_journal.record_execution_event(signal.signal_id, "order.requested", payload)
    return {
        "status": "submitted_to_risk",
        "accepted": True,
        "signal": signal.to_dict(include_raw=False),
    }


def _validate_image_signal_for_submission(signal) -> list[str]:
    reasons: list[str] = []
    if not signal.instrument:
        reasons.append("missing instrument")
    if signal.direction not in {"BUY", "SELL"}:
        reasons.append("direction must be BUY or SELL")
    if signal.entry_type != "MARKET":
        reasons.append("only MARKET/current-rate image signals can be submitted")
    if signal.stop_loss is None:
        reasons.append("missing stop loss")
    if signal.primary_take_profit is None:
        reasons.append("missing take profit")
    if signal.instrument:
        allowed = {symbol.casefold() for symbol in _private_signal_allowed_symbols()}
        if allowed and signal.instrument.casefold() not in allowed:
            reasons.append(f"{signal.instrument} is not enabled for image signal trading")
        quote = _current_broker_quote(signal.instrument)
        price = float(quote.get("price") or 0)
        if price <= 0:
            reasons.append("missing current broker price")
        elif signal.stop_loss is not None and signal.primary_take_profit is not None:
            level_reason = _validate_private_signal_levels(signal.direction, price, signal.stop_loss, signal.primary_take_profit)
            if level_reason:
                reasons.append(level_reason)
    return reasons


def _validate_private_signal_levels(direction: str, price: float, stop_loss: float, take_profit: float) -> Optional[str]:
    if direction == "BUY" and not (stop_loss < price < take_profit):
        return "BUY requires stop_loss < current_price < take_profit"
    if direction == "SELL" and not (take_profit < price < stop_loss):
        return "SELL requires take_profit < current_price < stop_loss"
    risk = abs(price - stop_loss)
    reward = abs(take_profit - price)
    rr = reward / max(risk, 1e-12)
    if rr + 1e-9 < IMAGE_SIGNAL_MIN_RISK_REWARD_RATIO:
        return f"risk/reward {rr:.2f} < {IMAGE_SIGNAL_MIN_RISK_REWARD_RATIO:.2f}"
    return None


async def _publish_image_signal_event(event_type: EventType, signal, reasons: list[str]) -> None:
    await get_event_bus().publish(Event(
        event_type=event_type,
        source_agent="image_signal_upload",
        payload={
            "signal_id": signal.signal_id,
            "message_id": signal.message_id,
            "instrument": signal.instrument,
            "direction": signal.direction,
            "entry_type": signal.entry_type,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.primary_take_profit,
            "requested_risk_pct": signal.requested_risk_pct,
            "validation_status": signal.validation_status,
            "rejection_reasons": reasons,
            "parser_confidence": signal.parser_confidence,
            "parser_version": signal.parser_version,
            "signal_age": signal.signal_age,
            "message_timestamp": signal.message_timestamp,
            "source": "image_execution_upload",
        },
        priority=3,
        correlation_id=signal.signal_id,
    ))


async def _adopt_existing_position_for_signal(signal, order_payload: Dict[str, Any]) -> Optional[dict]:
    positions = (_current_broker_positions().get("positions") or [])
    matching = [
        position
        for position in positions
        if str(position.get("symbol") or "").casefold() == str(signal.instrument or "").casefold()
        and str(position.get("direction") or "").upper() == str(signal.direction or "").upper()
    ]
    if not matching:
        return None
    if len(matching) > 1:
        result = {
            "ok": False,
            "reason": "multiple matching open positions; provide a ticket before adopting image signal levels",
            "matching_positions": len(matching),
            "signal_id": signal.signal_id,
            "symbol": signal.instrument,
            "direction": signal.direction,
        }
        if system.trade_journal:
            system.trade_journal.record_execution_event(signal.signal_id, "position.adoption_blocked", result)
        return result

    result = _modify_broker_position_levels(
        symbol=signal.instrument,
        direction=signal.direction,
        ticket=matching[0].get("ticket"),
        stop_loss=float(signal.stop_loss or 0),
        take_profit=float(signal.primary_take_profit or 0),
    )
    result.update({
        "signal_id": signal.signal_id,
        "source_signal_id": signal.signal_id,
        "source": "image_execution_upload",
    })
    if system.trade_journal:
        system.trade_journal.record_execution_event(
            signal.signal_id,
            "position.adopted_existing" if result.get("ok") else "position.adoption_failed",
            result,
        )
    if result.get("ok"):
        await get_event_bus().publish(Event(
            event_type=EventType.POSITION_MODIFIED,
            source_agent="image_signal_upload",
            payload={**order_payload, "adoption": result},
            priority=2,
            correlation_id=signal.signal_id,
        ))
    return result


async def _durable_order_history(memory_history: List[dict], limit: int = 100) -> List[dict]:
    event_types = {
        EventType.ORDER_REQUESTED.value,
        EventType.ORDER_SUBMITTED.value,
        EventType.ORDER_FILLED.value,
        EventType.ORDER_CANCELLED.value,
        EventType.ORDER_REJECTED.value,
        EventType.POSITION_MODIFIED.value,
    }
    durable = await get_event_history(limit=500)
    merged: list[dict] = []
    seen: set[str] = set()

    def add_order(item: dict, source: str) -> None:
        payload = item.get("payload") if "payload" in item else item
        if not isinstance(payload, dict):
            return
        key = str(
            payload.get("event_id")
            or payload.get("order_id")
            or payload.get("broker_order_id")
            or payload.get("signal_id")
            or f"{source}:{len(merged)}"
        )
        if key in seen:
            return
        seen.add(key)
        merged.append({
            **payload,
            "timestamp": payload.get("timestamp") or item.get("timestamp"),
            "history_source": source,
            "event_type": item.get("event_type"),
        })

    for event in durable:
        if event.get("event_type") in event_types:
            add_order(event, "persisted_event")
    for order in reversed(memory_history or []):
        add_order(order, "memory")

    merged.sort(key=lambda item: float(item.get("timestamp") or item.get("filled_at") or item.get("created_at") or 0), reverse=True)
    return merged[: max(1, min(int(limit), 250))]


def _private_signal_allowed_symbols() -> tuple[str, ...]:
    if not system.exness_broker:
        return ()
    return system.exness_broker.config.trade_symbols or system.exness_broker.config.symbols


def _record_image_signal_for_learning(result: dict, *, source: str = "ui_execution_upload") -> None:
    if not system.trader_learning_agent:
        return
    signal = result.get("signal") or {}
    symbol = signal.get("instrument")
    system.trader_learning_agent.store.record_signal(
        signal_id=f"image-{result.get('image_id')}",
        source=source,
        message_id=f"image-{result.get('image_hash')}",
        raw_message=result.get("raw_text"),
        parsed_signal=signal,
        market_snapshot=system.trader_learning_agent.latest_market_snapshot(str(symbol or "")),
        validation_status=result.get("status") or "PARSED",
        rejection_reasons=result.get("rejection_reasons") or [],
    )


def _current_broker_positions() -> dict:
    if not system.exness_broker:
        return {"positions": []}
    return system.exness_broker.positions()


def _modify_broker_position_levels(**kwargs) -> dict:
    if not system.exness_broker:
        return {"ok": False, "reason": "Exness broker adapter not initialized"}
    return system.exness_broker.modify_position_levels(**kwargs)


def _current_broker_quote(symbol: str) -> dict:
    if not system.exness_broker:
        return {"price": None, "spread_bps": None}
    result = system.exness_broker.market_data_payload(symbol)
    payload = result.get("payload") or {}
    return {
        "price": payload.get("price"),
        "spread_bps": payload.get("spread_bps"),
    }


def _private_readiness_report() -> dict:
    broker_status = system.exness_broker.status() if system.exness_broker else {}
    image_service = system.image_signal_service
    deepseek_configured = bool(image_service and image_service.vision_client.configured)
    private_status = {
        "image_signal_service_initialized": bool(image_service),
        "deepseek_api_key_configured": deepseek_configured,
        "min_risk_reward_ratio": IMAGE_SIGNAL_MIN_RISK_REWARD_RATIO,
    }
    checks = [
        {
            "name": "private_services_initialized",
            "status": "PASS" if system.trade_journal and image_service else "BLOCKED",
            "detail": "private journal and screenshot upload service are loaded",
        },
        {
            "name": "deepseek_vision_configured",
            "status": "PASS" if deepseek_configured else "BLOCKED",
            "detail": "set DEEPSEEK_API_KEY before parsing uploaded signal screenshots",
        },
        {
            "name": "broker_connected",
            "status": "PASS" if broker_status.get("connected") else "BLOCKED",
            "detail": broker_status.get("last_error") or "Exness MT5 connection status",
        },
        {
            "name": "demo_order_execution_enabled",
            "status": "PASS" if broker_status.get("trade_execution_enabled") else "BLOCKED",
            "detail": "requires TRADING_MODE=exness_demo and EXNESS_ENABLE_DEMO_TRADING=true",
        },
        {
            "name": "control_endpoint_security",
            "status": "PASS" if APP_ENV not in CONTROL_TOKEN_REQUIRED_ENVS or CONTROL_TOKEN else "FAIL",
            "detail": "production-like APP_ENV requires CONTROL_TOKEN",
        },
    ]
    live_trading_allowed = all(
        check["status"] == "PASS"
        for check in checks
        if check["name"] in {
            "private_services_initialized",
            "deepseek_vision_configured",
            "broker_connected",
            "demo_order_execution_enabled",
        }
    )
    return {
        "status": "GREEN" if live_trading_allowed else "RED",
        "live_trading_allowed": live_trading_allowed,
        "private_signal_config": private_status,
        "broker": broker_status,
        "checks": checks,
        "timestamp": time.time(),
    }


async def _get_full_snapshot() -> dict:
    """Full system state for initial WebSocket connection."""
    return {
        "portfolio": system.portfolio_manager.portfolio_summary if system.portfolio_manager else {},
        "agents": [a.health_check() for a in _get_all_agents()],
        "risk": {
            "portfolio": system.risk_agent.portfolio_state,
            "parameters": system.risk_agent.risk_parameters,
            "kill_switch_active": (
                system.orchestrator.kill_switch_active if system.orchestrator else False
            ),
        } if system.risk_agent else {},
        "regime": system.regime_agent.current_regime if system.regime_agent else "UNKNOWN",
        "sentiment": system.sentiment_agent.current_sentiment if system.sentiment_agent else {},
        "broker": {
            "exness": system.exness_broker.status() if system.exness_broker else {}
        },
        "recent_decisions": system.orchestrator.recent_decisions[:10] if system.orchestrator else [],
        "pipeline_stats": system.data_pipeline.stats if system.data_pipeline else {},
    }


def _configure_exness_agent_inputs() -> None:
    if not system.exness_broker:
        return
    for symbol in system.exness_broker.config.symbols:
        if system.strategy_agent:
            system.strategy_agent.add_to_watchlist(symbol)
        if system.sentiment_agent:
            system.sentiment_agent.add_symbol(symbol)
        if system.broker_confirmation_agent:
            system.broker_confirmation_agent.add_symbol(symbol)


def _sync_exness_demo_capital() -> None:
    if not system.exness_broker:
        return
    account_result = system.exness_broker.account_info()
    account = account_result.get("account") or {}
    equity = float(account.get("equity") or account.get("balance") or 0)
    if equity <= 0:
        logger.warning("Exness demo capital sync skipped: no positive account equity")
        return
    if system.risk_agent:
        system.risk_agent.update_capital(equity)
    if system.portfolio_manager:
        system.portfolio_manager.update_capital(equity)
    logger.info(f"Exness demo capital synced from broker equity: ${equity:,.2f}")


async def _stream_exness_market_data() -> None:
    if not system.exness_broker:
        return
    bus = get_event_bus()
    while system.initialized:
        for symbol in system.exness_broker.config.symbols:
            result = system.exness_broker.market_data_payload(symbol)
            payload = result.get("payload")
            if payload:
                from core.event_bus import Event
                await bus.publish(Event(
                    event_type=EventType.MARKET_DATA_UPDATE,
                    source_agent="exness_mt5",
                    payload=payload,
                    priority=4,
                ))
        await asyncio.sleep(max(0.5, EXNESS_MARKET_DATA_INTERVAL))


async def _reconcile_exness_broker_state() -> None:
    if not system.exness_broker:
        return
    while system.initialized:
        try:
            account_result = system.exness_broker.account_info()
            account = account_result.get("account") or {}
            equity = float(account.get("equity") or account.get("balance") or 0)
            position_result = system.exness_broker.positions()
            positions = position_result.get("positions") or []
            if equity > 0:
                if system.portfolio_manager:
                    system.portfolio_manager.reconcile_broker_positions(positions, equity)
                if system.risk_agent:
                    system.risk_agent.reconcile_broker_positions(positions, equity)
                if system.execution_agent:
                    system.execution_agent.reconcile_open_symbols(
                        {p.get("symbol") for p in positions if p.get("symbol")}
                    )
        except Exception:
            logger.error("Exness broker reconciliation failed", exc_info=True)
        await asyncio.sleep(max(1.0, EXNESS_RECONCILE_INTERVAL))


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    )
    raise RuntimeError("Start main:app; the legacy application is archived and disabled")
