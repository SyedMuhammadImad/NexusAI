"""Acquire closed-year public research data, never qualify downloads automatically."""
import json
from pathlib import Path
import sys
from datetime import datetime

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core.rebuild.evtl_provider import EVTLProvider, acquire
from core.rebuild.market_data import MarketStore, UTC, digest

store=MarketStore()
provider=EVTLProvider()
report={'provider':'EV_TRADING_LABS','attribution':'EV Trading Labs','datasets':[],'qualified':False}
for symbol in ('XAUUSD','XAGUSD','USOIL'):
    for frame in ('1H','4H'):
        identity=acquire(store,provider,symbol,frame,datetime(2021,1,1,tzinfo=UTC),datetime(2026,1,1,tzinfo=UTC))
        data=store.query(identity,research=False)
        report['datasets'].append({'instrument':symbol,'timeframe':frame,'dataset_id':identity,
                                   'bar_count':len(data['candles']),'gaps':data['manifest']['gaps'],
                                   'issues':data['manifest']['issues']})
        print(symbol,frame,identity,len(data['candles']),flush=True)
report['report_id']=digest(report)
path=store.root/('alternative-acquisition-'+report['report_id']+'.json')
path.write_text(json.dumps(report,indent=2),encoding='utf-8',newline='\n')
print(path,flush=True)
