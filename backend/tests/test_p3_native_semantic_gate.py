"""Characterize native-history compatibility gaps; NOT a native normalizer.

MetaQuotes documents BUY_CANCELED/SELL_CANCELED as revisions to an existing deal
and a separate balance adjustment. No MT5 API or operator data is used here.
"""
from copy import deepcopy
import json
import sqlite3

import pytest
from pydantic import ValidationError

from core.rebuild.execution_contracts import DealObservation
from test_p3_execution import fixture, protective_exit, reservation


@pytest.mark.parametrize('direction,sl,tp', [('BUY',90.,130.),('SELL',110.,70.)])
def test_revised_native_profit_cannot_replace_stored_deal(tmp_path,direction,sl,tp):
    ledger,_,engine,broker,request=fixture(tmp_path,direction=direction,sl=sl,tp=tp)
    assert engine.submit(request)['state']=='FILLED'
    protective_exit(broker)
    assert engine.reconcile()['status']=='RECONCILED'
    original=deepcopy(broker.deals[-1])
    assert original['profit']=='10'
    assert reservation(ledger)['state']=='RELEASED'

    # Isolate the documented PnL revision under the SAME deal ID. This is only
    # the common-field subset; no canceled native type is silently mapped to BUY.
    broker.deals[-1]['profit']='0'
    assert engine.reconcile()['status']=='RECONCILIATION_REQUIRED'
    assert engine.get(request)['state']=='SUBMISSION_AMBIGUOUS'
    assert reservation(ledger)['state']=='AMBIGUOUS'
    assert ledger.status()['halt']['state']=='HALTED'
    with ledger.connect() as conn:
        stored=json.loads(conn.execute('SELECT payload FROM p3_exit_deals WHERE broker_deal_id=?',
                                       (original['broker_deal_id'],)).fetchone()[0])
        assert stored['profit']=='10'
        evidence=json.loads(conn.execute("SELECT payload FROM quarantine WHERE reason='BROKER_RECONCILIATION_MISMATCH'").fetchone()[0])
        revised=next(d for d in evidence['evidence']['deals'] if d['broker_deal_id']==original['broker_deal_id'])
        assert revised['profit']=='0'
        assert conn.execute('SELECT lifecycle_state FROM p3_positions').fetchone()[0]=='RECOVERY_REQUIRED'
        assert conn.execute('SELECT count(*) FROM trade_outcomes').fetchone()[0]==0
    with pytest.raises(sqlite3.IntegrityError,match='Immutable protective deal'),ledger.transaction() as conn:
        conn.execute('UPDATE p3_exit_deals SET payload=? WHERE broker_deal_id=?',
                     (json.dumps(revised),original['broker_deal_id']))
    engine.submit(request)
    assert len(broker.calls)==1


@pytest.mark.parametrize('field,value',[('native_deal_type','DEAL_TYPE_BUY_CANCELED'),('broker_revision','revision-2')])
def test_current_contract_cannot_retain_native_revision_metadata(tmp_path,field,value):
    _,_,engine,broker,request=fixture(tmp_path)
    engine.submit(request)
    data=deepcopy(broker.deals[0])
    data[field]=value
    with pytest.raises(ValidationError) as caught:
        DealObservation.model_validate(data)
    assert any(error['loc']==(field,) and error['type']=='extra_forbidden' for error in caught.value.errors())


def test_balance_adjustment_is_not_a_trade_deal(tmp_path):
    _,_,engine,broker,request=fixture(tmp_path)
    engine.submit(request)
    data=deepcopy(broker.deals[0])
    data.update(volume='0',price='0',profit='-10')
    with pytest.raises(ValidationError) as caught:
        DealObservation.model_validate(data)
    assert {error['loc'][0] for error in caught.value.errors()}=={'volume','price'}
    # This rejection is safe. Assigning fake positive volume/price to make a
    # balance adjustment fit would invent an economic trade and is forbidden.
