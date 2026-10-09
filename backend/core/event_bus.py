"""
Event Bus — Central nervous system of the trading platform.
All agent communication flows through here. No direct agent-to-agent calls.
This is non-negotiable for scalability and auditability.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    # Market data events
    MARKET_DATA_UPDATE = "market.data.update"
    MARKET_REGIME_CHANGE = "market.regime.change"
    
    # Signal events
    STRATEGY_SIGNAL = "strategy.signal"
    SENTIMENT_SIGNAL = "sentiment.signal"
    ARBITRAGE_SIGNAL = "arbitrage.signal"
    MACRO_SIGNAL = "macro.signal"
    TRADE_SIGNAL_ACCEPTED = "trade_signal.accepted"
    TRADE_SIGNAL_REJECTED = "trade_signal.rejected"
    
    # Risk events
    RISK_ASSESSMENT = "risk.assessment"
    RISK_BREACH = "risk.breach"
    KILL_SWITCH_ACTIVATED = "risk.kill_switch"
    
    # Order lifecycle
    ORDER_REQUESTED = "order.requested"
    ORDER_SUBMITTED = "order.submitted"
    ORDER_FILLED = "order.filled"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REJECTED = "order.rejected"
    
    # Portfolio events
    PORTFOLIO_UPDATE = "portfolio.update"
    POSITION_OPENED = "position.opened"
    POSITION_CLOSED = "position.closed"
    POSITION_MODIFIED = "position.modified"
    
    # Compliance events
    COMPLIANCE_CHECK = "compliance.check"
    COMPLIANCE_VIOLATION = "compliance.violation"
    RECONCILIATION_ERROR = "reconciliation.error"
    
    # System events
    AGENT_STATUS = "system.agent_status"
    SYSTEM_HEARTBEAT = "system.heartbeat"
    BACKTEST_RESULT = "system.backtest_result"
    
    # Learning events
    PERFORMANCE_UPDATE = "learning.performance_update"
    WEIGHT_UPDATE = "learning.weight_update"
    TRADER_LEARNING_SNAPSHOT = "learning.trader_snapshot"
    TRADER_SHADOW_PREDICTION = "learning.trader_shadow_prediction"


@dataclass
class Event:
    """Immutable event record — every trade decision is traceable."""
    event_type: EventType
    source_agent: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    priority: int = 5  # 1=critical, 10=low
    correlation_id: Optional[str] = None  # Links related events

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source_agent": self.source_agent,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "priority": self.priority,
            "correlation_id": self.correlation_id,
        }


class EventBus:
    """
    Async event bus with priority queuing.
    
    Design decisions:
    - asyncio.PriorityQueue: kill-switch events jump the queue
    - Per-type subscriber dict: O(1) routing
    - Event history: full audit trail (capped at 10k for memory)
    - No blocking calls: everything async
    """

    def __init__(self, history_limit: int = 10_000):
        self._subscribers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._wildcard_subscribers: List[Callable] = []
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._history: List[Event] = []
        self._history_limit = history_limit
        self._running = False
        self._processed_count = 0
        self._error_count = 0
        self._broadcast_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """Subscribe to a specific event type."""
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed {handler.__qualname__} to {event_type.value}")

    def subscribe_all(self, handler: Callable) -> None:
        """Subscribe to ALL events — used by orchestrator and monitoring."""
        self._wildcard_subscribers.append(handler)

    async def publish(self, event: Event) -> None:
        """Publish an event. Priority 1 events go to front of queue."""
        # Priority queue needs (priority, counter, event) for stability
        await self._queue.put((event.priority, event.timestamp, event))
        
        # Also push to WebSocket broadcast queue (non-blocking)
        try:
            self._broadcast_queue.put_nowait(event.to_dict())
        except asyncio.QueueFull:
            pass  # Drop broadcast if WebSocket is behind — never drop trading events

        logger.debug(f"Published {event.event_type.value} from {event.source_agent}")

    async def start(self) -> None:
        """Start the event processing loop."""
        self._running = True
        logger.info("EventBus started")
        await self._process_loop()

    async def stop(self) -> None:
        self._running = False
        logger.info(f"EventBus stopped. Processed: {self._processed_count}, Errors: {self._error_count}")

    async def _process_loop(self) -> None:
        while self._running:
            try:
                # Timeout allows clean shutdown
                _, _, event = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                await self._dispatch(event)
                self._processed_count += 1
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self._error_count += 1
                logger.error(f"EventBus dispatch error: {e}", exc_info=True)

    async def _dispatch(self, event: Event) -> None:
        """Fan-out event to all relevant subscribers."""
        self._record_history(event)
        
        handlers = (
            self._subscribers.get(event.event_type, []) +
            self._wildcard_subscribers
        )

        if not handlers:
            logger.debug(f"No handlers for {event.event_type.value}")
            return

        tasks = [asyncio.create_task(self._safe_call(h, event)) for h in handlers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call(self, handler: Callable, event: Event) -> None:
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception as e:
            self._error_count += 1
            logger.error(f"Handler {handler.__qualname__} failed on {event.event_type.value}: {e}")

    def _record_history(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit:]

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100
    ) -> List[dict]:
        history = self._history
        if event_type:
            history = [e for e in history if e.event_type == event_type]
        return [e.to_dict() for e in history[-limit:]]

    @property
    def stats(self) -> dict:
        return {
            "processed": self._processed_count,
            "errors": self._error_count,
            "queue_size": self._queue.qsize(),
            "history_size": len(self._history),
            "subscribers": {k.value: len(v) for k, v in self._subscribers.items()},
        }


# Global singleton — one bus, one source of truth
_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
