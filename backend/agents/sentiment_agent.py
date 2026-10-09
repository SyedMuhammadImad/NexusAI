"""
Sentiment Agent — REAL NLP using VADER + Financial Lexicon.

No torch, no GPU, no API key required to start.
Production upgrade path: VADER → FinBERT → Bloomberg NLP

To enable real news: set NEWS_API_KEY environment variable.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from core.base_agent import BaseAgent
from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)

FINANCIAL_LEXICON = {
    "bullish": 2.5, "surge": 2.0, "rally": 2.0, "breakout": 1.8,
    "outperform": 2.0, "beat": 1.5, "upgrade": 2.0, "soar": 2.2,
    "skyrocket": 2.5, "boom": 2.0, "profit": 1.5, "dividend": 1.0,
    "record": 1.5, "strong": 1.2, "robust": 1.2, "momentum": 1.2,
    "acquisition": 0.8, "partnership": 1.0, "innovation": 1.0,
    "growth": 1.2, "expansion": 1.0, "recovery": 1.5, "rebound": 1.5,
    "bearish": -2.5, "crash": -2.5, "collapse": -2.5, "plunge": -2.0,
    "downgrade": -2.0, "loss": -1.5, "debt": -1.0, "recall": -2.0,
    "lawsuit": -1.8, "investigation": -1.5, "fraud": -3.0,
    "bankruptcy": -3.0, "default": -2.5, "layoffs": -1.5, "warning": -1.5,
    "miss": -1.5, "disappointing": -2.0, "concern": -1.0, "risk": -0.8,
    "volatility": -0.5, "uncertainty": -1.0, "headwinds": -1.5,
    "selloff": -2.2, "tumble": -2.0, "slump": -1.8, "tank": -2.0,
    "halt": -1.5, "suspended": -1.5, "delisted": -2.5,
}

SOURCE_WEIGHTS = {
    "bloomberg": 1.0, "reuters": 1.0, "wsj": 0.95, "ft": 0.95,
    "cnbc": 0.70, "marketwatch": 0.65, "seekingalpha": 0.50,
    "reddit": 0.30, "twitter": 0.25, "unknown": 0.20,
}

NEWS_TEMPLATES = {
    "AAPL": [
        "Apple beats quarterly earnings expectations with strong iPhone sales",
        "Apple faces antitrust scrutiny over App Store policies",
        "Apple unveils new AI features across product lineup",
        "Supply chain disruption may impact Apple holiday quarter",
        "Apple shares rally on strong services revenue growth",
        "Analysts upgrade Apple stock on Vision Pro momentum",
        "Apple buyback program extended boosting shareholder returns",
    ],
    "MSFT": [
        "Microsoft Azure cloud growth accelerates beating estimates",
        "Microsoft Copilot drives enterprise AI adoption surge",
        "Microsoft faces EU regulatory concerns over AI bundling",
        "Strong earnings lift Microsoft shares to new record",
        "Microsoft expands data center capacity amid AI demand boom",
        "Microsoft gaming division posts disappointing quarterly results",
    ],
    "TSLA": [
        "Tesla misses delivery estimates amid production challenges",
        "Tesla recalls vehicles over critical software update issue",
        "Tesla Autopilot investigation expands to additional models",
        "Tesla price cuts continue pressuring margins in EV market",
        "Tesla energy storage business posts record breaking quarter",
        "Elon Musk sells Tesla shares raising governance concerns",
        "Tesla Cybertruck production ramp exceeds analyst expectations",
    ],
    "BTC-USD": [
        "Bitcoin ETF inflows hit record as institutional adoption accelerates",
        "Bitcoin surges past key resistance ahead of halving event",
        "Crypto market selloff intensifies as regulatory fears mount",
        "Bitcoin mining difficulty reaches new all-time high",
        "Major exchange reports security incident affecting crypto markets",
        "Bitcoin consolidates as market awaits Federal Reserve decision",
        "Spot Bitcoin ETF sees massive inflows from institutional investors",
    ],
    "ETH-USD": [
        "Ethereum network activity reaches record levels",
        "ETH staking yields attract growing institutional interest",
        "Ethereum upgrade successfully reduces transaction fees",
        "DeFi protocol exploit drains Ethereum liquidity pools",
        "Ethereum ETF approval probability increases say analysts",
        "Ethereum layer 2 adoption accelerates reducing mainnet congestion",
    ],
    "BTCUSDm": [
        "Bitcoin ETF inflows support bullish crypto sentiment",
        "Crypto market falls as risk appetite weakens",
        "Bitcoin rebounds as institutional demand improves",
        "Digital asset selloff weighs on Bitcoin momentum",
    ],
    "EURUSDm": [
        "Euro strengthens as dollar softens after economic data",
        "EUR/USD slips as traders price stronger dollar outlook",
        "European growth data lifts euro sentiment",
        "Dollar rally pressures EUR/USD lower",
        "ECB policy comments support euro against dollar",
    ],
    "XAUUSDm": [
        "Gold rises as safe haven demand increases",
        "Gold prices fall as dollar and yields climb",
        "Central bank buying supports gold market sentiment",
        "Risk-on mood weighs on gold demand",
    ],
    "USOILm": [
        "US crude oil rallies as inventories tighten",
        "Oil prices fall as demand concerns grow",
        "WTI crude rebounds on supply disruption fears",
        "Energy markets weaken after bearish inventory report",
        "US oil gains as OPEC supply cuts support prices",
    ],
    "SPY": [
        "S&P 500 hits fresh record high on stronger than expected jobs data",
        "Markets fall sharply as Fed signals fewer rate cuts ahead",
        "Wall Street rallies on better than expected GDP growth report",
        "Recession fears mount as yield curve inversion deepens",
        "Earnings season broadly beats expectations lifting broad market",
        "Inflation data surprise triggers broad market selloff",
    ],
}

NEWS_SEARCH_TERMS = {
    "AAPL": "Apple stock",
    "MSFT": "Microsoft stock",
    "TSLA": "Tesla stock",
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SPY": "S&P 500",
    "BTCUSDm": "Bitcoin crypto market",
    "EURUSDm": "EUR USD forex euro dollar",
    "XAUUSDm": "gold XAU USD",
    "USOILm": "WTI crude oil US oil",
}

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _sia = SentimentIntensityAnalyzer()
    _sia.lexicon.update(FINANCIAL_LEXICON)
    VADER_AVAILABLE = True
    logger.info("Financial VADER NLP loaded — real NLP active")
except ImportError:
    VADER_AVAILABLE = False
    logger.warning("vaderSentiment not found — using mock (pip install vaderSentiment)")


def score_headline(headline: str) -> Tuple[float, float]:
    if not VADER_AVAILABLE:
        score = random.gauss(0, 0.25)
        return max(-1.0, min(1.0, score)), 0.50
    scores = _sia.polarity_scores(headline)
    compound = scores["compound"]
    non_neutral = scores["pos"] + scores["neg"]
    confidence = min(0.95, 0.4 + abs(compound) * 0.4 + non_neutral * 0.2)
    return compound, confidence


@dataclass
class AggregatedSentiment:
    symbol: str
    score: float
    confidence: float
    item_count: int
    positive_count: int
    negative_count: int
    neutral_count: int
    last_updated: float

    @property
    def direction(self) -> str:
        if self.score >= 0.15 and self.confidence >= 0.45:
            return "BUY"
        elif self.score <= -0.15 and self.confidence >= 0.45:
            return "SELL"
        return "HOLD"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "direction": self.direction,
            "item_count": self.item_count,
            "positive_pct": round(self.positive_count / max(self.item_count, 1) * 100, 1),
            "negative_pct": round(self.negative_count / max(self.item_count, 1) * 100, 1),
            "last_updated": self.last_updated,
            "nlp_engine": "financial_vader" if VADER_AVAILABLE else "mock",
        }


class SentimentAgent(BaseAgent):

    def __init__(self):
        super().__init__("sentiment_agent", "Sentiment Agent")
        self._windows: Dict[str, List[Tuple[float, float, float]]] = {}
        self._aggregated: Dict[str, AggregatedSentiment] = {}
        self._last_emitted: Dict[str, AggregatedSentiment] = {}
        self._recent_news: List[dict] = []
        self._tracked_symbols = ["AAPL", "MSFT", "TSLA", "BTC-USD", "ETH-USD", "SPY"]
        self._decay_half_life = 3600.0
        self._signal_threshold = 0.15
        self._min_confidence = 0.45
        self._min_items = 2
        self._newsapi_key: Optional[str] = None

    async def initialize(self) -> None:
        import os
        self._newsapi_key = os.getenv("NEWS_API_KEY")
        self.bus.subscribe(EventType.MARKET_DATA_UPDATE, self.handle_event)
        asyncio.create_task(self._polling_loop())
        logger.info(f"Sentiment Agent | NLP: {'Financial VADER' if VADER_AVAILABLE else 'Mock'} | NewsAPI: {'YES' if self._newsapi_key else 'NO (simulated)'}")

    async def process_event(self, event: Event) -> None:
        for item in event.payload.get("news", []):
            await self._ingest(item.get("headline", ""), item.get("source", "unknown"), item.get("symbols", []))

    async def _polling_loop(self) -> None:
        await asyncio.sleep(3)
        while True:
            try:
                if self._newsapi_key:
                    await self._fetch_newsapi()
                else:
                    await self._simulate()
                await asyncio.sleep(25)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sentiment polling error: {e}")
                await asyncio.sleep(60)

    async def _simulate(self) -> None:
        symbols = random.sample(self._tracked_symbols, random.randint(1, 2))
        for sym in symbols:
            templates = NEWS_TEMPLATES.get(sym, [])
            if templates:
                headline = random.choice(["", "Breaking: ", "Report: ", "Update: "]) + random.choice(templates)
                await self._ingest(headline, random.choice(list(SOURCE_WEIGHTS.keys())[:6]), [sym])

    async def _fetch_newsapi(self) -> None:
        try:
            import httpx
            for symbol in self._tracked_symbols:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get("https://newsapi.org/v2/everything", params={
                        "q": NEWS_SEARCH_TERMS.get(symbol, symbol),
                        "language": "en", "sortBy": "publishedAt",
                        "pageSize": 5, "apiKey": self._newsapi_key,
                    })
                    if r.status_code == 200:
                        for article in r.json().get("articles", []):
                            h = article.get("title", "")
                            src = article.get("source", {}).get("name", "unknown").lower()
                            if h and "[Removed]" not in h:
                                await self._ingest(h, src, [symbol])
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"NewsAPI error: {e}")

    async def _ingest(self, headline: str, source: str, symbols: List[str]) -> None:
        if not headline:
            return
        raw_score, confidence = score_headline(headline)
        src_w = SOURCE_WEIGHTS.get(source.lower().split(".")[0], 0.20)
        weighted = raw_score * src_w
        conf_w = confidence * src_w

        self._recent_news.append({
            "headline": headline[:120], "source": source,
            "symbols": symbols, "timestamp": time.time(),
            "sentiment_score": round(weighted, 4),
            "sentiment_label": "positive" if weighted > 0.1 else "negative" if weighted < -0.1 else "neutral",
        })
        if len(self._recent_news) > 300:
            self._recent_news = self._recent_news[-300:]

        for sym in symbols:
            if sym not in self._tracked_symbols:
                continue
            if sym not in self._windows:
                self._windows[sym] = []
            self._windows[sym].append((time.time(), weighted, conf_w))
            cutoff = time.time() - 86400
            self._windows[sym] = [t for t in self._windows[sym] if t[0] > cutoff]
            await self._aggregate(sym)

    async def _aggregate(self, symbol: str) -> None:
        window = self._windows.get(symbol, [])
        if not window:
            return
        now = time.time()
        ws = tw = tc = 0.0
        pos = neg = neu = 0
        for ts, score, conf in window:
            tw_ = 2 ** (-(now - ts) / self._decay_half_life)
            ew = tw_ * conf
            ws += score * ew; tw += ew; tc += conf * tw_
            if score >= 0.1: pos += 1
            elif score <= -0.1: neg += 1
            else: neu += 1
        if tw == 0:
            return
        final = ws / tw
        conf = min(0.92, tc / len(window))
        self._aggregated[symbol] = AggregatedSentiment(
            symbol=symbol, score=final, confidence=conf,
            item_count=len(window), positive_count=pos,
            negative_count=neg, neutral_count=neu, last_updated=now,
        )
        agg = self._aggregated[symbol]
        prev = self._last_emitted.get(symbol)
        if (len(window) >= self._min_items and conf >= self._min_confidence and
                abs(final) >= self._signal_threshold and
                (prev is None or prev.direction != agg.direction or abs(final - prev.score) > 0.08)):
            await self._emit(symbol, agg)

    async def _emit(self, symbol: str, agg: AggregatedSentiment) -> None:
        if agg.direction == "HOLD":
            return
        self._last_emitted[symbol] = agg
        self.metrics.signals_generated += 1
        await self.publish(EventType.SENTIMENT_SIGNAL, {
            "symbol": symbol, "direction": agg.direction,
            "confidence": agg.confidence,
            "reasoning": f"NLP score={agg.score:+.3f} | {agg.item_count} articles | +{agg.positive_count}/-{agg.negative_count} | {'VADER' if VADER_AVAILABLE else 'mock'}",
            "sentiment_data": agg.to_dict(), "ttl_seconds": 300.0,
        }, priority=4)
        logger.info(f"Sentiment: {symbol} {agg.direction} score={agg.score:+.3f} ({'REAL' if VADER_AVAILABLE else 'mock'})")

    def add_symbol(self, symbol: str) -> None:
        if symbol not in self._tracked_symbols:
            self._tracked_symbols.append(symbol)

    @property
    def current_sentiment(self) -> Dict[str, dict]:
        return {s: a.to_dict() for s, a in self._aggregated.items()}

    @property
    def recent_news(self) -> List[dict]:
        return self._recent_news[-30:]

    @property
    def nlp_status(self) -> dict:
        return {
            "engine": "financial_vader" if VADER_AVAILABLE else "mock",
            "real_news": self._newsapi_key is not None,
            "tracked_symbols": self._tracked_symbols,
            "articles_processed": len(self._recent_news),
        }
