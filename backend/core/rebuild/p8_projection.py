"""Lightweight P9 evidence projection. No model imports, loading or execution."""
import json
from pathlib import Path
import tempfile

from .market_data import digest

DEFAULT=Path(__file__).resolve().parents[3]/'knowledge/Audits/P8-RESEARCH-RESULTS.json'


def projection(path=None):
    path=Path(path or DEFAULT).absolute()
    if path!=DEFAULT and (not path.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
                         or any(p.lower() in {'private','data','.env'} for p in path.parts)):
        raise ValueError('Only public research evidence or temporary fixture allowed')
    empty=dict(status='NOT_AVAILABLE',scope='RESEARCH_ONLY',ml_filter='DISABLED',
        human_imitation='INSUFFICIENT_DATA',kronos='NOT_RUN',execution_eligible=False)
    if not path.is_file(): return empty
    try:
        if path.is_symlink() or path.stat().st_nlink!=1 or path.stat().st_size>8*1024*1024:
            raise ValueError('Unbounded or linked projection')
        value=json.loads(path.read_text(encoding='utf-8'))
        if (digest({k:v for k,v in value.items() if k!='result_id'})!=value['result_id']
            or value['version']!='p8-research-v1' or value['scope']!='RESEARCH_ONLY'
            or value['execution_eligible'] is not False): raise ValueError('Invalid P8 evidence')
        return dict(status=value['status'],scope='RESEARCH_ONLY',result_id=value['result_id'],
            feature_schema_id=value['feature_schema_id'],ml_filter=value['track_a']['filter_status'],
            human_imitation=value['track_b']['status'],kronos=value['kronos']['runtime'],
            policy_hash=value['track_a']['policy_hash'],registry_entries=len(value['registry']),
            tracks=dict(profitability=value['track_a']['result'],human=value['track_b']['result'],
                        kronos=value['kronos']['added_value']),execution_eligible=False)
    except (ValueError,KeyError,TypeError,OSError): return dict(empty,status='INVALID_EVIDENCE')
