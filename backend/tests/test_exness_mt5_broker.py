from collections import namedtuple
from types import SimpleNamespace

from brokers.exness_mt5 import ExnessMT5Config, ExnessMT5ReadOnlyBroker


def test_exness_status_reports_missing_config_without_connecting(monkeypatch):
    monkeypatch.delenv("EXNESS_DEMO_LOGIN", raising=False)
    monkeypatch.delenv("EXNESS_DEMO_PASSWORD", raising=False)
    monkeypatch.delenv("EXNESS_DEMO_SERVER", raising=False)

    broker = ExnessMT5ReadOnlyBroker(mt5_module=object())

    status = broker.connect()

    assert status["configured"] is False
    assert status["connected"] is False
    assert status["read_only"] is True
    assert status["trade_execution_enabled"] is False
    assert "EXNESS_DEMO_LOGIN" in status["last_error"]


def test_exness_config_preserves_symbol_case(monkeypatch):
    monkeypatch.setenv("EXNESS_DEMO_LOGIN", "12345678")
    monkeypatch.setenv("EXNESS_DEMO_PASSWORD", "secret-password")
    monkeypatch.setenv("EXNESS_DEMO_SERVER", "Exness-MT5Trial")
    monkeypatch.setenv("EXNESS_SYMBOLS", "XAUUSDm,EURUSDm,BTCUSDm")

    config = ExnessMT5Config.from_env()

    assert config.symbols == ("XAUUSDm", "EURUSDm", "BTCUSDm")


def test_exness_resolves_provider_symbol_aliases(monkeypatch):
    monkeypatch.delenv("EXNESS_SYMBOL_MAP", raising=False)
    config = ExnessMT5Config(
        login=12345678,
        password="secret-password",
        server="Exness-MT5Trial",
        terminal_path="",
        symbols=("XAUUSDm", "EURUSDm", "BTCUSDm", "USOILm"),
        trade_symbols=("EURUSDm", "XAUUSDm", "USOILm"),
        symbol_map=ExnessMT5Config.from_env().symbol_map,
    )
    broker = ExnessMT5ReadOnlyBroker(config=config, mt5_module=object())

    assert broker.resolve_symbol("EURUSD") == "EURUSDm"
    assert broker.resolve_symbol("XAUUSD") == "XAUUSDm"
    assert broker.resolve_symbol("GOLD") == "XAUUSDm"
    assert broker.resolve_symbol("USOIL") == "USOILm"


def test_exness_account_info_masks_login_and_exposes_safe_fields():
    Account = namedtuple(
        "Account",
        "login server name company currency balance equity margin margin_free margin_level leverage trade_mode",
    )

    class FakeMT5:
        def initialize(self, **kwargs):
            self.kwargs = kwargs
            return True

        def account_info(self):
            return Account(
                login=12345678,
                server="Exness-MT5Trial",
                name="Demo User",
                company="Exness",
                currency="USD",
                balance=10000.0,
                equity=10020.0,
                margin=100.0,
                margin_free=9920.0,
                margin_level=10020.0,
                leverage=200,
                trade_mode=0,
            )

        def last_error(self):
            return (0, "OK")

        def shutdown(self):
            return True

    config = ExnessMT5Config(
        login=12345678,
        password="secret-password",
        server="Exness-MT5Trial",
        terminal_path="",
        symbols=("XAUUSDm",),
    )
    broker = ExnessMT5ReadOnlyBroker(config=config, mt5_module=FakeMT5())

    result = broker.account_info()

    assert result["status"]["connected"] is True
    assert result["status"]["config"]["login"] == "12***78"
    assert result["account"]["login"] == "12***78"
    assert result["account"]["balance"] == 10000.0
    assert "password" not in result["account"]


