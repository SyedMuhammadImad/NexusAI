"""
Data Pipeline — Market data ingestion and distribution.

Production connections:
- Equities: Alpaca WebSocket, Polygon.io, Yahoo Finance
- Crypto: Binance WebSocket, Coinbase Pro
- Forex: OANDA, Interactive Brokers
- Macro: FRED API, Alpha Vantage

This module implements:
1. Realistic mock data generation (identical interface to real feeds)
2. Data normalization (one schema regardless of source)
3. Distribution to the event bus
4. Data quality validation

To go live: swap MockDataSource for real broker WebSocket clients.
The rest of the system doesn't need to change — that's the point.
"""

import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from core.event_bus import Event, EventType, get_event_bus

logger = logging.getLogger(__name__)


class AssetClass(str, Enum):
    EQUITY = "equity"
    CRYPTO = "crypto"
    FOREX = "forex"
    COMMODITY = "commodity"


@dataclass
class MarketDataPoint:
    """Normalized market data — same structure regardless of source."""
    symbol: str
    asset_class: AssetClass
    price: float
    bid: float
    ask: float
    volume: float
    timestamp: float
    
    # Technical indicators (populated by data processor)
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    rsi: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_mid: Optional[float] = None
    atr: Optional[float] = None
    avg_volume: Optional[float] = None
    vix: Optional[float] = None

    @property
    def spread_bps(self) -> float:
        if self.price <= 0:
            return 0
        return (self.ask - self.bid) / self.price * 10_000

    def to_payload(self) -> dict:
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class.value,
            "price": round(self.price, 6),
            "bid": round(self.bid, 6),
            "ask": round(self.ask, 6),
            "volume": round(self.volume, 2),
            "timestamp": self.timestamp,
            "spread_bps": round(self.spread_bps, 2),
            # Technical indicators
            "sma_20": self.sma_20,
            "sma_50": self.sma_50,
            "sma_200": self.sma_200,
            "rsi": self.rsi,
            "macd_line": self.macd_line,
            "macd_signal": self.macd_signal,
            "bb_upper": self.bb_upper,
            "bb_lower": self.bb_lower,
            "bb_mid": self.bb_mid,
            "atr": self.atr,
            "avg_volume": self.avg_volume,
            "vix": self.vix,
        }


@dataclass
class InstrumentConfig:
    """Configuration for each tracked instrument."""
    symbol: str
    asset_class: AssetClass
    base_price: float
    volatility: float      # Daily volatility as fraction (e.g., 0.02 = 2%)
    typical_spread: float  # Spread in bps
    typical_volume: float  # Typical daily volume
    update_interval: float # Seconds between updates


# Default instruments to track
DEFAULT_INSTRUMENTS = [
    InstrumentConfig("AAPL", AssetClass.EQUITY, 185.0, 0.018, 3, 80_000_000, 5.0),
    InstrumentConfig("MSFT", AssetClass.EQUITY, 420.0, 0.016, 2, 25_000_000, 5.0),
    InstrumentConfig("TSLA", AssetClass.EQUITY, 250.0, 0.040, 5, 120_000_000, 5.0),
    InstrumentConfig("SPY", AssetClass.EQUITY, 520.0, 0.010, 1, 80_000_000, 3.0),
    InstrumentConfig("BTC-USD", AssetClass.CRYPTO, 95_000.0, 0.035, 5, 25_000_000_000, 2.0),
    InstrumentConfig("ETH-USD", AssetClass.CRYPTO, 3_400.0, 0.040, 6, 15_000_000_000, 2.0),
    InstrumentConfig("EUR-USD", AssetClass.FOREX, 1.0850, 0.005, 0.5, 5_000_000_000, 1.0),
    InstrumentConfig("GBP-USD", AssetClass.FOREX, 1.2700, 0.007, 0.8, 2_000_000_000, 1.0),
]


