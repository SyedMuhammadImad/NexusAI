"""Subprocess-only crash fixture; no broker imports or calls."""
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.rebuild.contracts import parse_source
from core.rebuild.ledger import BrokerDeal, BrokerOrder, BrokerPosition, DemoAccount, IntentRequest, Ledger

ACCOUNT=DemoAccount(account_id="crash-fixture",server="fixture",currency="USD",evidence_source="FIXTURE")


def populate(path, stop="none"):
    ledger=Ledger(path,account=ACCOUNT)
    signal=parse_source(text="GOLD BUY ENTRY 100 SL 90 TP 120",source_type="SCREENSHOT",source_id="g",source_message_id="m",
                        source_timestamp=1000.,received_timestamp=1001.,parsed_timestamp=1002.)
    ledger.save_signal(signal)
    if stop=="signal": os._exit(71)
    intent=ledger.create_intent(IntentRequest(client_order_id="crash-client",signal_id=signal.signal_id,action="OPEN",
        symbol="XAUUSD",direction="BUY",volume=.01,entry=100.,stop_loss=90.,take_profit=120.))
    if stop=="intent": os._exit(71)
    ledger.record_order(BrokerOrder(account_key=ACCOUNT.key,client_order_id="crash-client",broker_order_id="o1",retcode=10009,
                                   requested_volume=.01,filled_volume=.01,status="FILLED",timestamp=1003.))
    if stop=="order": os._exit(71)
    ledger.record_deal(BrokerDeal(account_key=ACCOUNT.key,broker_deal_id="d1",broker_order_id="o1",broker_position_id="p1",
        deal_type="IN",volume=.01,price=100.,profit=0.,commission=-.1,swap=0.,fee=0.,timestamp=1004.))
    if stop=="deal": os._exit(71)
    ledger.record_position(BrokerPosition(
        account_key=ACCOUNT.key,
        observation_id="snapshot-1",broker_position_id="p1",
        originating_client_order_id="crash-client",symbol="XAUUSD",direction="BUY",open_volume=.01,timestamp=1005.))
    if stop=="position": os._exit(71)
    if stop=="transaction":
        with ledger.transaction() as conn:
            conn.execute("UPDATE order_intents SET state='UNKNOWN' WHERE intent_id=?",(intent["intent_id"],))
            os._exit(71)
    return ledger


if __name__=="__main__":
    populate(Path(sys.argv[1]),sys.argv[2])
