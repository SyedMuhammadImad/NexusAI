"""Versioned P4 source policy. No broker, credentials, or network dependencies."""
from datetime import datetime, timezone
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from .ledger import canonical, hashed, now
from .lifecycle_contracts import SourceType, SourceEvent


class SourceRule(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    source_type: SourceType
    source_id: str=Field(min_length=1,max_length=256)
    enabled: StrictBool=True
    execution_eligibility: Literal['NONE','P2_ONLY']='NONE'
    sender_ids: frozenset[str]=frozenset()
    group_id: str | None=None
    expected_provenance: frozenset[str]=frozenset()
    freshness_seconds: int=Field(default=600,gt=0,strict=True)
    adapter_version: Literal['p4-v1']='p4-v1'
    parser_version: Literal['deterministic_v3_p2']='deterministic_v3_p2'
    qualification: Literal['UNQUALIFIED']='UNQUALIFIED'

    @model_validator(mode='after')
    def valid(self):
        if self.source_id!=self.source_id.strip(): raise ValueError('Invalid source identity')
        if self.group_id is not None and (not self.group_id.strip() or self.group_id!=self.group_id.strip() or len(self.group_id)>256):
            raise ValueError('Invalid group identity')
        if self.source_type not in {'MANUAL','WHATSAPP_HUMAN'} and self.execution_eligibility!='NONE':
            raise ValueError('Source cannot be execution eligible in P4')
        if self.source_type=='WHATSAPP_HUMAN' and (not self.sender_ids or not self.group_id):
            raise ValueError('WhatsApp requires explicit sender and group allowlists')
        if any(not s.strip() or len(s)>256 for s in self.sender_ids|self.expected_provenance):
            raise ValueError('Invalid provenance policy')
        return self


class SourceConfiguration(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    revision: int=Field(default=1,gt=0,strict=True)
    sources: tuple[SourceRule,...]=()

    @model_validator(mode='after')
    def unique(self):
        ids=[s.source_id for s in self.sources]
        if len(ids)!=len(set(ids)): raise ValueError('Source identities must be unique')
        return self


def active(conn):
    row=conn.execute('SELECT payload FROM p4_source_configuration ORDER BY revision DESC LIMIT 1').fetchone()
    return SourceConfiguration.model_validate_json(row[0]) if row else None


def install(ledger, configuration):
    config=SourceConfiguration.model_validate(configuration.model_dump())
    payload=config.model_dump(mode='json')
    for s in payload['sources']:
        for k in ('sender_ids','expected_provenance'): s[k]=sorted(s[k])
    payload['sources']=sorted(payload['sources'],key=lambda s:s['source_id'])
    digest=hashed(payload)
    with ledger.transaction() as conn:
        prior=conn.execute('SELECT * FROM p4_source_configuration ORDER BY revision DESC LIMIT 1').fetchone()
        if prior and prior['payload_hash']==digest: return
        if prior and config.revision<=prior['revision']: raise ValueError('Explicit increasing source revision required')
        if conn.execute('SELECT 1 FROM p3_attempts').fetchone():
            raise ValueError('Cannot convert an execution ledger to P4')
        conn.execute('INSERT INTO p4_source_configuration VALUES(?,?,?,?)',(config.revision,canonical(payload),digest,now()))
        ledger.audit(conn,'P4_CONFIGURATION_RECORDED',None,dict(revision=config.revision,hash=digest,broker_execution=False))


def rule_for(conn,event):
    config=active(conn)
    if config is None: return None
    rule=next((r for r in config.sources if r.source_id==event.source_id),None)
    # Existing authenticated archive bridge stays review-only without provisioning live identities.
    if rule is None and event.source_type=='HISTORICAL_WHATSAPP':
        return SourceRule(source_id=event.source_id,source_type='HISTORICAL_WHATSAPP')
    if rule is None or not rule.enabled or rule.source_type!=event.source_type:
        raise ValueError('P4_SOURCE_NOT_AUTHORIZED')
    if not rule.expected_provenance<=event.metadata.keys(): raise ValueError('P4_PROVENANCE_MISSING')
    if any(not event.metadata[k].strip() for k in rule.expected_provenance): raise ValueError('P4_PROVENANCE_MISSING')
    if rule.source_type=='WHATSAPP_HUMAN' and (event.sender_id not in rule.sender_ids or event.metadata.get('group_id')!=rule.group_id):
        raise ValueError('P4_SENDER_OR_GROUP_NOT_AUTHORIZED')
    if event.source_type=='NEXUSAI_STRATEGY' and any(not event.metadata.get(k) for k in ('strategy_id','strategy_version')):
        raise ValueError('P4_STRATEGY_IDENTITY_REQUIRED')
    if event.source_type=='SCREENSHOT' and not event.metadata.get('evidence_ref'):
        raise ValueError('P4_SCREENSHOT_REFERENCE_REQUIRED')
    if event.source_time_utc is not None and event.source_type!='HISTORICAL_WHATSAPP':
        from .source_ingestion import normalize_time
        if normalize_time(event.original_timestamp or '',event.timezone_evidence)!=event.source_time_utc:
            raise ValueError('P4_TIME_EVIDENCE_CONFLICT')
    return rule


def check_signal(conn,signal_id,*,current=None,admission=True):
    if active(conn) is None: return False
    row=conn.execute('SELECT e.payload FROM source_events e JOIN signals s ON s.source_event_id=e.source_event_id WHERE s.signal_id=?',(signal_id,)).fetchone()
    if not row: raise ValueError('P4_CANONICAL_SOURCE_REQUIRED')
    event=SourceEvent.model_validate_json(row[0])
    rule=rule_for(conn,event)
    if admission:
        if rule.execution_eligibility!='P2_ONLY' or event.source_type not in {'MANUAL','WHATSAPP_HUMAN'}:
            raise ValueError('P4_SOURCE_RESEARCH_ONLY')
        current=current or datetime.now(timezone.utc)
        if event.source_time_utc is None or not event.timezone_evidence:
            raise ValueError('P4_TIME_UNRESOLVED')
        age=(current-event.source_time_utc).total_seconds()
        if age<0 or (event.source_type=='WHATSAPP_HUMAN' and age>rule.freshness_seconds):
            raise ValueError('P4_SOURCE_EXPIRED_OR_FUTURE')
    return True
