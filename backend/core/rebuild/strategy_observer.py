"""Restart-safe CLOSED broker-bar observer. No execution adapter or secret access."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import json
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .ledger import canonical, hashed
from .operations import STRATEGY_IDS
from .research_strategies import Features, catalogue
from .safety_contracts import Positive, Nonnegative
from .source_ingestion import SourceSubmission, SignalFields

VERSION = 'v1-closed-broker-bars-v1'
MAPPINGS = {'XAUUSD':'XAUUSDm','XAGUSD':'XAGUSDm','USOIL':'USOILm'}


class BrokerCandle(BaseModel):
    model_config = ConfigDict(extra='forbid',frozen=True,allow_inf_nan=False)
    provider: Literal['FIXTURE','MT5_DEMO']
    account_key: str = Field(min_length=1)
    broker_symbol: str
    instrument: Literal['XAUUSD','XAGUSD','USOIL']
    timeframe: Literal['1H','4H']
    opened: AwareDatetime
    closed: AwareDatetime
    open: Positive
    high: Positive
    low: Positive
    close: Positive
    volume: Nonnegative
    price_basis: Literal['BID'] = 'BID'
    volume_unit: Literal['TICK_COUNT'] = 'TICK_COUNT'
    source_ref: str = Field(min_length=1)
    raw_native: dict = Field(default_factory=dict)
    read_evidence_ref: str = Field(default='FIXTURE_NOT_BROKER_ATTESTED',min_length=1)

    @model_validator(mode='after')
    def valid_bar(self):
        hours = 1 if self.timeframe == '1H' else 4
        if (self.opened.utcoffset()!=timedelta(0) or self.closed.utcoffset()!=timedelta(0)
                or self.opened.minute or self.opened.second or self.opened.microsecond
                or self.opened.hour % hours or self.closed-self.opened!=timedelta(hours=hours)):
            raise ValueError('BROKER_BAR_UTC_ALIGNMENT_REQUIRED')
        if (self.low>min(self.open,self.close) or self.high<max(self.open,self.close)
                or self.low>self.high or self.volume!=self.volume.to_integral_value()
                or MAPPINGS[self.instrument]!=self.broker_symbol):
            raise ValueError('INVALID_BROKER_BAR_OR_MAPPING')
        if self.provider=='MT5_DEMO' and not self.raw_native:
            raise ValueError('NATIVE_BAR_EVIDENCE_REQUIRED')
        return self


def normalize_closed_rates(rows, *, account, symbol, timeframe, current, chart_basis, evidence_ref):
    """Pure native-rate parser. BID basis must be independently evidenced by caller."""
    if current.tzinfo is None or chart_basis!='BID' or timeframe not in {'1H','4H'} or not evidence_ref:
        raise ValueError('BROKER_BAR_SEMANTICS_UNPROVEN')
    mapping = {v:k for k,v in MAPPINGS.items()}
    if symbol not in mapping or rows is None: raise ValueError('BROKER_BAR_SERIES_UNSUPPORTED')
    bars = []
    previous_opened = None
    for row in rows:
        if not isinstance(row,dict):
            row = {name:row[name].item() for name in row.dtype.names}
        fields={'time','open','high','low','close','tick_volume','spread','real_volume'}
        if set(row)!=fields or any(type(row[k]) is not int or row[k]<0 for k in ('tick_volume','spread','real_volume')):
            raise ValueError('INVALID_NATIVE_BAR_FIELDS')
        if type(row['time']) is not int or row['time']<=0:
            raise ValueError('INVALID_NATIVE_BAR_TIME')
        opened=datetime.fromtimestamp(row['time'],timezone.utc)
        if previous_opened is not None and opened <= previous_opened:
            raise ValueError('DUPLICATE_OR_UNORDERED_BROKER_BARS')
        previous_opened = opened
        closed=opened+timedelta(hours=1 if timeframe=='1H' else 4)
        bar=BrokerCandle(provider=account.evidence_source,account_key=account.key,
            broker_symbol=symbol,instrument=mapping[symbol],timeframe=timeframe,
            opened=opened,closed=closed,**{k:row[k] for k in ('open','high','low','close')},
            volume=row['tick_volume'],source_ref=hashed([VERSION,account.key,symbol,timeframe,row]),
            raw_native=row,read_evidence_ref=evidence_ref)
        if opened>current: raise ValueError('FUTURE_BROKER_BAR')
        if closed<=current: bars.append(bar)
    if any(a.opened>=b.opened for a,b in zip(bars,bars[1:])):
        raise ValueError('DUPLICATE_OR_UNORDERED_BROKER_BARS')
    return tuple(bars)


class AttestedClosedBarReader:
    """Read-only injected native API, usable only inside the qualified operator path."""
    def __init__(self,isolation,*,clock):
        self.isolation,self.clock=isolation,clock

    def read(self,symbol,timeframe,*,count=256):
        from .mt5_evidence import record, enum
        from .safety import fresh
        i=self.isolation
        if (i.client is None or i.directory is None or i.session_id is None
                or symbol not in i.settings.symbols or timeframe not in {'1H','4H'}
                or type(count) is not int or not 1<=count<=4096):
            raise ValueError('BROKER_BAR_READ_NOT_QUALIFIED')
        account=i.settings.account
        i.require_safe(account,i.session_id,i.directory,'CLOSED_BAR_READ_START')
        attestation=i.attest_native()
        client=i.client
        info=record(client.symbol_info(symbol),('name','chart_mode'))
        if info['name']!=symbol or enum(client,info['chart_mode'],['SYMBOL_CHART_MODE_BID','SYMBOL_CHART_MODE_LAST'])!='SYMBOL_CHART_MODE_BID':
            raise ValueError('BROKER_BID_BAR_BASIS_UNPROVEN')
        native_frame=getattr(client,'TIMEFRAME_H1' if timeframe=='1H' else 'TIMEFRAME_H4')
        rates=client.copy_rates_from_pos(symbol,native_frame,0,count)
        current=self.clock()
        fresh(attestation.observed_at,current,5)
        bars=normalize_closed_rates(rates,account=account,symbol=symbol,timeframe=timeframe,
            current=current,chart_basis='BID',evidence_ref=attestation.evidence_id)
        i.require_safe(account,i.session_id,i.directory,'CLOSED_BAR_READ_FINISH')
        return bars


class StrategyObserver:
    def __init__(self,ledger,*,clock,sources=None,source_id=None):
        self.ledger,self.clock,self.sources,self.source_id=ledger,clock,sources,source_id

    def evaluate(self,deployment_id,bars):
        current=self.clock()
        if current.tzinfo is None: raise ValueError('AWARE_OBSERVATION_TIME_REQUIRED')
        current=current.astimezone(timezone.utc)
        values=tuple(BrokerCandle.model_validate(b.model_dump()) for b in bars)
        if not values: raise ValueError('CLOSED_BROKER_BARS_REQUIRED')
        if any(b.closed>current for b in values): raise ValueError('FORMING_BAR_FORBIDDEN')
        if any(a.opened>=b.opened for a,b in zip(values,values[1:])):
            raise ValueError('DUPLICATE_OR_UNORDERED_BROKER_BARS')
        with self.ledger.transaction() as conn:
            row=conn.execute('SELECT * FROM v1_deployments WHERE deployment_id=?',(deployment_id,)).fetchone()
            if row is None or row['strategy_id'] not in STRATEGY_IDS: raise ValueError('UNKNOWN_DEPLOYMENT')
            strategies={s.strategy_id:s for s in catalogue()}
            strategy=strategies[row['strategy_id']]
            if row['strategy_version']!=strategy.version: raise ValueError('FROZEN_STRATEGY_VERSION_MISMATCH')
            for b in values:
                if ((b.account_key,b.provider)!=(self.ledger.account.key,self.ledger.account.evidence_source)
                        or (b.instrument,b.timeframe)!=(row['instrument'],row['timeframe'])):
                    raise ValueError('BROKER_SERIES_IDENTITY_MISMATCH')
            prior=[]
            for r in conn.execute('SELECT event_id,payload FROM v1_deployment_events WHERE deployment_id=?',(deployment_id,)):
                payload=json.loads(r['payload'])
                if payload.get('kind')=='CLOSED_BAR_EVALUATED': prior.append(payload)
            prior.sort(key=lambda p:p['bar']['opened'])
            known={datetime.fromisoformat(p['bar']['opened']).isoformat():p for p in prior}
            combined={k:BrokerCandle.model_validate(p['bar']) for k,p in known.items()}
            new=[]
            for b in values:
                key=b.opened.isoformat(); document=b.model_dump(mode='json')
                if key in known:
                    stored=BrokerCandle.model_validate(known[key]['bar'])
                    if stored.model_dump(mode='json',exclude={'read_evidence_ref'})!=b.model_dump(mode='json',exclude={'read_evidence_ref'}):
                        raise ValueError('REVISED_BROKER_BAR_REQUIRES_REVIEW')
                elif prior and b.opened<datetime.fromisoformat(prior[-1]['bar']['opened']):
                    raise ValueError('OLDER_BROKER_BAR_REQUIRES_REVIEW')
                else:
                    combined[key]=b;new.append(key)
            features=Features();results=[]
            for key,b in sorted(combined.items()):
                gap=bool(features.bars and b.opened!=features.bars[-1].closed)
                if gap: features=Features()  # Unknown closure: reset, never fill missing observations.
                frame=features.push(b)
                if key not in new: continue
                direction=strategy.direction(frame)
                proposal=None
                if direction and frame.features.get('atr',D(0))>0:
                    sign=D(1) if direction=='BUY' else D(-1)
                    stop=b.close-sign*D(2)*frame.features['atr']
                    tp=b.close+sign*D(4)*frame.features['atr']
                    if min(stop,tp)>0:
                        proposal=SignalFields(instrument=b.broker_symbol,direction=direction,
                            entry_type='MARKET',entry=None,stop_loss=float(stop),take_profit=(float(tp),)).model_dump(mode='json')
                identity=hashed([VERSION,deployment_id,b.opened.isoformat()])
                payload=dict(kind='CLOSED_BAR_EVALUATED',version=VERSION,evaluation_id=identity,
                    strategy_id=strategy.strategy_id,strategy_version=strategy.version,
                    bar=b.model_dump(mode='json'),warmup_count=frame.count,gap_reset=gap,
                    candidate=proposal,scope=b.provider,execution_eligible=False,
                    status='CANDIDATE_RESEARCH_ONLY' if proposal else 'NO_SIGNAL')
                conn.execute('INSERT INTO v1_deployment_events VALUES(?,?,?,?)',
                    (identity,deployment_id,current.isoformat(),canonical(payload)))
                results.append(payload)
            if not results:
                # Retry may finish canonical ingestion after a crash following checkpoint commit.
                results=[known[b.opened.isoformat()] for b in values]
        routed=[]
        for result in results:
            bar=result['bar'];hours=1 if bar['timeframe']=='1H' else 4
            boundary=current.replace(minute=0,second=0,microsecond=0,hour=current.hour//hours*hours)
            if (result['candidate'] and datetime.fromisoformat(bar['closed'])==boundary
                    and self.sources is not None and self.source_id is not None):
                submission=SourceSubmission(source_type='NEXUSAI_STRATEGY',source_id=self.source_id,
                    message_id=result['evaluation_id'],original_timestamp=bar['closed'],timezone_evidence='UTC',
                    provenance={'origin':VERSION,'evaluation_id':result['evaluation_id'],
                                'broker_bar_ref':bar['source_ref'],'price_basis':'BID',
                                'source_close':bar['close'],'account_reference':bar['account_key']},
                    signal=SignalFields.model_validate(result['candidate']),
                    strategy_id=result['strategy_id'],strategy_version=result['strategy_version'],
                    evidence_ref=bar['source_ref'])
                routed.append(self.sources.ingest(submission))
        return dict(evaluations=results,canonical_candidates=routed,broker_execution='HARD_DISABLED',
                    p2_routing='BLOCKED_BY_EXISTING_RESEARCH_SOURCE_POLICY')


def scheduler_projection(conn,deployment_id):
    rows=[]
    for row in conn.execute('SELECT observed_at,payload FROM v1_deployment_events WHERE deployment_id=?',(deployment_id,)):
        value=json.loads(row['payload'])
        if value.get('kind')=='CLOSED_BAR_EVALUATED': rows.append((row['observed_at'],value))
    if not rows: return dict(last_evaluated_at=None,last_signal_id=None,scheduler_status='NOT_RUN')
    rows.sort(key=lambda v:v[1]['bar']['opened'])
    signals=[p for _,p in rows if p['candidate']]
    return dict(last_evaluated_at=rows[-1][1]['bar']['closed'],
        last_signal_id=signals[-1]['evaluation_id'] if signals else None,
        scheduler_status='OBSERVED_NON_EXECUTING',evaluation_count=len(rows),
        candle_provider=rows[-1][1]['bar']['provider'],warmup_count=rows[-1][1]['warmup_count'])
