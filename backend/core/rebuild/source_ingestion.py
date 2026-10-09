"""Authenticated-adapter domain service; canonical persistence, never dispatch."""
from datetime import datetime, timezone
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ledger import canonical, hashed
from .lifecycle_contracts import SourceEvent, SourceType
from .lifecycle_service import LifecycleService
from .source_registry import active, install, rule_for, check_signal


class SignalFields(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,allow_inf_nan=False)
    instrument: str=Field(min_length=1,max_length=32)
    direction: Literal['BUY','SELL']
    entry_type: Literal['MARKET','LIMIT']
    entry: float | None=Field(default=None,gt=0)
    stop_loss: float=Field(gt=0)
    take_profit: tuple[float,...]=Field(min_length=1,max_length=3)
    requested_risk_pct: float | None=Field(default=None,gt=0,le=100)

    @model_validator(mode='after')
    def geometry(self):
        if self.entry_type=='LIMIT' and self.entry is None: raise ValueError('LIMIT requires entry')
        for tp in self.take_profit:
            if tp<=0 or not (self.stop_loss<tp if self.direction=='BUY' else tp<self.stop_loss):
                raise ValueError('Invalid geometry')
            if self.entry is not None and not (self.stop_loss<self.entry<tp if self.direction=='BUY' else tp<self.entry<self.stop_loss):
                raise ValueError('Invalid geometry')
        return self

    def text(self):
        label='Entry' if self.entry_type=='LIMIT' else 'Current rate'
        entry=f'{label}: {self.entry}' if self.entry is not None else 'MARKET'
        lines=[self.instrument,self.direction,entry,f'Stoploss: {self.stop_loss}']
        lines += [f'TP{i}: {v}' for i,v in enumerate(self.take_profit,1)]
        if self.requested_risk_pct is not None: lines.append(f'Risk: {self.requested_risk_pct}%')
        return '\n'.join(lines)


class SourceSubmission(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,allow_inf_nan=False)
    source_type: SourceType
    source_id: str=Field(min_length=1,max_length=256)
    message_id: str=Field(min_length=1,max_length=256)
    original_timestamp: str=Field(min_length=1,max_length=256)
    timezone_evidence: str=Field(min_length=1,max_length=256)
    provenance: dict[str,str]=Field(min_length=1,max_length=20)
    sender_id: str=Field(default='',max_length=256)
    group_id: str | None=Field(default=None,max_length=256)
    raw_text: str | None=Field(default=None,min_length=1,max_length=16000)
    signal: SignalFields | None=None
    strategy_id: str | None=Field(default=None,min_length=1,max_length=128)
    strategy_version: str | None=Field(default=None,min_length=1,max_length=128)
    evidence_ref: str | None=Field(default=None,min_length=1,max_length=1024)

    @model_validator(mode='after')
    def source_fields(self):
        reserved={'group_id','strategy_id','strategy_version','evidence_ref','p4_input_hash','adapter_version','parser_version','registry_revision','structured_input'}
        if reserved & self.provenance.keys(): raise ValueError('Reserved provenance keys')
        if any(not k.strip() or not v.strip() for k,v in self.provenance.items()):
            raise ValueError('Empty provenance')
        if any(v is not None and not v.strip() for v in (self.group_id,self.strategy_id,self.strategy_version,self.evidence_ref)):
            raise ValueError('Empty source evidence')
        if self.source_type in {'MANUAL','NEXUSAI_STRATEGY'} and self.signal is None:
            raise ValueError('Structured signal required')
        if self.source_type in {'WHATSAPP_HUMAN','HISTORICAL_WHATSAPP'} and (self.raw_text is None or self.signal is not None):
            raise ValueError('Raw message required; parsed overrides forbidden')
        if self.source_type=='WHATSAPP_HUMAN' and (not self.sender_id or not self.group_id):
            raise ValueError('Sender/group required')
        if self.source_type=='NEXUSAI_STRATEGY' and (not self.strategy_id or not self.strategy_version):
            raise ValueError('Strategy identity/version required')
        if self.source_type=='SCREENSHOT' and not self.evidence_ref: raise ValueError('Evidence reference required')
        if self.raw_text and self.signal: raise ValueError('Conflicting raw/structured inputs')
        return self


def normalize_time(original,evidence):
    try:
        stamp=datetime.fromisoformat(original.replace('Z','+00:00'))
        if stamp.tzinfo is None or stamp.utcoffset() is None: return None
        offset=stamp.strftime('%z')
        offset=offset[:3]+':'+offset[3:]
        if evidence not in {offset,'ISO_OFFSET'} and not (evidence in {'UTC','Z'} and offset=='+00:00'):
            return None
        return stamp.astimezone(timezone.utc)
    except (ValueError,OverflowError):
        return None


class SourceIngestion:
    def __init__(self,ledger,configuration,*,clock=None):
        install(ledger,configuration)
        self.ledger=ledger
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.lifecycle=LifecycleService(ledger,p2=True)

    def ingest(self,submission):
        s=SourceSubmission.model_validate(submission.model_dump())
        current=self.clock()
        identity=hashed(['p4',s.source_type,s.source_id,s.message_id])
        digest=hashed(s.model_dump(mode='json'))
        metadata=dict(s.provenance,p4_input_hash=digest,adapter_version='p4-v1',parser_version='deterministic_v3_p2')
        for key in ('group_id','strategy_id','strategy_version','evidence_ref'):
            if getattr(s,key) is not None: metadata[key]=getattr(s,key)
        if s.signal: metadata['structured_input']=canonical(s.signal.model_dump(mode='json'))
        raw=s.signal.text() if s.signal else s.raw_text or 'Unparsed screenshot evidence'
        with self.ledger.connect() as conn:
            config=active(conn)
            previous=conn.execute('SELECT payload FROM source_events WHERE source_event_id=?',(identity,)).fetchone()
        metadata['registry_revision']=str(config.revision)
        if previous:
            event=SourceEvent.model_validate_json(previous[0])
            if event.metadata.get('p4_input_hash')!=digest: raise ValueError('P4_REPLAY_CONFLICT')
        else:
            event=SourceEvent(source_event_id=identity,source_type=s.source_type,source_id=s.source_id,
                source_message_id=s.message_id,sender_id=s.sender_id,raw_text=raw,metadata=metadata,
                original_timestamp=s.original_timestamp,timezone_evidence=s.timezone_evidence,
                source_time_utc=normalize_time(s.original_timestamp,s.timezone_evidence),received_at=current)
        with self.ledger.connect() as conn:
            rule_for(conn,event)
        self.lifecycle.save_source(event)
        result=dict(source_event_id=identity,signal_id=None,status='REVIEW_REQUIRED',
                    execution_eligibility='NONE',broker_execution='HARD_DISABLED',execution_enabled=False)
        if event.source_time_utc is None:
            return dict(result,reason='TIME_UNRESOLVED')
        try:
            signal=self.lifecycle.validate_source(identity)
        except ValueError:
            return dict(result,reason='PARSER_REJECTED')
        result.update(signal_id=signal['signal_id'],status='VALIDATED')
        try:
            with self.ledger.connect() as conn:
                check_signal(conn,signal['signal_id'],current=current)
            result['execution_eligibility']='P2_ONLY'
        except ValueError:
            result['reason']='RESEARCH_ONLY_OR_EXPIRED'
        return result
