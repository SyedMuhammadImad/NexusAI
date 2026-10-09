from services.signal_parser import SignalParser


def test_signal_parser_extracts_complete_market_trade():
    parsed = SignalParser().parse(
        message_id="msg-1",
        group_id="group-a",
        sender_id="sender-a",
        text="BUY EURUSDm market SL 1.1600 TP1 1.1660 risk 0.5%",
        message_timestamp=1000.0,
        received_timestamp=1005.0,
    )

    assert parsed.instrument == "EURUSDm"
    assert parsed.direction == "BUY"
    assert parsed.entry_type == "MARKET"
    assert parsed.stop_loss == 1.16
    assert parsed.take_profit_1 == 1.166
    assert parsed.requested_risk_pct == 0.5
    assert parsed.parser_confidence == 1.0
    assert parsed.signal_age == 5.0


def test_signal_parser_does_not_guess_missing_fields():
    parsed = SignalParser().parse(
        message_id="msg-2",
        group_id="group-a",
        sender_id="sender-a",
        text="Watching EURUSDm for later",
    )

    assert parsed.instrument == "EURUSDm"
    assert parsed.direction is None
    assert parsed.entry_type is None
    assert parsed.stop_loss is None
    assert parsed.primary_take_profit is None
    assert parsed.parser_confidence < 0.5


def test_signal_parser_normalizes_wti_to_usoil():
    parsed = SignalParser().parse(
        message_id="msg-3",
        group_id="group-a",
        sender_id="sender-a",
        text="short WTI market SL 79.50 TP 76.00",
    )

    assert parsed.instrument == "USOIL"
    assert parsed.direction == "SELL"


def test_signal_parser_extracts_provider_current_rate_format():
    parsed = SignalParser().parse(
        message_id="msg-4",
        group_id="group-a",
        sender_id="sender-a",
        text=(
            "EURUSD\n"
            "BUY\n"
            "Current rate: 1.15975\n\n"
            "Stoploss 1.15930\n\n"
            "Take profit: 1.16000"
        ),
        message_timestamp=1000.0,
        received_timestamp=1001.0,
    )

    assert parsed.instrument == "EURUSD"
    assert parsed.direction == "BUY"
    assert parsed.entry_type == "MARKET"
    assert parsed.entry_price == 1.15975
    assert parsed.stop_loss == 1.1593
    assert parsed.take_profit_1 == 1.16
    assert parsed.parser_confidence == 1.0


def test_signal_parser_extracts_gold_current_rate_without_price():
    parsed = SignalParser().parse(
        message_id="msg-5",
        group_id="group-a",
        sender_id="sender-a",
        text=(
            "XAU USD\n"
            "GOLD BUY\n\n"
            "Current rate buy\n\n"
            "Stoploss: 4425\n\n"
            "Take profit: 4436"
        ),
        message_timestamp=1000.0,
        received_timestamp=1001.0,
    )

    assert parsed.instrument == "XAUUSD"
    assert parsed.direction == "BUY"
    assert parsed.entry_type == "MARKET"
    assert parsed.entry_price is None
    assert parsed.stop_loss == 4425
    assert parsed.take_profit_1 == 4436
    assert parsed.parser_confidence == 1.0


def test_signal_parser_does_not_rewrite_suspicious_gold_level():
    parsed = SignalParser().parse(
        message_id="msg-6",
        group_id="group-a",
        sender_id="sender-a",
        text=(
            "XAU USD\n"
            "GOLD BUY\n\n"
            "Current rate buy\n\n"
            "Stoploss: 44250\n\n"
            "Take profit: 4436"
        ),
        message_timestamp=1000.0,
        received_timestamp=1001.0,
    )

    assert parsed.instrument == "XAUUSD"
    assert parsed.stop_loss == 44250
