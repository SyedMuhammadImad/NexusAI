from agents.strategy_agent import StrategyAgent


def broker_payload(symbol="EURUSDm", price=1.1):
    return {
        "symbol": symbol,
        "asset_class": "broker",
        "price": price,
        "bid": price - 0.00001,
        "ask": price + 0.00001,
        "volume": 0.0,
        "spread_bps": 0.2,
    }


def test_strategy_waits_for_broker_history_before_indicators():
    agent = StrategyAgent()

    for i in range(49):
        indicators = agent._build_indicators("EURUSDm", broker_payload(price=1.1 + i * 0.00001))

    assert indicators is None


def test_strategy_builds_broker_indicators_from_observed_history():
    agent = StrategyAgent()
    indicators = None

    for i in range(50):
        indicators = agent._build_indicators("EURUSDm", broker_payload(price=1.1 + i * 0.00001))

    assert indicators is not None
    assert indicators.symbol == "EURUSDm"
    assert indicators.spread_bps == 0.2
    assert indicators.atr_14 > 0
    assert indicators.sma_20 > 1.1
    assert indicators.sma_50 > 1.1


def test_strategy_prefers_ohlcv_candles_for_broker_indicators():
    agent = StrategyAgent()
    candles = []
    for i in range(60):
        close = 1.1 + i * 0.0001
        candles.append({
            "time": i,
            "open": close - 0.00005,
            "high": close + 0.0002,
            "low": close - 0.0002,
            "close": close,
            "tick_volume": 100 + i,
        })

    payload = broker_payload(price=1.2)
    payload["ohlcv"] = candles

    indicators = agent._build_indicators("EURUSDm", payload)

    assert indicators is not None
    assert indicators.price == 1.2
    assert indicators.volume == 159
    assert indicators.avg_volume > 140
    assert indicators.atr_14 >= 0.00039
