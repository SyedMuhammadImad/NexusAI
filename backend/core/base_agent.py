"""
Base Agent — Every agent inherits from this. 
Enforces: lifecycle management, health reporting, structured logging, 
performance tracking. No rogue agents allowed.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from core.event_bus import Event, EventBus, EventType, get_event_bus

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class AgentMetrics:
    """Performance tracking for every agent."""
    events_processed: int = 0
    events_published: int = 0
    errors: int = 0
    last_active: float = field(default_factory=time.time)
    avg_processing_ms: float = 0.0
    signals_generated: int = 0
    uptime_start: float = field(default_factory=time.time)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.uptime_start

    def to_dict(self) -> dict:
        return {
            "events_processed": self.events_processed,
            "events_published": self.events_published,
            "errors": self.errors,
            "last_active": self.last_active,
            "avg_processing_ms": round(self.avg_processing_ms, 2),
            "signals_generated": self.signals_generated,
            "uptime_seconds": round(self.uptime_seconds, 1),
        }


class BaseAgent(ABC):
    """
    Abstract base for all trading agents.
    
    Contract every agent must fulfill:
    1. initialize() — async setup, subscribe to events
    2. process_event(event) — handle incoming events
    3. start() / stop() — lifecycle management
    4. health_check() — heartbeat response
    
    What this gives you automatically:
    - Performance timing on every event
    - Error isolation (one bad agent can't crash others)
    - Status reporting
    - Pause/resume without restart
    """

    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name
        self.bus: EventBus = get_event_bus()
        self.status: AgentStatus = AgentStatus.INITIALIZING
        self.metrics: AgentMetrics = AgentMetrics()
        self._enabled: bool = True
        self._heartbeat_interval: float = 30.0
        self._config: Dict[str, Any] = {}
        logger.info(f"Agent created: {self.name} ({self.agent_id})")

    @abstractmethod
    async def initialize(self) -> None:
        """Subscribe to events and set up resources."""
        pass

    @abstractmethod
    async def process_event(self, event: Event) -> None:
        """Handle an incoming event."""
        pass

    async def start(self) -> None:
        """Start the agent — initializes and begins heartbeat."""
        try:
            await self.initialize()
            self.status = AgentStatus.RUNNING
            asyncio.create_task(self._heartbeat_loop())
            logger.info(f"{self.name} started")
            await self._publish_status("started")
        except Exception as e:
            self.status = AgentStatus.ERROR
            logger.error(f"{self.name} failed to start: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        self.status = AgentStatus.STOPPED
        await self._publish_status("stopped")
        logger.info(f"{self.name} stopped | metrics: {self.metrics.to_dict()}")

    def pause(self) -> None:
        self._enabled = False
        self.status = AgentStatus.PAUSED
        logger.warning(f"{self.name} paused")

    def resume(self) -> None:
        self._enabled = True
        self.status = AgentStatus.RUNNING
        logger.info(f"{self.name} resumed")

    async def handle_event(self, event: Event) -> None:
        """
        Wraps process_event with timing, error handling, and metrics.
        This is what gets registered as the event subscriber.
        """
        if not self._enabled:
            return

        start_ms = time.time() * 1000
        try:
            await self.process_event(event)
            self.metrics.events_processed += 1
            self.metrics.last_active = time.time()
            elapsed = time.time() * 1000 - start_ms
            # Exponential moving average
            self.metrics.avg_processing_ms = (
                0.9 * self.metrics.avg_processing_ms + 0.1 * elapsed
            )
        except Exception as e:
            self.metrics.errors += 1
            self.status = AgentStatus.ERROR
            logger.error(f"{self.name} error processing {event.event_type.value}: {e}", exc_info=True)
            # Don't re-raise — isolate the failure

    async def publish(
        self,
        event_type: EventType,
        payload: dict,
        priority: int = 5,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Publish an event. Tracks metrics."""
        event = Event(
            event_type=event_type,
            source_agent=self.agent_id,
            payload=payload,
            priority=priority,
            correlation_id=correlation_id,
        )
        await self.bus.publish(event)
        self.metrics.events_published += 1

    def health_check(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status.value,
            "enabled": self._enabled,
            "metrics": self.metrics.to_dict(),
        }

    def update_config(self, config: Dict[str, Any]) -> None:
        """Hot-reload config without restart."""
        self._config.update(config)
        logger.info(f"{self.name} config updated: {config}")

    async def _heartbeat_loop(self) -> None:
        while self.status not in (AgentStatus.STOPPED,):
            await asyncio.sleep(self._heartbeat_interval)
            if self.status == AgentStatus.RUNNING:
                await self._publish_status("heartbeat")

    async def _publish_status(self, event_subtype: str) -> None:
        await self.publish(
            EventType.AGENT_STATUS,
            {
                "subtype": event_subtype,
                "agent_id": self.agent_id,
                "name": self.name,
                "status": self.status.value,
                "metrics": self.metrics.to_dict(),
            },
            priority=8,
        )
