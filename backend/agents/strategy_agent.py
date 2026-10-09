"""
Strategy Agent — Identifies trading opportunities.
Supports: Trend Following, Mean Reversion, Breakout, RSI divergence.

This agent consumes market data and emits directional signals.
It does NOT make trade decisions — that's the orchestrator's job.

In production: swap the mock calculations with real TA-Lib calls
and your trained ML model inference.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)


class StrategyType(str, Enum):
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    RSI_DIVERGENCE = "rsi_divergence"


@dataclass
class TechnicalIndicators:
    symbol: str
    price: float
    sma_20: float
    sma_50: float
    sma_200: float
    rsi_14: float
    macd_line: float
    macd_signal: float
    bb_upper: float
    bb_lower: float
    bb_mid: float
    volume: float
    avg_volume: float
    atr_14: float  # Average True Range — volatility measure
    spread_bps: Optional[float] = None

    @property
    def price_vs_sma20(self) -> float:
        return (self.price - self.sma_20) / self.sma_20

    @property
    def price_vs_sma50(self) -> float:
        return (self.price - self.sma_50) / self.sma_50

    @property
    def macd_histogram(self) -> float:
        return self.macd_line - self.macd_signal

    @property
    def bb_position(self) -> float:
        """0 = at lower band, 1 = at upper band"""
        band_width = self.bb_upper - self.bb_lower
        if band_width == 0:
            return 0.5
        return (self.price - self.bb_lower) / band_width

    @property
    def is_golden_cross(self) -> bool:
        return self.sma_50 > self.sma_200

    @property
    def volume_ratio(self) -> float:
        return self.volume / max(self.avg_volume, 1)


@dataclass
class OhlcvCandle:
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


class StrategyAgent(BaseAgent):
    """
    Multi-strategy signal generator.
    
    Each strategy runs independently and votes.
    Final signal aggregates all active strategy votes.
    """

    def __init__(self, active_strategies: Optional[List[StrategyType]] = None):
        super().__init__("strategy_agent", "Strategy Agent")
        self.active_strategies = active_strategies or [
            StrategyType.TREND_FOLLOWING,
            StrategyType.MEAN_REVERSION,
            StrategyType.BREAKOUT,
            StrategyType.RSI_DIVERGENCE,
        ]
        self._indicators_cache: Dict[str, TechnicalIndicators] = {}
        self._price_history: Dict[str, List[float]] = {}
        self._signal_history: List[dict] = []
        self._watchlist: List[str] = ["AAPL", "MSFT", "BTC-USD", "ETH-USD", "EUR-USD"]

    async def initialize(self) -> None:
        self.bus.subscribe(EventType.MARKET_DATA_UPDATE, self.handle_event)
        logger.info(f"Strategy Agent initialized | strategies: {[s.value for s in self.active_strategies]}")

    async def process_event(self, event: Event) -> None:
        if event.event_type != EventType.MARKET_DATA_UPDATE:
            return

        payload = event.payload
        symbol = payload.get("symbol")
        if not symbol or symbol not in self._watchlist:
            return

        # Build indicator snapshot from incoming data
        indicators = self._build_indicators(symbol, payload)
        if not indicators:
            return

        self._indicators_cache[symbol] = indicators

        # Run all active strategies
        strategy_signals = []
        for strategy in self.active_strategies:
            result = self._run_strategy(strategy, indicators)
            if result:
                strategy_signals.append(result)

        if not strategy_signals:
            return

        # Aggregate strategy votes into one signal
        final_signal = self._aggregate_strategy_signals(symbol, strategy_signals)
        if final_signal:
            await self._emit_signal(symbol, final_signal, indicators)

    def _build_indicators(self, symbol: str, payload: dict) -> Optional[TechnicalIndicators]:
        """
        Build TechnicalIndicators from market data payload.
        In production: use real OHLCV data + TA-Lib calculations.
        """
        try:
            price = float(payload.get("price", 0))
            if price <= 0:
                return None

            history = self._price_history.setdefault(symbol, [])
            history.append(price)
            if len(history) > 240:
                del history[:-240]

            ohlcv = payload.get("ohlcv") or payload.get("candles")
            if ohlcv:
                indicators = self._indicators_from_ohlcv(symbol, payload, ohlcv)
            elif self._payload_has_indicators(payload):
                indicators = self._indicators_from_payload(symbol, payload, price)
            else:
                indicators = self._indicators_from_history(symbol, payload, history)

            if indicators is None:
                return None
            return indicators
        except Exception as e:
            logger.error(f"Failed to build indicators for {symbol}: {e}")
            return None

    def _payload_has_indicators(self, payload: dict) -> bool:
        required = [
            "sma_20", "sma_50", "sma_200", "rsi", "macd_line",
            "macd_signal", "bb_upper", "bb_lower", "bb_mid", "atr",
            "avg_volume",
        ]
        return all(payload.get(key) is not None for key in required)

    def _indicators_from_payload(
        self, symbol: str, payload: dict, price: float
    ) -> TechnicalIndicators:
        return TechnicalIndicators(
            symbol=symbol,
            price=price,
            sma_20=float(payload["sma_20"]),
            sma_50=float(payload["sma_50"]),
            sma_200=float(payload["sma_200"]),
            rsi_14=float(payload["rsi"]),
            macd_line=float(payload["macd_line"]),
            macd_signal=float(payload["macd_signal"]),
            bb_upper=float(payload["bb_upper"]),
            bb_lower=float(payload["bb_lower"]),
            bb_mid=float(payload["bb_mid"]),
            volume=float(payload["volume"]),
            avg_volume=float(payload["avg_volume"]),
            atr_14=float(payload["atr"]),
            spread_bps=payload.get("spread_bps"),
        )

    def _indicators_from_ohlcv(
        self, symbol: str, payload: dict, raw_candles: List[dict]
    ) -> Optional[TechnicalIndicators]:
        candles = self._normalize_ohlcv(raw_candles)
        if len(candles) < 50:
            return None

        candles = candles[-240:]
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]

        price = float(payload.get("price") or closes[-1])
        sma_20 = self._sma(closes, 20)
        sma_50 = self._sma(closes, 50)
        sma_200 = self._sma(closes, min(200, len(closes)))
        rsi = self._rsi(closes, 14)
        macd_line, macd_signal = self._macd(closes)

        closes_20 = closes[-20:]
        std_20 = float(np.std(closes_20))
        bb_mid = sma_20
        bb_upper = bb_mid + 2 * std_20
        bb_lower = bb_mid - 2 * std_20
        atr = self._atr_from_ohlcv(highs, lows, closes, 14)
        volume = volumes[-1]
        avg_volume = sum(volumes[-20:]) / max(len(volumes[-20:]), 1)

        return TechnicalIndicators(
            symbol=symbol,
            price=price,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            rsi_14=rsi,
            macd_line=macd_line,
            macd_signal=macd_signal,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            bb_mid=bb_mid,
            volume=volume,
            avg_volume=avg_volume,
            atr_14=atr,
            spread_bps=payload.get("spread_bps"),
        )

    def _normalize_ohlcv(self, raw_candles: List[dict]) -> List[OhlcvCandle]:
        candles = []
        for raw in raw_candles:
            try:
                open_price = float(raw.get("open") or 0)
                high = float(raw.get("high") or 0)
                low = float(raw.get("low") or 0)
                close = float(raw.get("close") or 0)
                if min(open_price, high, low, close) <= 0:
                    continue
                volume = float(
                    raw.get("volume")
                    or raw.get("tick_volume")
                    or raw.get("real_volume")
                    or 0
                )
                candles.append(
                    OhlcvCandle(
                        timestamp=float(raw.get("time") or raw.get("timestamp") or 0),
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                    )
                )
            except (TypeError, ValueError):
                continue
        return candles

    def _indicators_from_history(
        self, symbol: str, payload: dict, history: List[float]
    ) -> Optional[TechnicalIndicators]:
        if len(history) < 50:
            return None

        price = history[-1]
        sma_20 = self._sma(history, 20)
        sma_50 = self._sma(history, 50)
        sma_200 = self._sma(history, min(200, len(history)))
        rsi = self._rsi(history, 14)
        macd_line, macd_signal = self._macd(history)

        prices_20 = history[-20:]
        std_20 = float(np.std(prices_20))
        bb_mid = sma_20
        bb_upper = bb_mid + 2 * std_20
        bb_lower = bb_mid - 2 * std_20
        atr = self._atr_from_prices(history, 14)
        volume = float(payload.get("volume") or 0)
        avg_volume = float(payload.get("avg_volume") or volume or 1)

        return TechnicalIndicators(
            symbol=symbol,
            price=price,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            rsi_14=rsi,
            macd_line=macd_line,
            macd_signal=macd_signal,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            bb_mid=bb_mid,
            volume=volume,
            avg_volume=avg_volume,
            atr_14=atr,
            spread_bps=payload.get("spread_bps"),
        )

    def _sma(self, values: List[float], period: int) -> float:
        window = values[-period:]
        return sum(window) / len(window)

    def _ema(self, values: List[float], period: int) -> float:
        if not values:
            return 0.0
        alpha = 2 / (period + 1)
        ema = values[0]
        for value in values[1:]:
            ema = value * alpha + ema * (1 - alpha)
        return ema

    def _macd(self, values: List[float]) -> Tuple[float, float]:
        ema_12 = self._ema(values, 12)
        ema_26 = self._ema(values, 26)
        macd_line = ema_12 - ema_26
        if len(values) < 35:
            return macd_line, macd_line
        macd_series = []
        for idx in range(26, len(values) + 1):
            window = values[:idx]
            macd_series.append(self._ema(window, 12) - self._ema(window, 26))
        return macd_line, self._ema(macd_series, min(9, len(macd_series)))

    def _rsi(self, values: List[float], period: int = 14) -> float:
        if len(values) < period + 1:
            return 50.0
        changes = [
            values[i] - values[i - 1]
            for i in range(len(values) - period, len(values))
        ]
        gains = [max(0.0, change) for change in changes]
        losses = [abs(min(0.0, change)) for change in changes]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _atr_from_prices(self, values: List[float], period: int = 14) -> float:
        recent = values[-period:]
        if len(recent) < 2:
            return max(values[-1] * 0.001, 0.00001)
        ranges = [abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
        atr = sum(ranges) / len(ranges)
        return max(atr, values[-1] * 0.00005)

    def _atr_from_ohlcv(
        self, highs: List[float], lows: List[float], closes: List[float], period: int = 14
    ) -> float:
        if len(closes) < 2:
            return max(closes[-1] * 0.001, 0.00001)
        start = max(1, len(closes) - period)
        true_ranges = []
        for idx in range(start, len(closes)):
            true_ranges.append(
                max(
                    highs[idx] - lows[idx],
                    abs(highs[idx] - closes[idx - 1]),
                    abs(lows[idx] - closes[idx - 1]),
                )
            )
        atr = sum(true_ranges) / max(len(true_ranges), 1)
        return max(atr, closes[-1] * 0.00005)

    def _run_strategy(
        self, strategy: StrategyType, ind: TechnicalIndicators
    ) -> Optional[Tuple[str, float, str]]:
        """
        Returns (direction, confidence, reasoning) or None if no signal.
        
        Each strategy has clear, testable rules.
        If you can't articulate the rule, don't trade it.
        """
        if strategy == StrategyType.TREND_FOLLOWING:
            return self._trend_following(ind)
        elif strategy == StrategyType.MEAN_REVERSION:
            return self._mean_reversion(ind)
        elif strategy == StrategyType.BREAKOUT:
            return self._breakout(ind)
        elif strategy == StrategyType.RSI_DIVERGENCE:
            return self._rsi_divergence(ind)
        return None

    def _trend_following(self, ind: TechnicalIndicators) -> Optional[Tuple[str, float, str]]:
        """
        Rules:
        - BUY: Price > SMA20 > SMA50, Golden cross, Volume confirmation
        - SELL: Price < SMA20 < SMA50, Death cross, Volume confirmation
        """
        is_uptrend = (
            ind.price > ind.sma_20 and
            ind.sma_20 > ind.sma_50 and
            ind.is_golden_cross and
            ind.macd_histogram > 0
        )
        is_downtrend = (
            ind.price < ind.sma_20 and
            ind.sma_20 < ind.sma_50 and
            not ind.is_golden_cross and
            ind.macd_histogram < 0
        )
        volume_confirmed = ind.volume_ratio > 1.2

        if is_uptrend and volume_confirmed:
            confidence = min(0.85, 0.5 + abs(ind.price_vs_sma20) * 5)
            return ("BUY", confidence, "Trend following: uptrend confirmed with volume")
        elif is_downtrend and volume_confirmed:
            confidence = min(0.85, 0.5 + abs(ind.price_vs_sma20) * 5)
            return ("SELL", confidence, "Trend following: downtrend confirmed with volume")

        return None

    def _mean_reversion(self, ind: TechnicalIndicators) -> Optional[Tuple[str, float, str]]:
        """
        Rules:
        - BUY: Price at/below lower BB, RSI oversold (<30)
        - SELL: Price at/above upper BB, RSI overbought (>70)
        """
        oversold = ind.rsi_14 < 32 and ind.bb_position < 0.15
        overbought = ind.rsi_14 > 68 and ind.bb_position > 0.85

        if oversold:
            # Confidence scales with how extreme the oversold condition is
            rsi_excess = (32 - ind.rsi_14) / 32
            bb_excess = (0.15 - ind.bb_position) / 0.15
            confidence = min(0.80, 0.45 + (rsi_excess + bb_excess) * 0.3)
            return ("BUY", confidence, f"Mean reversion: RSI={ind.rsi_14:.1f}, BB={ind.bb_position:.2f} oversold")
        elif overbought:
            rsi_excess = (ind.rsi_14 - 68) / 32
            bb_excess = (ind.bb_position - 0.85) / 0.15
            confidence = min(0.80, 0.45 + (rsi_excess + bb_excess) * 0.3)
            return ("SELL", confidence, f"Mean reversion: RSI={ind.rsi_14:.1f}, BB={ind.bb_position:.2f} overbought")

        return None

    def _breakout(self, ind: TechnicalIndicators) -> Optional[Tuple[str, float, str]]:
        """
        Rules:
        - BUY: Price breaks above upper BB with high volume (3x surge expected)
        - SELL: Price breaks below lower BB with high volume
        
        Note: Breakouts need sequential data in production. 
        Here we approximate with BB + volume.
        """
        high_volume_breakout = ind.volume_ratio > 2.0
        upside_breakout = ind.price > ind.bb_upper and high_volume_breakout
        downside_breakout = ind.price < ind.bb_lower and high_volume_breakout

        if upside_breakout:
            confidence = min(0.75, 0.45 + (ind.volume_ratio - 2.0) * 0.1)
            return ("BUY", confidence, f"Breakout: above BB with {ind.volume_ratio:.1f}x volume")
        elif downside_breakout:
            confidence = min(0.75, 0.45 + (ind.volume_ratio - 2.0) * 0.1)
            return ("SELL", confidence, f"Breakout: below BB with {ind.volume_ratio:.1f}x volume")

        return None

    def _rsi_divergence(self, ind: TechnicalIndicators) -> Optional[Tuple[str, float, str]]:
        """
        RSI neutral zone entry — when RSI crosses 50 with momentum.
        Simple but effective as a confirmation signal.
        """
        bullish_cross = 48 < ind.rsi_14 < 55 and ind.macd_histogram > 0
        bearish_cross = 45 < ind.rsi_14 < 52 and ind.macd_histogram < 0

        if bullish_cross:
            return ("BUY", 0.45, f"RSI momentum cross up: {ind.rsi_14:.1f}")
        elif bearish_cross:
            return ("SELL", 0.45, f"RSI momentum cross down: {ind.rsi_14:.1f}")

        return None

    def _aggregate_strategy_signals(
        self, symbol: str, signals: List[Tuple[str, float, str]]
    ) -> Optional[dict]:
        """
        Combine multiple strategy signals into one.
        Direction must have majority agreement; confidence averages.
        """
        buy_signals = [(conf, reason) for dir, conf, reason in signals if dir == "BUY"]
        sell_signals = [(conf, reason) for dir, conf, reason in signals if dir == "SELL"]

        if not buy_signals and not sell_signals:
            return None

        # Direction by majority
        if len(buy_signals) > len(sell_signals):
            direction = "BUY"
            relevant = buy_signals
        elif len(sell_signals) > len(buy_signals):
            direction = "SELL"
            relevant = sell_signals
        else:
            # Tie — compare average confidence
            buy_conf = sum(c for c, _ in buy_signals) / len(buy_signals)
            sell_conf = sum(c for c, _ in sell_signals) / len(sell_signals)
            if buy_conf > sell_conf:
                direction = "BUY"
                relevant = buy_signals
            else:
                direction = "SELL"
                relevant = sell_signals

        avg_confidence = sum(c for c, _ in relevant) / len(relevant)
        # Bonus confidence for consensus
        if len(relevant) == len(signals):  # All strategies agree
            avg_confidence = min(0.95, avg_confidence * 1.15)

        combined_reasoning = " | ".join(r for _, r in relevant)

        return {
            "direction": direction,
            "confidence": round(avg_confidence, 4),
            "reasoning": combined_reasoning,
            "strategy_count": len(relevant),
        }

    async def _emit_signal(
        self, symbol: str, signal: dict, ind: TechnicalIndicators
    ) -> None:
        self.metrics.signals_generated += 1
        payload = {
            "symbol": symbol,
            "direction": signal["direction"],
            "confidence": signal["confidence"],
            "reasoning": signal["reasoning"],
            "strategy_count": signal["strategy_count"],
            "price": ind.price,
            "spread_bps": ind.spread_bps,
            "indicators": {
                "price": ind.price,
                "rsi": ind.rsi_14,
                "sma_20": ind.sma_20,
                "sma_50": ind.sma_50,
                "sma_200": ind.sma_200,
                "macd_histogram": ind.macd_histogram,
                "macd_line": ind.macd_line,
                "macd_signal": ind.macd_signal,
                "bb_position": ind.bb_position,
                "volume_ratio": ind.volume_ratio,
                "atr": ind.atr_14,
            },
            "ttl_seconds": 120.0,
        }
        await self.publish(EventType.STRATEGY_SIGNAL, payload, priority=3)
        
        logger.info(
            f"Strategy signal: {symbol} {signal['direction']} "
            f"({signal['confidence']:.0%}) — {signal['reasoning'][:80]}"
        )
        self._signal_history.append({"timestamp": time.time(), **payload})
        if len(self._signal_history) > 500:
            self._signal_history = self._signal_history[-500:]

    def add_to_watchlist(self, symbol: str) -> None:
        if symbol not in self._watchlist:
            self._watchlist.append(symbol)
            logger.info(f"Added {symbol} to strategy watchlist")

    def remove_from_watchlist(self, symbol: str) -> None:
        self._watchlist = [s for s in self._watchlist if s != symbol]

    @property
    def watchlist(self) -> List[str]:
        return self._watchlist.copy()

    @property
    def recent_signals(self) -> List[dict]:
        return self._signal_history[-20:]
