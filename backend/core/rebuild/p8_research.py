"""Offline research orchestration. Publishes evidence only, not an active model."""
from pathlib import Path
import hashlib
import json

from .market_data import digest,encode
from .p8_evidence import ROOT,SCHEMA,SCHEMA_ID,LABEL_POLICY
from .p8_models import evaluate,POLICY
from .p8_human import audit_archive
from .p8_kronos import audit_runtime
from .p8_registry import Registry

ARCHIVE=Path('C:/Users/LOCAL_USER/.codex/codex-remote-attachments/01a02bd6-6d78-77e3-9796-f19b04942980/A7C95756-427A-42E2-817C-0D378ABFDCDC/1-WhatsApp-Chat-BUY-SELL-CALLS.zip')


def fingerprint(path):
    info=path.stat(); h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''): h.update(chunk)
    return dict(sha256=h.hexdigest(),bytes=info.st_size,mtime_ns=info.st_mtime_ns)


def run_research(rows,audit,start,end):
    path=ROOT/'research/p5-market-data/market-data.sqlite3'; before=fingerprint(path)
    print('P8_FIT_BEGIN',len(rows),flush=True)
    a,artifacts,predictions=evaluate(rows,start,end)
    repeated,again,again_predictions=evaluate(rows,start,end)
    if (a!=repeated or artifacts!=again or predictions!=again_predictions):
        raise ValueError('Research fit not exactly reproducible')
    print('P8_FIT_REPRODUCED',a['predictions_hash'],flush=True)
    b=audit_archive(ARCHIVE.read_bytes()) if ARCHIVE.is_file() else dict(
        track='HUMAN_IMITATION',status='INSUFFICIENT_DATA',result='INSUFFICIENT_DATA',
        blockers=['User-provided historical archive not present'],execution_eligible=False)
    c=audit_runtime()
    registry=Registry(); entries=[]
    for item in artifacts:
        fold=a['folds'][item['fold']]; key=item['model']; model=fold['models'][key]
        entry=dict(track='PROFITABILITY',task='resolved research WIN vs LOSS',model_type=key,
            dataset_ids=audit['dataset_ids'],dataset_rows_hash=audit['rows_hash'],
            schema_id=SCHEMA_ID,label_policy=LABEL_POLICY,train_range=[start.isoformat(),fold['cutoff']],
            validation_ranges=[],validation_policy='NO_TUNING; predeclared thresholds',
            test_ranges=[[fold['cutoff'],fold['end']]],hyperparameters=POLICY,seed=POLICY['seed'],
            metrics=model['metrics'],status='EXPERIMENTAL' if key.startswith('prior') else 'REJECTED',
            qualification_filter_status=a['filter_status'],execution_eligible=False)
        identity=registry.register(entry,item['payload']); registry.register(entry,item['payload'])
        persisted,loaded=Registry().read(identity)
        if loaded!=item['payload']: raise ValueError('Model restart/replay mismatch')
        entries.append({k:v for k,v in persisted.items() if k!='created_at'})
    for track,report,status in [('HUMAN_IMITATION',b,'INSUFFICIENT_DATA'),('KRONOS',c,'KRONOS_RUNTIME_BLOCKED')]:
        entry=dict(track=track,task='historical conditional behavior' if track=='HUMAN_IMITATION' else 'runtime feasibility',
            model_type='AUDIT_ONLY',dataset_ids=[b.get('archive_sha256')] if track=='HUMAN_IMITATION' else audit['dataset_ids'],
            schema_id='p8-human-shape-audit-v1' if track=='HUMAN_IMITATION' else 'p8-kronos-context-v1',
            label_policy='NO_PROFITABILITY_LABELS',train_range=None,validation_ranges=[],test_ranges=[],
            hyperparameters={},seed=POLICY['seed'],metrics={},status=status,execution_eligible=False)
        identity=registry.register(entry,report)
        persisted,loaded=Registry().read(identity)
        if loaded!=report: raise ValueError('Track audit registry mismatch')
        entries.append({k:v for k,v in persisted.items() if k!='created_at'})
    after=fingerprint(path)
    if before!=after: raise ValueError('P5/P6/P7 evidence store changed during P8')
    result=dict(version='p8-research-v1',status='EVALUATED_RESEARCH_ONLY',scope='RESEARCH_ONLY',
        input_audit=audit,feature_schema=SCHEMA,feature_schema_id=SCHEMA_ID,
        track_a=a,track_b=b,kronos=c,registry=entries,reproducibility='EXACT_DOUBLE_FIT',
        source_store_unchanged=before==after,source_store_sha256=before['sha256'],
        execution_eligible=False,broker_execution='UNCHANGED',live_trading='LOCKED')
    result['result_id']=digest(result)
    registry.register(dict(track='P8',task='research closeout',model_type='EVIDENCE',
        dataset_ids=audit['dataset_ids'],schema_id=SCHEMA_ID,label_policy=LABEL_POLICY,train_range=None,
        validation_ranges=[],test_ranges=[],hyperparameters=POLICY,seed=POLICY['seed'],metrics={},
        status='EXPERIMENTAL',execution_eligible=False),result)
    # Full replay arrays remain owned research artifacts, never in source-control.
    for name,value in [('labels',rows),('predictions',predictions),('result',result)]:
        target=registry.root/(name+'-'+digest(value)+'.json')
        if not target.exists(): target.write_text(encode(value),encoding='utf-8')
        if json.loads(target.read_text())!=value: raise ValueError('Replay artifact mismatch')
    target=ROOT/'knowledge/Audits/P8-RESEARCH-RESULTS.json'
    temporary=target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result,indent=2,ensure_ascii=True,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    temporary.replace(target)
    print('P8_TRACK_A',json.dumps({k:dict(metrics=v['metrics'],primary_operating_point=v['operating_points'][0])
                                  for k,v in a['summary'].items()},sort_keys=True),flush=True)
    print('P8_HUMAN_COUNTS',b.get('raw_messages'),b.get('usable_signal_shapes'),flush=True)
    print('P8_KRONOS',c['runtime'],c['blockers'],flush=True)
    return result
