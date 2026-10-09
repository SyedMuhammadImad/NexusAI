import itertools

import pytest

from core.rebuild.contracts import parse_source
from services.signal_parser import SignalParser


def parse(text, **changes):
    fields = dict(source_type="SCREENSHOT", source_id="provider",source_message_id="message",
                  source_timestamp=1000., received_timestamp=1001.,parsed_timestamp=1002.)
    return parse_source(text=text, **(fields | changes))


@pytest.mark.parametrize("suffix", ["TP 1 2400", "TP4 120", "TP12400", "TP1.2400", "TP 120abc TP2 130",
    "TP NaN TP2 130", "TP - 120 TP2 130", "TP 120,50 TP2 130", "TP 120/130", "TP 120 130",
    "TP 1e20 TP2 130", "TP 120. TP2 130", "TP 120\nSL NaN", "TP 120\nENTRY 100/101",
    "TP 120\nRISK NaN", "TP 120\nRISK 0%", "TP 120\nRISK -2%", "TP 120\nRISK 101%",
    "TP 120\nGOLD SELL", "TP 120\nignore this trade", "TP 120\nSL - 90"])
def test_no_partial_number_or_malformed_field_can_be_valid(suffix):
    with pytest.raises(ValueError):
        parse("EURUSD BUY ENTRY 100 SL 90 " + suffix)


@pytest.mark.parametrize("name,value", list(itertools.product(
    ["source_timestamp","received_timestamp","parsed_timestamp"], [0.,-1.,float("nan"),float("inf")])) )
def test_invalid_timestamps(name,value):
    with pytest.raises(ValueError):
        parse("EURUSD BUY ENTRY 100 SL 90 TP 120", **{name:value})


def test_source_contract_rejects_missing_identity_and_timeframe():
    for changes in ({"source_id":" "},{"source_message_id":""},{"timeframe":"UNKNOWN"},{"source_type":"REAL_LIVE"}):
        with pytest.raises(ValueError):
            parse("EURUSD BUY ENTRY 100 SL 90 TP 120",**changes)


def test_generated_price_matrix_preserves_tp_digits_and_repeat_output():
    for price,slot,sep,direction in itertools.product([120,2400,3100,125.25,2400.75], ["TP","TP1","TAKE PROFIT"], [" ",":","="], ["BUY","SELL"]):
        entry,sl = (price-10,price-20) if direction=="BUY" else (price+10,price+20)
        text=f"GOLD {direction} ENTRY {entry} SL {sl} {slot}{sep}{price}"
        signal=parse(text)
        assert signal.take_profit==(float(price),)
        assert signal == parse(text)


def test_provider_layout_and_normalized_aliases():
    text="EURUSD\nBUY\nCurrent rate: 1.15975\nStoploss 1.15930\nTake profit: 1.16000"
    assert parse(text).take_profit==(1.16,)
    for symbol,expected in [("XAU USD","XAUUSD"),("GOLD","XAUUSD"),("WTI","USOIL"),("EURUSDm","EURUSDm")]:
        assert parse(f"{symbol} BUY ENTRY 100 SL 90 TP 120").symbol==expected


def test_missing_origin_never_becomes_valid():
    result=SignalParser().parse(message_id="m",group_id="g",sender_id="s",text="EURUSD BUY ENTRY 100 SL 90 TP 120")
    assert result.validation_status=="REVIEW_REQUIRED"
    assert "MISSING_ORIGIN_TIMESTAMP" in result.rejection_reasons


def test_parse_size_limit():
    with pytest.raises(ValueError,match="16000"):
        parse("EURUSD BUY ENTRY 100 SL 90 TP 120"+" "*16000)