def test_exness_quote_reads_bid_ask_from_mt5():
    Tick = namedtuple("Tick", "bid ask last time time_msc")

    class FakeMT5:
        def initialize(self, **kwargs):
            return True

        def account_info(self):
            return {"login": 12345678}

        def symbol_select(self, symbol, enabled):
            self.selected = (symbol, enabled)
            return True

        def symbol_info_tick(self, symbol):
            return Tick(bid=2301.25, ask=2301.55, last=2301.40, time=1, time_msc=1000)

        def last_error(self):
            return (0, "OK")

        def shutdown(self):
            return True

    config = ExnessMT5Config(
        login=12345678,
        password="secret-password",
        server="Exness-MT5Trial",
        terminal_path="",
        symbols=("XAUUSDm",),
    )
    broker = ExnessMT5ReadOnlyBroker(config=config, mt5_module=FakeMT5())

    result = broker.quote("xauusdm")

    assert result["status"]["connected"] is True
    assert broker._mt5.selected == ("XAUUSDm", True)
    assert result["quote"] == {
        "symbol": "XAUUSDm",
        "bid": 2301.25,
        "ask": 2301.55,
        "last": 2301.40,
        "time": 1,
        "time_msc": 1000,
    }


def test_exness_market_data_payload_includes_m1_ohlcv_when_available():
    Tick = namedtuple("Tick", "bid ask last time time_msc")
    Rate = namedtuple("Rate", "time open high low close tick_volume real_volume")

    class FakeMT5:
        TIMEFRAME_M1 = 1

        def initialize(self, **kwargs):
            return True

        def account_info(self):
            return {"login": 12345678}

        def symbol_select(self, symbol, enabled):
            return True

        def symbol_info_tick(self, symbol):
            return Tick(bid=1.15989, ask=1.15997, last=0.0, time=1, time_msc=1000)

        def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
            return [
                Rate(
                    time=i,
                    open=1.1 + i * 0.0001,
                    high=1.1002 + i * 0.0001,
                    low=1.0998 + i * 0.0001,
                    close=1.1001 + i * 0.0001,
                    tick_volume=100 + i,
                    real_volume=0,
                )
                for i in range(60)
            ]

        def last_error(self):
            return (0, "OK")

    config = ExnessMT5Config(
        login=12345678,
        password="secret-password",
        server="Exness-MT5Trial",
        terminal_path="",
        symbols=("EURUSDm",),
    )
    broker = ExnessMT5ReadOnlyBroker(config=config, mt5_module=FakeMT5())

    result = broker.market_data_payload("EURUSDm")

    assert result["payload"]["ohlcv_timeframe"] == "M1"
    assert len(result["payload"]["ohlcv"]) == 60
    assert result["payload"]["ohlcv"][-1]["tick_volume"] == 159.0


def test_exness_positions_returns_public_broker_snapshot():
    Position = namedtuple(
        "Position",
        "ticket symbol type volume price_open price_current sl tp profit time",
    )
    Info = namedtuple("Info", "trade_contract_size")

    class FakeMT5:
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        POSITION_TYPE_BUY = 0

        def initialize(self, **kwargs):
            return True

        def account_info(self):
            return {"login": 12345678, "trade_mode": 0}

        def positions_get(self):
            return [
                Position(
                    ticket=77,
                    symbol="USOILm",
                    type=0,
                    volume=0.01,
                    price_open=84.0,
                    price_current=84.5,
                    sl=83.0,
                    tp=86.0,
                    profit=5.0,
                    time=123,
                )
            ]

        def symbol_info(self, symbol):
            return Info(trade_contract_size=1000.0)

        def order_calc_margin(self, order_type, symbol, volume, price):
            return 0.42

        def last_error(self):
            return (0, "OK")

    config = ExnessMT5Config(
        login=12345678,
        password="secret-password",
        server="Exness-MT5Trial",
        terminal_path="",
        symbols=("USOILm",),
    )
    broker = ExnessMT5ReadOnlyBroker(config=config, mt5_module=FakeMT5())

    result = broker.positions()

    assert result["positions"] == [{
        "ticket": 77,
        "symbol": "USOILm",
        "direction": "BUY",
        "volume_lots": 0.01,
        "quantity": 10.0,
        "price_open": 84.0,
        "price_current": 84.5,
        "stop_loss": 83.0,
        "take_profit": 86.0,
        "profit": 5.0,
        "margin_required": 0.42,
        "notional_usd": 845.0,
        "time": 123,
    }]


