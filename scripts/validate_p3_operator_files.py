"""Offline, read-only schema/consistency check. No native calls or ledger creation.

Default validates public templates. --operator-files is an explicit operator-only
read of three fixed private files; reports never include values or exception text.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core.rebuild.native_operator import OperatorSettings, RiskBasis, CostBasis, PRIVATE
from core.rebuild.operator_verification import _plain_path
from core.rebuild.safety import VERSION, fresh
from core.rebuild.safety_contracts import SafetyConfiguration

ROOT=Path(__file__).resolve().parents[1]
NAMES=('operator','risk-basis','costs')
MODELS=(OperatorSettings,RiskBasis,CostBasis)


def _pairs(items):
    result={}
    for key,value in items:
        if key in result: raise ValueError()
        result[key]=value
    return result


def _placeholder(value):
    if isinstance(value,str): return re.fullmatch(r'<[A-Z0-9_]+>',value) is not None
    if isinstance(value,dict): return any(_placeholder(k) or _placeholder(v) for k,v in value.items())
    if isinstance(value,list): return any(_placeholder(v) for v in value)
    return False


def validate_files(paths, *, current=None):
    """Paths supplied by fixed CLI mapping or synthetic test code, never by CLI users."""
    results={}
    models=[]
    for name,path,model in zip(NAMES,paths,MODELS,strict=True):
        status='FAIL'
        try:
            _plain_path(path)
            if not path.is_file():
                results[name]='MISSING'
                continue
            if path.stat().st_size>65536 or path.stat().st_nlink!=1: raise ValueError()
            raw=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=_pairs,
                           parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
            if _placeholder(raw):
                status='PLACEHOLDERS'
            else:
                models.append(model.model_validate(raw))
                status='PASS'
        except Exception:
            pass
        results[name]=status
    consistency='NOT_CHECKED'
    if len(models)==3:
        try:
            operator,basis,costs=models
            a=operator.account
            if (a.evidence_source!='MT5_DEMO' or not a.account_id.isdecimal() or int(a.account_id)<=0
                    or not operator.password.get_secret_value() or operator.policy_version!=VERSION): raise ValueError()
            SafetyConfiguration(approved_account_key=a.key,authorized_sources={operator.source_id},instruments=operator.symbols)
            exe=Path(operator.terminal_exe)
            # Lexical check only: do not inspect the terminal binary or its directory.
            if (not exe.is_absolute() or '..' in exe.parts or not exe.is_relative_to(PRIVATE)
                    or exe.name.lower() not in {'terminal64.exe','terminal.exe'}): raise ValueError()
            now=current or datetime.now(timezone.utc)
            day=now.astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
            for evidence in (basis,costs):
                if (evidence.account_key,evidence.currency)!=(a.key,a.currency): raise ValueError()
            fresh(basis.observed_at,now,5)
            if basis.day_start!=day or basis.week_start!=day-timedelta(days=day.weekday()): raise ValueError()
            if costs.observed_at>now or costs.valid_until<=now or costs.valid_until<=costs.observed_at: raise ValueError()
            if not operator.symbols<=costs.commission_per_lot.keys(): raise ValueError()
            consistency='PASS'
        except Exception:
            consistency='FAIL'
    return dict(files=results,consistency=consistency,
                status='PASS' if consistency=='PASS' and all(v=='PASS' for v in results.values()) else 'FAIL',
                broker_connected=False,trading_authorized=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operator-files',action='store_true',help='Operator-only fixed private files; no connection')
    args=parser.parse_args()
    paths=[PRIVATE/f'p3-{name}.json' if args.operator_files else ROOT/'backend/examples'/f'p3-{name}.example.json'
           for name in NAMES]
    try:
        report=validate_files(paths)
    except Exception:
        report=dict(status='FAIL',broker_connected=False,trading_authorized=False)
    print(json.dumps(report,sort_keys=True))
    return 0 if report['status']=='PASS' else 2


if __name__=='__main__':
    raise SystemExit(main())
