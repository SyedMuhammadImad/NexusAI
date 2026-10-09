"""Offline validation uses public templates and temporary synthetic documents only."""
from datetime import timedelta
import importlib.util
import json
from pathlib import Path

import pytest

from test_p3_native_operator import setup
from test_p2_safety import TIME

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('p3_setup_validator',ROOT/'scripts/validate_p3_operator_files.py')
validator=importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


@pytest.fixture
def documents(setup,monkeypatch):
    s=setup
    monkeypatch.setattr(validator,'PRIVATE',s.private)
    operator=s.settings.model_dump(mode='json')
    operator['password']='synthetic-test-only'
    values=[operator,s.basis.model_dump(mode='json'),s.costs.model_dump(mode='json')]
    paths=[s.tmp_path/f'input-{i}.json' for i in range(3)]
    for p,v in zip(paths,values): p.write_text(json.dumps(v),encoding='utf-8')
    return paths,values


def test_valid_documents_without_connection_or_sensitive_output(documents,capsys):
    paths,_=documents
    report=validator.validate_files(paths,current=TIME)
    assert report['status']=='PASS'
    assert report['broker_connected'] is report['trading_authorized'] is False
    assert 'synthetic-test-only' not in json.dumps(report)
    assert capsys.readouterr()==('','')


@pytest.mark.parametrize('index,field,value',[
    (0,'password',''),(0,'policy_version','wrong'),(0,'symbols',['EURUSDm']),
    (0,'terminal_sha256','invalid'),(0,'service_sid','invalid'),(0,'terminal_exe','terminal64.exe'),
    (1,'account_key','wrong'),(1,'currency','EUR'),(1,'day_equity','0'),
    (1,'high_water_equity','NaN'),(1,'cash_flow_total','Infinity'),
    (1,'observed_at',(TIME-timedelta(seconds=6)).isoformat()),
    (1,'day_start',TIME.isoformat()),(1,'week_start',TIME.isoformat()),
    (2,'account_key','wrong'),(2,'commission_per_lot',{}),
    (2,'commission_per_lot',{'XAUUSDm':-1}),
    (2,'valid_until',TIME.isoformat()),(2,'observed_at',(TIME+timedelta(seconds=1)).isoformat()),
    (2,'unexpected','synthetic-private-value')])
def test_schema_ranges_and_consistency_fail_closed(documents,index,field,value,capsys):
    paths,values=documents
    values[index][field]=value
    paths[index].write_text(json.dumps(values[index]),encoding='utf-8')
    report=validator.validate_files(paths,current=TIME)
    assert report['status']=='FAIL'
    assert 'synthetic-private-value' not in json.dumps(report)
    assert capsys.readouterr()==('','')


@pytest.mark.parametrize('text',['{"password":"first","password":"second"}',
    '{bad json','{"value":NaN}','[]','{}'])
def test_malformed_documents_do_not_emit_input(documents,text,capsys):
    paths,_=documents
    paths[0].write_text(text,encoding='utf-8')
    report=validator.validate_files(paths,current=TIME)
    assert report['status']=='FAIL'
    assert report['consistency']=='NOT_CHECKED'
    assert capsys.readouterr()==('','')


def test_missing_and_oversized_files(documents):
    paths,_=documents
    missing=paths[0].with_name('not-created.json')
    report=validator.validate_files([missing,*paths[1:]],current=TIME)
    assert report['files']['operator']=='MISSING'
    paths[0].write_text(' '*65537)
    assert validator.validate_files(paths,current=TIME)['files']['operator']=='FAIL'


def test_public_templates_intentionally_fail_and_cover_all_fields():
    paths=[ROOT/'backend/examples'/f'p3-{n}.example.json' for n in validator.NAMES]
    report=validator.validate_files(paths,current=TIME)
    assert set(report['files'].values())=={'PLACEHOLDERS'}
    for path,model in zip(paths,validator.MODELS):
        document=json.loads(path.read_text())
        assert set(document)==set(model.model_fields)
    from core.rebuild.ledger import DemoAccount
    assert set(json.loads(paths[0].read_text())['account'])==set(DemoAccount.model_fields)


def test_default_cli_only_maps_public_templates(monkeypatch,capsys):
    monkeypatch.setattr('sys.argv',['validate_p3_operator_files.py'])
    seen=[]
    def check(paths):
        seen.extend(paths)
        return dict(status='FAIL',broker_connected=False,trading_authorized=False)
    monkeypatch.setattr(validator,'validate_files',check)
    assert validator.main()==2
    assert all(p.parent==ROOT/'backend/examples' for p in seen)
    assert json.loads(capsys.readouterr().out)['status']=='FAIL'


def test_operator_cli_mapping_without_opening_private_files(monkeypatch,capsys):
    monkeypatch.setattr('sys.argv',['validate_p3_operator_files.py','--operator-files'])
    seen=[]
    def check(paths):
        seen.extend(paths)
        return dict(status='FAIL',broker_connected=False,trading_authorized=False)
    monkeypatch.setattr(validator,'validate_files',check)
    assert validator.main()==2
    assert seen==[validator.PRIVATE/f'p3-{n}.json' for n in validator.NAMES]
    assert 'account_id' not in capsys.readouterr().out


def test_placeholder_rule_does_not_ban_password_punctuation(documents):
    paths,values=documents
    values[0]['password']='synthetic<>punctuation-only'
    paths[0].write_text(json.dumps(values[0]))
    assert validator.validate_files(paths,current=TIME)['status']=='PASS'
