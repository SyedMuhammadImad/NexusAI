"""Bounded source/runtime feasibility audit; forecasts can never become real bars."""
import hashlib
import importlib.util
import json
from pathlib import Path
import urllib.request
import zipfile

from .market_data import Candle,digest
from .p8_evidence import stamp

REPOSITORY='https://github.com/shiyu-coder/Kronos'
CHECKPOINT='https://huggingface.co/NeoQuasar/Kronos-mini'


def public_json(url):
    # Explicit anonymous opener; no netrc, HuggingFace cache or environment token.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(url,headers={'User-Agent':'NexusAI-P8-anonymous-research'}),timeout=20) as response:
        body=response.read(4*1024*1024+1)
    if len(body)>4*1024*1024: raise ValueError('Metadata response too large')
    return json.loads(body)


def probe_torch():
    try:
        __import__('torch')
        return 'SUCCEEDED'
    except ImportError as e:
        return type(e).__name__


def context_view(view,*,as_of,horizon=1):
    if not isinstance(horizon,int) or isinstance(horizon,bool) or not 1<=horizon<=24:
        raise ValueError('Bounded forecast horizon required')
    t=stamp(as_of); bars=[Candle.model_validate(c) for c in view['candles']]
    if not bars or len(bars)>2048 or any(b.closed>t for b in bars):
        raise ValueError('Non-empty bounded completed context required')
    if any(a.closed>b.opened for a,b in zip(bars,bars[1:])):
        raise ValueError('Ordered nonoverlapping context required')
    if len({(b.provider,b.instrument,b.timeframe) for b in bars})!=1:
        raise ValueError('Mixed context identity')
    data=dict(dataset_id=view['dataset_id'],qualification_id=view['qualification_id'],
        instrument=bars[0].instrument,timeframe=bars[0].timeframe,as_of=t.isoformat(),
        horizon=horizon,rows=[dict(timestamp=b.opened.isoformat(),available_at=b.closed.isoformat(),
            **{k:str(getattr(b,k)) for k in ('open','high','low','close')},volume=None,amount=None) for b in bars],
        volume_assumption='UNKNOWN retained; any runtime zero imputation must be experiment-only',
        price_basis='BID; separate ask retained by canonical dataset',execution_eligible=False)
    return dict(context_id=digest(data),**data)


def audit_runtime(*,network=True):
    source=Path(__file__).resolve().parents[4]/'kronos/Kronos-master.zip'
    result=dict(track='KRONOS',status='KRONOS_RUNTIME_BLOCKED',runtime='BLOCKED',
        repository=REPOSITORY,checkpoint=CHECKPOINT,checkpoint_loaded=False,
        evaluation='NOT_RUN',baseline_comparison='NOT_RUN',added_value='BLOCKED',execution_eligible=False,
        source_commit='UNKNOWN; ZIP has no Git provenance',dependencies={},metadata={},
        hardware='CPU fallback supported by source; actual inference performance unmeasured',
        input='OHLC + optional volume/amount; separate input/future calendar timestamps',
        context='mini 2048 with 2k tokenizer; small/base 512',horizon=1,
        preprocessing='per-context mean/std; float32; clipping=5; epsilon=1e-5',
        output='sampled forecast OHLCVA; not broker observations or qualified source candles')
    if source.is_file():
        body=source.read_bytes(); result['source_archive_sha256']=hashlib.sha256(body).hexdigest()
        with zipfile.ZipFile(source) as z:
            names=z.namelist(); result['archive_checkpoint_count']=sum(n.endswith(('.pt','.pth','.safetensors','.bin')) for n in names)
            for member in ('requirements.txt','model/kronos.py','README.md'):
                key=next((n for n in names if n.endswith('/'+member)),None)
                if key:
                    raw=z.read(key); result.setdefault('source_files',{})[member]=hashlib.sha256(raw).hexdigest()
                    if member=='requirements.txt': result['source_requirements']=raw.decode().splitlines()
    missing=[]
    for name in ('torch','pandas','einops','huggingface_hub','safetensors'):
        available=importlib.util.find_spec(name) is not None
        result['dependencies'][name]='PRESENT' if available else 'MISSING'
        if not available: missing.append(name)
    result['torch_import']=probe_torch()
    if network:
        for key,url in (
            ('torch','https://pypi.org/pypi/torch/json'),
            ('pandas_pin','https://pypi.org/pypi/pandas/2.2.2/json'),
            ('numpy_312_candidate','https://pypi.org/pypi/numpy/1.26.4/json'),
            ('checkpoint','https://huggingface.co/api/models/NeoQuasar/Kronos-mini?blobs=true')):
            try:
                meta=public_json(url)
                if key=='checkpoint':
                    result['metadata'][key]=dict(url=url,revision=meta.get('sha'),
                        files=[dict(name=s['rfilename'],size=s.get('size') or s.get('lfs',{}).get('size')) for s in meta.get('siblings',[])])
                else:
                    wheels=[dict(name=f['filename'],bytes=f['size'],sha256=f['digests']['sha256'])
                            for f in meta.get('urls',[]) if 'win_amd64' in f['filename'] and 'cp314' in f['filename']]
                    result['metadata'][key]=dict(url=url,version=meta['info']['version'],windows_cp314_wheels=wheels)
                    result['metadata'][key]['windows_cp312_wheels']=[
                        dict(name=f['filename'],bytes=f['size'],sha256=f['digests']['sha256'])
                        for f in meta.get('urls',[]) if '-cp312-cp312-win_amd64.whl' in f['filename']]
            except (OSError,ValueError,KeyError) as e:
                result['metadata'][key]=dict(url=url,status='UNAVAILABLE',error=type(e).__name__)
    result['blockers']=['Missing runtime modules: '+', '.join(missing),
        'No checkpoint in inspected source archive; no compatible isolated runtime/checkpoint pair loaded']
    pin=result['metadata'].get('pandas_pin',{})
    if 'windows_cp314_wheels' in pin and not pin['windows_cp314_wheels']:
        result['blockers'].append('Source pandas==2.2.2 pin has no Windows CPython 3.14 wheel; do not compile or alter working backend')
    wheels=result['metadata'].get('torch',{}).get('windows_cp314_wheels',[])
    result['optional_dependency_download_budget_bytes']=128*1024*1024
    result['budget_scope']='Optional isolated Kronos dependency stack; no working backend or bundled runtime mutation'
    if wheels and min(w['bytes'] for w in wheels)>result['optional_dependency_download_budget_bytes']:
        result['blockers'].append('Torch wheel alone exceeds bounded 128 MiB optional dependency budget; isolated runtime deferred')
    alternative=[result['metadata'].get(k,{}).get('windows_cp312_wheels',[]) for k in ('torch','pandas_pin','numpy_312_candidate')]
    if all(alternative):
        total=sum(min(w['bytes'] for w in group) for group in alternative)
        result['alternative_python312_core_dependency_bytes']=total
        if total>result['optional_dependency_download_budget_bytes']:
            result['blockers'].append('Isolated CPython 3.12 torch+pandas+numpy wheels exceed 128 MiB bounded optional dependency budget before remaining dependencies/checkpoints')
    result['installation']='NONE; no backend dependency pins changed; no checkpoint download'
    result['evidence_id']=digest(result)
    return result
