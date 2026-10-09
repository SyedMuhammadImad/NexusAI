"""Descriptive real-data diagnostics; does not qualify or repair observations."""
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
import json
import hashlib
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core.rebuild.market_data import MarketStore, UTC, digest
from core.rebuild.export_research import ExportResearch, kronos_rows
from core.rebuild.research_reader import ResearchDatasetReader
from core.rebuild.provider_comparison import compare
from core.rebuild.evtl_provider import EVTLProvider, read_json


def verify_raw(data, store):
    """Reparse every saved source; never rely on the normalized rows alone."""
    records=[]
    for receipt in data['provenance']:
        provenance=json.loads(receipt['provenance'])
        with store.connect() as c:
            raw=bytes(c.execute('SELECT body FROM raw WHERE id=?',(receipt['raw_id'],)).fetchone()[0])
        assert hashlib.sha256(raw).hexdigest()==receipt['raw_id']
        parts=[]; offset=0
        while offset<len(raw):
            assert offset+8<=len(raw)
            length=int.from_bytes(raw[offset:offset+8],'big'); offset+=8
            assert 0<length<=len(raw)-offset
            parts.append(raw[offset:offset+length]); offset+=length
        assert hashlib.sha256(parts[0]).hexdigest()==provenance['catalogue_sha256']
        entries=read_json(parts[0])['files']
        assert len(parts)==len(provenance['responses'])+1
        rows=[]
        for part,response in zip(parts[1:],provenance['responses']):
            entry=response['catalogue_entry']
            assert entry in entries and len(part)==entry['bytes']
            assert hashlib.sha256(part).hexdigest()==response['sha256']
            parsed=EVTLProvider().normalize(part,data['manifest']['instrument'],data['manifest']['timeframe'],entry['year'])
            assert len(parsed)==entry['bars']==response['raw_observation_count']
            assert min(int(x.opened.timestamp()) for x in parsed)==entry['first']
            assert max(int(x.opened.timestamp()) for x in parsed)==entry['last']
            rows.extend(x.payload() for x in parsed)
            records.append(dict(url=response['url'],sha256=response['sha256'],bytes=len(part),
                                raw_observations=len(parsed),ingested_at=receipt['ingested_at']))
        assert digest(sorted(rows,key=lambda x:x['opened']))==data['manifest']['content_hash']
    return records

IDS = {
    'XAUUSD': ('fbc58e02da92f01faf51d03b62515b06f1fc5f3a7b8c5bcfa0c0605f6674220e',
               'c475e55d548f51300bbd4fe5ab502d2bcbc2f9ac606a317513ac38bc66198918'),
    'XAGUSD': ('1f4d67a2ed1f7db36a60577d51f6203fe17b4ea8230113dfc1705782a6a6a908',
               '827f905b9a22a76cb0635c73c9b3c22a41c435c4c6c826dc8b40dabf9933f8b6'),
    'USOIL': ('1889257a8e67cf363dd2bdd67ee25ff9482b227ec2c89e13c30d2bbadd317d70',
              'e1c28463fcdc28055fd2ef203f8297c8e853ccf7f6c196bf331c261f13069612'),
}
store = MarketStore()
qualifier = ExportResearch(store)
reader = ResearchDatasetReader(store)
HISTDATA = dict(XAUUSD='c254adbcd70038ee533d04ea01486eb0620af2a6826f1b0e231146a627b106d7',
    XAGUSD='a596229b6024ae23313e703177fa054946b6fa4e0f08a9721847781b4410787b',
    USOIL='fb1ff343f833a36a73cd9af75cf4268ac17336c0b2843dd4b593278c93b1efbe')
report = {'provider':'EV_TRADING_LABS','qualified':False,'instruments':{}}
for symbol, ids in IDS.items():
    h1,h4 = [store.query(i,research=False) for i in ids]
    bars = {datetime.fromisoformat(c['opened']):c for c in h1['candles']}
    matched,mismatches,partial = 0,[],[]
    for c in h4['candles']:
        t = datetime.fromisoformat(c['opened'])
        children = [bars[t+timedelta(hours=i)] for i in range(4) if t+timedelta(hours=i) in bars]
        if len(children)!=4: partial.append(dict(at=t.isoformat(),hours=len(children)))
        if not children:
            mismatches.append(dict(at=t.isoformat(),reason='NO_H1_CHILDREN')); continue
        for side in ('BID','ASK'):
            rows = children if side=='BID' else [x['ask_ohlc'] for x in children]
            expected = dict(open=Decimal(rows[0]['open']),high=max(Decimal(x['high']) for x in rows),
                            low=min(Decimal(x['low']) for x in rows),close=Decimal(rows[-1]['close']))
            actual = c if side=='BID' else c['ask_ohlc']
            if any(Decimal(actual[k])!=v for k,v in expected.items()):
                mismatches.append(dict(at=t.isoformat(),side=side,reason='OHLC_MISMATCH'))
        matched+=1
    r = dict(dataset_ids=ids,counts=[len(h1['candles']),len(h4['candles'])],
             issues=Counter(i['kind'] for i in h1['manifest']['issues']),
             gap_patterns=Counter(),gap_examples={},h4_ohlc_mismatches=mismatches,
             h4_partial_hours=partial,h4_compared=matched,
             yearly=Counter(datetime.fromisoformat(c['opened']).year for c in h1['candles']))
    for g in h1['manifest']['gaps']:
        t=datetime.fromisoformat(g['start'])
        key=f"{t.strftime('%a %H')} {g['missing_count']}h"
        r['gap_patterns'][key]+=1
        r['gap_examples'].setdefault(key,[])
        if len(r['gap_examples'][key])<3: r['gap_examples'][key].append(g['start'])
    report['instruments'][symbol]=r
    print(symbol,json.dumps({k:v for k,v in r.items() if k not in ('h4_partial_hours','gap_examples','h4_ohlc_mismatches')}),flush=True)
    print('OHLC mismatches',len(mismatches),'examples',mismatches[:3],flush=True)
    r['qualifications']=[]
    r['raw_replay']=[dict(dataset_id=d['dataset_id'],sources=verify_raw(d,store)) for d in (h1,h4)]
    for identity in ids:
        q=qualifier.qualify(identity,hourly_dataset=ids[0])
        assert qualifier.qualify(identity,hourly_dataset=ids[0])==q
        result=dict(q)
        if q['state'].startswith('QUALIFIED'):
            segment=q['longest_range']
            a,b=datetime.fromisoformat(segment['start']),datetime.fromisoformat(segment['end'])
            view=reader.query(q['qualification_id'],start=a,end=b)
            reopened=ResearchDatasetReader(MarketStore(store.root)).query(q['qualification_id'],start=a,end=b)
            assert view==reopened
            converted=kronos_rows(view,as_of=b)
            result['verified_query_bars']=len(view['candles'])
            result['kronos_contract']=dict(row_hash=converted['row_hash'],rows=len(converted['rows']),
                                          volume_kind=converted['volume_kind'],runtime='NOT_RUN')
        r['qualifications'].append(result)
        print('QUALIFICATION',symbol,q['state'],q['longest_range'],'conflicts',len(q['conflicts']),flush=True)
    r['comparison']=compare(h1,store.query(HISTDATA[symbol],research=False))
    print('COMPARISON',json.dumps(r['comparison']),flush=True)
report['report_id']=digest(report)
path=store.root/('alternative-audit-'+report['report_id']+'.json')
path.write_text(json.dumps(report,indent=2),encoding='utf-8',newline='\n')
print(path,flush=True)