def test_exness_demo_order_uses_order_check_and_order_send():
    Tick = namedtuple("Tick", "bid ask last time time_msc")
    Info = namedtuple("Info", "trade_contract_size volume_min volume_max volume_step")
    Account = namedtuple("Account", "login trade_mode")
    Result = namedtuple("Result", "retcode comment order deal price volume")

    class FakeMT5:
        TRADE_ACTION_DEAL = 1
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        ORDER_TIME_GTC = 0
        ORDER_FILLING_IOC = 1
        ACCOUNT_TRADE_MODE_DEMO = 0

        def __init__(self):
            self.checked = None
            self.sent = None

        def initialize(self, **kwargs):
            return True

        def account_info(self):
            return Account(login=12345678, trade_mode=0)

        def symbol_select(self, symbol, enabled):
            self.selected = (symbol, enabled)
            return True

        def symbol_info_tick(self, symbol):
            return Tick(bid=2301.25, ask=2301.55, last=2301.40, time=1, time_msc=1000)

        def symbol_info(self, symbol):
            return Info(trade_contract_size=100.0, volume_min=0.01, volume_max=50.0, volume_step=0.01)

        def order_check(self, request):
            self.checked = request.copy()
            return SimpleNamespace(retcode=0, comment="OK")

        def order_send(self, request):
            self.sent = request.copy()
            return Result(retcode=10009, comment="Done", order=11, deal=22, price=request["price"], volume=request["volume"])

        def order_calc_margin(self, order_type, symbol, volume, price):
            return 0.58

        def last_error(self):
            return (0, "OK")

        def shutdown(self):
            return True

    fake = FakeMT5()
    config = ExnessMT5Config(
        login=12345678,
        password="secret-password",
        server="Exness-MT5Trial",
        terminal_path="",
        symbols=("XAUUSDm",),
        symbol_map={"xauusdm": "XAUUSDm"},
        enable_demo_trading=True,
        allow_min_volume_round_up=True,
        max_order_volume=0.01,
        deviation_points=20,
        magic=260831,
    )
    broker = ExnessMT5ReadOnlyBroker(config=config, mt5_module=fake)
    order = SimpleNamespace(
        symbol="xauusdm",
        direction="BUY",
        quantity=0.001,
        stop_loss=2200.0,
        take_profit=2400.0,
        risk_amount_usd=200.0,
    )

    result = broker.submit_market_order(order)

    assert result["ok"] is True
    assert fake.checked["symbol"] == "XAUUSDm"
    assert fake.sent["volume"] == 0.01
    assert result["fill_price"] == 2301.55
    assert result["fill_quantity"] == 1.0
    assert result["notional_usd"] == 2301.55
    assert result["margin_required"] == 0.58
    assert result["position_size_usd"] == 0.58


