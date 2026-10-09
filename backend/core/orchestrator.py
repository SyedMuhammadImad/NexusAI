"""
Master Orchestrator — The hedge fund desk chief.

Receives signals from all agents, resolves conflicts, and makes
the final call on every trade. This is where weighted scoring,
voting, and RL live.

Design: Signals don't expire immediately — they have a TTL.
If a signal expires before a decision is made, it's discarded.
This prevents stale data from driving trades.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from core.base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    EXIT = "EXIT"
    REDUCE = "REDUCE"


class TradeAction(str, Enum):
    EXECUTE_BUY = "EXECUTE_BUY"
    EXECUTE_SELL = "EXECUTE_SELL"
    EXECUTE_EXIT = "EXECUTE_EXIT"
    REDUCE_POSITION = "REDUCE_POSITION"
    HOLD = "HOLD"
    BLOCKED_RISK = "BLOCKED_RISK"
    BLOCKED_COMPLIANCE = "BLOCKED_COMPLIANCE"


@dataclass
class AgentSignal:
    """A single agent's vote on what to do."""
    agent_id: str
    symbol: str
    direction: SignalDirection
    confidence: float  # 0.0 - 1.0
    reasoning: str
    price: float = 0.0
    indicators: Dict[str, float] = field(default_factory=dict)
    spread_bps: Optional[float] = None
    event_type: str = ""
    timestamp: float = field(default_factory=time.time)
    ttl_seconds: float = 60.0  # Signal validity window

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl_seconds

    def weighted_score(self, agent_weight: float) -> float:
        """Score = confidence × weight, negative if bearish."""
        multiplier = 1.0 if self.direction == SignalDirection.BUY else -1.0
        if self.direction == SignalDirection.HOLD:
            multiplier = 0.0
        return self.confidence * agent_weight * multiplier

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 4),
            "reasoning": self.reasoning,
            "price": self.price,
            "indicators": self.indicators,
            "spread_bps": self.spread_bps,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "ttl_seconds": self.ttl_seconds,
        }


@dataclass
class OrchestratorDecision:
    """The final trade decision with full audit trail."""
    symbol: str
    action: TradeAction
    composite_score: float
    participating_signals: int
    consensus_pct: float
    final_confidence: float
    reasoning: List[str]
    signal_details: List[dict] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    blocked_by: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "composite_score": round(self.composite_score, 4),
            "participating_signals": self.participating_signals,
            "consensus_pct": round(self.consensus_pct, 2),
            "final_confidence": round(self.final_confidence, 4),
            "reasoning": self.reasoning,
            "signal_details": self.signal_details,
            "timestamp": self.timestamp,
            "blocked_by": self.blocked_by,
        }


# Agent weight table — how much each agent's opinion matters
# These are tunable. In production, the Learning Agent updates these.
DEFAULT_AGENT_WEIGHTS: Dict[str, float] = {
    "strategy_agent": 0.30,
    "sentiment_agent": 0.15,
    "broker_confirmation_agent": 0.15,
    "macro_agent": 0.15,
    "risk_agent": 0.20,       # Risk is special — see veto logic below
    "arbitrage_agent": 0.10,
    "regime_agent": 0.10,
}

# Hard minimums for action
BUY_THRESHOLD = 0.25       # Composite score must exceed this to BUY
SELL_THRESHOLD = -0.25     # Must be below this to SELL
MIN_SIGNALS_REQUIRED = 2   # At least 2 agents must have voted
MIN_CONSENSUS_PCT = 0.55   # At least 55% agreement on direction