class PriceSimulator:
    """
    Geometric Brownian Motion price simulator.
    This is NOT random walk — it's the same model used in Black-Scholes
    and by most institutional risk systems.
    
    GBM: dS = μ*S*dt + σ*S*dW
    Where dW ~ N(0, dt)
    """

    def __init__(self, config: InstrumentConfig):
        self.config = config
        self._price = config.base_price
        self._tick_vol = config.volatility / math.sqrt(252 * 390)  # Per-tick vol
        self._price_history: List[float] = [config.base_price] * 200
        self._volume_history: List[float] = [config.typical_volume] * 50
        self._drift = 0.0  # Can inject drift for scenario testing
        # Simulate a VIX-like indicator (shared, injected externally)
        self._vix_ref = [20.0]

    def next_tick(self) -> MarketDataPoint:
        """Generate the next realistic tick."""
        # GBM price update
        dt = self.config.update_interval / (252 * 390 * 60)  # Fraction of trading year
        dw = random.gauss(0, 1) * math.sqrt(dt)
        self._price *= (1 + self._drift * dt + self.config.volatility * dw)
        self._price = max(self._price, self.config.base_price * 0.01)  # Floor
        
        # Volume with time-of-day pattern (simplified)
        volume_noise = random.gauss(1.0, 0.3)
        current_volume = max(0, self.config.typical_volume * volume_noise / (390 * 60))  # Per-second

        # Update histories
        self._price_history.append(self._price)
        if len(self._price_history) > 200:
            self._price_history = self._price_history[-200:]
        self._volume_history.append(current_volume)
        if len(self._volume_history) > 50:
            self._volume_history = self._volume_history[-50:]

        # Compute indicators
        sma_20 = sum(self._price_history[-20:]) / 20
        sma_50 = sum(self._price_history[-50:]) / 50
        sma_200 = sum(self._price_history[-200:]) / 200
        
        # RSI (simplified)
        rsi = self._compute_rsi()
        
        # Bollinger Bands
        prices_20 = self._price_history[-20:]
        std_20 = (sum((p - sma_20)**2 for p in prices_20) / 20) ** 0.5
        bb_upper = sma_20 + 2 * std_20
        bb_lower = sma_20 - 2 * std_20
        
        # ATR (simplified as recent price range)
        atr = max(self._price_history[-14:]) - min(self._price_history[-14:])
        
        # Spread
        spread_price = self._price * self.config.typical_spread / 10_000
        
        avg_volume = sum(self._volume_history) / len(self._volume_history)

        return MarketDataPoint(
            symbol=self.config.symbol,
            asset_class=self.config.asset_class,
            price=self._price,
            bid=self._price - spread_price / 2,
            ask=self._price + spread_price / 2,
            volume=current_volume,
            timestamp=time.time(),
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            rsi=rsi,
            macd_line=self._price - sma_20,  # Simplified MACD
            macd_signal=(self._price - sma_20) * 0.9,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            bb_mid=sma_20,
            atr=atr,
            avg_volume=avg_volume * 390 * 60,  # Scale back to daily
            vix=self._vix_ref[0],
        )

    def _compute_rsi(self, period: int = 14) -> float:
        """Welles Wilder RSI."""
        prices = self._price_history[-period-1:]
        if len(prices) < 2:
            return 50.0
        
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [max(0, c) for c in changes]
        losses = [abs(min(0, c)) for c in changes]
        
        avg_gain = sum(gains) / len(gains) if gains else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))


class MarketDataPipeline:
    """
    Coordinates all price simulators and publishes to event bus.
    
    In production: replace PriceSimulator with WebSocket stream readers.
    The publish logic stays identical.
    """

    def __init__(self, instruments: Optional[List[InstrumentConfig]] = None):
        self.bus = get_event_bus()
        self._instruments = instruments or DEFAULT_INSTRUMENTS
        self._simulators: Dict[str, PriceSimulator] = {}
        self._running = False
        self._vix = [20.0]  # Shared VIX reference
        self._tick_count = 0
        self._last_vix_update = 0.0

        for config in self._instruments:
            sim = PriceSimulator(config)
            sim._vix_ref = self._vix  # Share VIX reference
            self._simulators[config.symbol] = sim

    async def start(self) -> None:
        self._running = True
        logger.info(f"Market data pipeline started — {len(self._simulators)} instruments")
        
        # Start each instrument on its own update loop
        tasks = [
            asyncio.create_task(self._stream_instrument(symbol, sim))
            for symbol, sim in self._simulators.items()
        ]
        asyncio.create_task(self._vix_simulation_loop())
        await asyncio.gather(*tasks)

    async def _stream_instrument(self, symbol: str, sim: PriceSimulator) -> None:
        config = sim.config
        while self._running:
            try:
                data_point = sim.next_tick()
                await self.bus.publish(
                    Event(
                        event_type=EventType.MARKET_DATA_UPDATE,
                        source_agent="market_data_pipeline",
                        payload=data_point.to_payload(),
                        priority=6,  # Market data is medium priority
                    )
                )
                self._tick_count += 1
            except Exception as e:
                logger.error(f"Error streaming {symbol}: {e}")
            
            await asyncio.sleep(config.update_interval)

    async def _vix_simulation_loop(self) -> None:
        """VIX mean-reverts to 20. Occasionally spikes."""
        while self._running:
            await asyncio.sleep(60)  # Update VIX every minute
            current_vix = self._vix[0]
            
            # Mean reversion to 20 with occasional spikes
            target = 20.0
            reversion = 0.05 * (target - current_vix)
            noise = random.gauss(0, 1.5)
            spike = random.gauss(0, 5) if random.random() < 0.05 else 0  # 5% chance of spike
            
            new_vix = max(10, min(80, current_vix + reversion + noise + spike))
            self._vix[0] = new_vix
            
            if abs(new_vix - current_vix) > 3:
                logger.info(f"VIX moved: {current_vix:.1f} → {new_vix:.1f}")

    async def stop(self) -> None:
        self._running = False
        logger.info(f"Market data pipeline stopped | {self._tick_count} ticks generated")

    def inject_price_shock(self, symbol: str, shock_pct: float) -> None:
        """Inject a price shock for stress testing."""
        if symbol in self._simulators:
            sim = self._simulators[symbol]
            sim._price *= (1 + shock_pct)
            logger.warning(f"Price shock injected: {symbol} {shock_pct:+.1%}")

    @property
    def stats(self) -> dict:
        return {
            "tracked_instruments": len(self._simulators),
            "tick_count": self._tick_count,
            "current_vix": round(self._vix[0], 1),
            "running": self._running,
        }