def test_exness_demo_order_rejects_when_min_lot_exceeds_approved_risk():
    Tick = namedtuple("Tick", "bid ask last time time_msc")
    Info = namedtuple("Info", "trade_contract_size volume_min volume_max volume_step")
    Account = namedtuple("Account", "login trade_mode")

    class FakeMT5:
        TRADE_ACTION_DEAL = 1
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        ORDER_TIME_GTC = 0
        ORDER_FILLING_IOC = 1
        ACCOUNT_TRADE_MODE_DEMO = 0

        def initialize(self, **kwargs):
            return True

        def account_info(self):
            return Account(login=12345678, trade_mode=0)

        def symbol_select(self, symbol, enabled):
            return True

        def symbol_info_tick(self, symbol):
            return Tick(bid=1.15989, ask=1.15997, last=0.0, time=1, time_msc=1000)

        def symbol_info(self, symbol):
            return Info(trade_contract_size=100000.0, volume_min=0.01, volume_max=50.0, volume_step=0.01)

        def order_calc_margin(self, order_type, symbol, volume, price):
            return 0.58

        def last_error(self):
            return (0, "OK")

    config = ExnessMT5Config(
        login=12345678,
        password="secret-password",
        server="Exness-MT5Trial",
        terminal_path="",
        symbols=("EURUSDm",),
        symbol_map={},
        enable_demo_trading=True,
        allow_min_volume_round_up=True,
        max_order_volume=0.01,
        max_order_risk_usd=2.0,
        deviation_points=20,
        magic=260831,
    )
    broker = ExnessMT5ReadOnlyBroker(config=config, mt5_module=FakeMT5())
    order = SimpleNamespace(
        symbol="EURUSDm",
        direction="BUY",
        quantity=4.31,
        stop_loss=1.1251,
        take_profit=1.2121,
        risk_amount_usd=2.0,
    )

    result = broker.submit_market_order(order)

    assert result["ok"] is False
    assert "exceeds approved risk" in result["reason"]
    assert result["volume_lots"] == 0.01
    assert round(result["actual_risk_usd"], 2) > 2.0


def test_exness_can_modify_demo_position_levels():
    Position = namedtuple("Position", "ticket symbol type volume price_open price_current sl tp profit")
    Account = namedtuple("Account", "login trade_mode")

    class FakeMT5:
        TRADE_ACTION_SLTP = 6
        POSITION_TYPE_BUY = 0
        ACCOUNT_TRADE_MODE_DEMO = 0

        def initialize(self, **kwargs):
            return True

        def account_info(self):
            return Account(login=12345678, trade_mode=0)

        def positions_get(self):
            return (Position(123, "EURUSDm", 0, 0.01, 1.1589, 1.1589, 1.1585, 1.1594, 0.0),)

        def order_send(self, request):
            self.sent = request.copy()
            return SimpleNamespace(retcode=10009, comment="Done")

        def last_error(self):
            return (0, "OK")

    fake = FakeMT5()
    config = ExnessMT5Config(
        login=12345678,
        password="secret-password",
        server="Exness-MT5Trial",
        terminal_path="",
        symbols=("EURUSDm",),
        symbol_map={"eurusd": "EURUSDm", "eurusdm": "EURUSDm"},
        enable_demo_trading=True,
        max_order_volume=0.01,
        deviation_points=20,
        magic=260831,
    )
    broker = ExnessMT5ReadOnlyBroker(config=config, mt5_module=fake)

    result = broker.modify_position_levels(
        symbol="EURUSD",
        direction="BUY",
        stop_loss=1.1584,
        take_profit=1.16,
    )

    assert result["ok"] is True
    assert fake.sent["action"] == 6
    assert fake.sent["position"] == 123
    assert fake.sent["symbol"] == "EURUSDm"
    assert fake.sent["sl"] == 1.1584
    assert fake.sent["tp"] == 1.16


def test_exness_order_rejects_when_demo_trading_disabled():
    class FakeMT5:
        ACCOUNT_TRADE_MODE_DEMO = 0

        def initialize(self, **kwargs):
            return True

        def account_info(self):
            return {"login": 12345678, "trade_mode": 0}

        def last_error(self):
            return (0, "OK")

    config = ExnessMT5Config(
        login=12345678,
        password="secret-password",
        server="Exness-MT5Trial",
        terminal_path="",
        symbols=("XAUUSDm",),
        symbol_map={},
        enable_demo_trading=False,
        allow_min_volume_round_up=False,
        max_order_volume=0.01,
        deviation_points=20,
        magic=260831,
    )
    broker = ExnessMT5ReadOnlyBroker(config=config, mt5_module=FakeMT5())
    order = SimpleNamespace(symbol="XAUUSDm", direction="BUY", quantity=1.0)

    result = broker.submit_market_order(order)

    assert result["ok"] is False
    assert "EXNESS_ENABLE_DEMO_TRADING" in result["reason"]