class MasterOrchestrator(BaseAgent):
    """
    The final decision maker. Aggregates signals, resolves conflicts,
    and dispatches orders. Cannot be paused — only killed.
    """

    def __init__(
        self,
        agent_weights: Optional[Dict[str, float]] = None,
        min_final_confidence: float = 0.60,
        min_strategy_confidence: float = 0.55,
        min_confirmation_confidence: float = 0.52,
        cooldown_seconds: float = 120.0,
    ):
        super().__init__("master_orchestrator", "Master Orchestrator")
        self._agent_weights = agent_weights or DEFAULT_AGENT_WEIGHTS
        self._min_final_confidence = min_final_confidence
        self._min_strategy_confidence = min_strategy_confidence
        self._min_confirmation_confidence = min_confirmation_confidence
        self._pending_signals: Dict[str, List[AgentSignal]] = {}  # symbol -> signals
        self._decisions: List[OrchestratorDecision] = []
        self._kill_switch_active = False
        self._paused_symbols: set = set()
        self._decision_cooldown: Dict[str, float] = {}  # symbol -> last decision time
        self._cooldown_seconds = cooldown_seconds  # Min seconds between decisions on same symbol

    async def initialize(self) -> None:
        """Subscribe to all signal and risk events."""
        self.bus.subscribe(EventType.STRATEGY_SIGNAL, self.handle_event)
        self.bus.subscribe(EventType.SENTIMENT_SIGNAL, self.handle_event)
        self.bus.subscribe(EventType.ARBITRAGE_SIGNAL, self.handle_event)
        self.bus.subscribe(EventType.MACRO_SIGNAL, self.handle_event)
        self.bus.subscribe(EventType.RISK_ASSESSMENT, self.handle_event)
        self.bus.subscribe(EventType.KILL_SWITCH_ACTIVATED, self.handle_event)
        self.bus.subscribe(EventType.MARKET_REGIME_CHANGE, self.handle_event)
        self.bus.subscribe(EventType.COMPLIANCE_VIOLATION, self.handle_event)
        logger.info("Orchestrator subscribed to all signal channels")

    async def process_event(self, event: Event) -> None:
        if event.event_type == EventType.KILL_SWITCH_ACTIVATED:
            await self._handle_kill_switch(event)
            return

        if event.event_type == EventType.COMPLIANCE_VIOLATION:
            symbol = event.payload.get("symbol")
            if symbol:
                self._paused_symbols.add(symbol)
                logger.warning(f"Symbol {symbol} paused due to compliance violation")
            return

        if self._kill_switch_active:
            logger.warning("Kill switch active — ignoring all signals")
            return

        # Handle risk assessment — these can veto or block
        if event.event_type == EventType.RISK_ASSESSMENT:
            await self._handle_risk_assessment(event)
            return

        # Handle market regime — adjust weights
        if event.event_type == EventType.MARKET_REGIME_CHANGE:
            await self._handle_regime_change(event)
            return

        # All other signals get added to the pending pool
        await self._ingest_signal(event)

    async def _ingest_signal(self, event: Event) -> None:
        payload = event.payload
        symbol = payload.get("symbol")
        if not symbol:
            return

        signal = AgentSignal(
            agent_id=event.source_agent,
            symbol=symbol,
            direction=SignalDirection(payload.get("direction", "HOLD")),
            confidence=float(payload.get("confidence", 0.5)),
            reasoning=payload.get("reasoning", ""),
            price=float(payload.get("price", 0) or 0),
            indicators=payload.get("indicators", {}) or {},
            spread_bps=payload.get("spread_bps"),
            event_type=event.event_type.value,
            ttl_seconds=payload.get("ttl_seconds", 60.0),
        )

        if symbol not in self._pending_signals:
            self._pending_signals[symbol] = []

        # Remove old signals from this agent for this symbol (one vote per agent)
        self._pending_signals[symbol] = [
            s for s in self._pending_signals[symbol]
            if s.agent_id != event.source_agent and not s.is_expired
        ]
        self._pending_signals[symbol].append(signal)

        logger.info(
            f"Signal ingested: {event.source_agent} → {symbol} {signal.direction.value} "
            f"({signal.confidence:.2f})"
        )

        # Evaluate after every new signal
        await self._evaluate_symbol(symbol)

    async def _evaluate_symbol(self, symbol: str) -> None:
        """Core decision logic — the weighted scoring system."""
        if symbol in self._paused_symbols:
            logger.debug(f"Skipping {symbol} — compliance pause")
            return

        # Cooldown check
        last_decision = self._decision_cooldown.get(symbol, 0)
        if (time.time() - last_decision) < self._cooldown_seconds:
            return

        signals = [s for s in self._pending_signals.get(symbol, []) if not s.is_expired]
        if len(signals) < MIN_SIGNALS_REQUIRED:
            return

        # Calculate weighted composite score
        composite_score = 0.0
        total_weight = 0.0
        reasons = []

        for signal in signals:
            weight = self._agent_weights.get(signal.agent_id, 0.05)
            score_contribution = signal.weighted_score(weight)
            composite_score += score_contribution
            total_weight += weight
            reasons.append(
                f"{signal.agent_id}: {signal.direction.value} "
                f"({signal.confidence:.0%}) → {score_contribution:+.3f}"
            )

        if total_weight > 0:
            composite_score /= total_weight  # Normalize

        # Consensus check — how many agents agree on direction?
        direction_votes = {"BUY": 0, "SELL": 0, "HOLD": 0}
        for s in signals:
            direction_votes[s.direction.value] += 1

        dominant_direction = max(direction_votes, key=direction_votes.get)
        consensus_pct = direction_votes[dominant_direction] / len(signals)

        decision = self._make_decision(
            symbol=symbol,
            composite_score=composite_score,
            consensus_pct=consensus_pct,
            signals=signals,
            reasons=reasons,
        )

        self._decisions.append(decision)
        self._decision_cooldown[symbol] = time.time()

        logger.info(
            f"DECISION: {symbol} → {decision.action.value} | "
            f"score={composite_score:+.3f} | consensus={consensus_pct:.0%} | "
            f"signals={len(signals)}"
        )

        await self._dispatch_decision(decision)

    def _make_decision(
        self,
        symbol: str,
        composite_score: float,
        consensus_pct: float,
        signals: List[AgentSignal],
        reasons: List[str],
    ) -> OrchestratorDecision:
        """Map scores to actionable decisions."""
        action = TradeAction.HOLD
        final_confidence = abs(composite_score) * consensus_pct
        target_direction = (
            "BUY" if composite_score >= BUY_THRESHOLD
            else "SELL" if composite_score <= SELL_THRESHOLD
            else "HOLD"
        )
        gate_passed, gate_reasons = self._strict_trade_gate(signals, target_direction)

        confidence_blocked = (
            target_direction in {"BUY", "SELL"}
            and final_confidence < self._min_final_confidence
        )

        if consensus_pct < MIN_CONSENSUS_PCT:
            reasons.append(f"No consensus ({consensus_pct:.0%} < {MIN_CONSENSUS_PCT:.0%}) → HOLD")
        elif confidence_blocked:
            reasons.append(
                f"Confidence gate: {final_confidence:.0%} < "
                f"{self._min_final_confidence:.0%} minimum → HOLD"
            )
        elif target_direction in {"BUY", "SELL"} and not gate_passed:
            reasons.extend(gate_reasons)
        elif composite_score >= BUY_THRESHOLD:
            action = TradeAction.EXECUTE_BUY
        elif composite_score <= SELL_THRESHOLD:
            action = TradeAction.EXECUTE_SELL
        else:
            reasons.append(f"Score {composite_score:+.3f} in neutral zone → HOLD")

        return OrchestratorDecision(
            symbol=symbol,
            action=action,
            composite_score=composite_score,
            participating_signals=len(signals),
            consensus_pct=consensus_pct,
            final_confidence=final_confidence,
            reasoning=reasons,
            signal_details=[signal.to_dict() for signal in signals],
            blocked_by=(
                "confidence_gate" if confidence_blocked
                else "strict_agent_gate" if gate_reasons
                else None
            ),
        )

    def _strict_trade_gate(
        self, signals: List[AgentSignal], target_direction: str
    ) -> Tuple[bool, List[str]]:
        if target_direction not in {"BUY", "SELL"}:
            return True, []

        reasons = []
        strategy = next((s for s in signals if s.agent_id == "strategy_agent"), None)
        if strategy is None:
            reasons.append("Strict gate: missing Strategy Agent signal → HOLD")
        elif strategy.direction.value != target_direction:
            reasons.append(
                f"Strict gate: Strategy Agent is {strategy.direction.value}, not {target_direction} → HOLD"
            )
        elif strategy.confidence < self._min_strategy_confidence:
            reasons.append(
                f"Strict gate: Strategy Agent confidence {strategy.confidence:.0%} "
                f"< {self._min_strategy_confidence:.0%} → HOLD"
            )

        confirmation_agents = {"sentiment_agent", "broker_confirmation_agent", "macro_agent"}
        confirmations = [
            s for s in signals
            if (
                s.agent_id in confirmation_agents
                and s.direction.value == target_direction
                and s.confidence >= self._min_confirmation_confidence
            )
        ]
        if not confirmations:
            reasons.append(
                f"Strict gate: no independent confirmation agrees with {target_direction} "
                f"at >= {self._min_confirmation_confidence:.0%} confidence → HOLD"
            )

        blockers = [
            s.agent_id for s in signals
            if s.agent_id in confirmation_agents
            and s.direction.value not in {target_direction, "HOLD"}
        ]
        if blockers:
            reasons.append(
                f"Strict gate: opposing confirmation from {', '.join(sorted(blockers))} → HOLD"
            )

        return not reasons, reasons

    async def _dispatch_decision(self, decision: OrchestratorDecision) -> None:
        """Turn a decision into an order request."""
        if decision.action == TradeAction.HOLD:
            return  # Nothing to dispatch for HOLD

        order_payload = {
            "symbol": decision.symbol,
            "action": decision.action.value,
            "confidence": decision.final_confidence,
            "composite_score": decision.composite_score,
            "reasoning": decision.reasoning,
            "orchestrator_decision": decision.to_dict(),
            "agent_signals": decision.signal_details,
        }
        active_signals = [
            signal for signal in self._pending_signals.get(decision.symbol, [])
            if not signal.is_expired
        ]
        signal_prices = [signal.price for signal in active_signals if signal.price > 0]
        if signal_prices:
            order_payload["price"] = signal_prices[-1]
        strategy_signals = [
            signal for signal in active_signals
            if signal.agent_id == "strategy_agent" and signal.indicators
        ]
        if strategy_signals:
            order_payload["indicators"] = strategy_signals[-1].indicators
        spread_values = [
            signal.spread_bps for signal in active_signals
            if signal.spread_bps is not None
        ]
        if spread_values:
            order_payload["spread_bps"] = spread_values[-1]

        await self.publish(
            EventType.ORDER_REQUESTED,
            order_payload,
            priority=2,  # High priority — this is a real trade request
        )

    async def _handle_risk_assessment(self, event: Event) -> None:
        """Risk agent can add weight or flag symbols."""
        payload = event.payload
        symbol = payload.get("symbol")
        risk_level = payload.get("risk_level", "NORMAL")

        if risk_level == "CRITICAL" and symbol:
            self._paused_symbols.add(symbol)
            logger.warning(f"Risk agent flagged {symbol} as CRITICAL — paused")
        elif risk_level == "HIGH" and symbol:
            # Reduce risk agent weight for aggressive signals
            logger.info(f"Risk agent flagged {symbol} as HIGH risk")

    async def _handle_kill_switch(self, event: Event) -> None:
        self._kill_switch_active = True
        logger.critical(f"KILL SWITCH ACTIVATED by {event.source_agent}: {event.payload.get('reason')}")
        await self.publish(
            EventType.ORDER_REQUESTED,
            {"action": "CLOSE_ALL_POSITIONS", "reason": event.payload.get("reason"), "emergency": True},
            priority=1,  # Maximum priority
        )

    async def _handle_regime_change(self, event: Event) -> None:
        """Adjust agent weights based on market regime."""
        regime = event.payload.get("regime", "UNKNOWN")
        logger.info(f"Market regime change: {regime}")

        # In bear/high-volatility regimes, risk agent gets more weight
        if regime == "BEAR":
            self._agent_weights["risk_agent"] = 0.35
            self._agent_weights["strategy_agent"] = 0.25
        elif regime == "BULL":
            self._agent_weights["risk_agent"] = 0.15
            self._agent_weights["strategy_agent"] = 0.35
        else:  # SIDEWAYS / UNKNOWN — revert to default
            self._agent_weights = DEFAULT_AGENT_WEIGHTS.copy()

        await self.publish(
            EventType.WEIGHT_UPDATE,
            {"regime": regime, "new_weights": self._agent_weights},
        )

    def update_agent_weight(self, agent_id: str, new_weight: float) -> None:
        """Called by Learning Agent to update weights based on performance."""
        if agent_id in self._agent_weights:
            old_weight = self._agent_weights[agent_id]
            self._agent_weights[agent_id] = max(0.01, min(0.5, new_weight))
            logger.info(f"Weight updated: {agent_id} {old_weight:.3f} → {new_weight:.3f}")

    def deactivate_kill_switch(self, authorized_by: str) -> None:
        """Manual override to reactivate after kill switch."""
        self._kill_switch_active = False
        logger.warning(f"Kill switch deactivated by {authorized_by}")

    @property
    def recent_decisions(self) -> List[dict]:
        return [d.to_dict() for d in self._decisions[-50:]]

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch_active

    @property
    def agent_weights(self) -> Dict[str, float]:
        return self._agent_weights.copy()
