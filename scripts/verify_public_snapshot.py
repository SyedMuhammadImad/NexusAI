import os,sys
from pathlib import Path
from urllib.parse import unquote,urlsplit
keep={'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE','HOMEDRIVE','HOMEPATH','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE'}
for k in list(os.environ):
    if k.upper() not in keep: del os.environ[k]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
blocked=[]
def guard(event,args):
    if event in {'open','os.listdir','os.scandir','sqlite3.connect'} and args and isinstance(args[0],(str,bytes,os.PathLike)):
        value=os.fsdecode(args[0])
        if value.startswith('file:'):
            uri=urlsplit(value)
            if uri.netloc not in {'','localhost'}:
                blocked.append(event)
                raise PermissionError('Nonlocal SQLite URI forbidden in tests')
            value=unquote(uri.path)
            if len(value)>2 and value[0]=='/' and value[2]==':': value=value[1:]
        if value==':memory:': return
        p=str(Path(value).resolve()).replace('\\','/').lower()
        if '/backend/private' in p or '/backend/data/' in p or p.endswith('/backend/data') or '/.env' in p and not p.endswith('/.env.example'):
            blocked.append(event)
            raise PermissionError('Sensitive location forbidden in fixture verification')
    if event=='import' and args[0] in {'main','legacy_application','MetaTrader5'}:
        blocked.append(event)
        raise PermissionError('Forbidden runtime import')
for event,path in [('sqlite3.connect',Path.cwd()/'backend/data/private_trader_learning.sqlite3'),('open',Path.cwd()/'backend/.env'),('sqlite3.connect','backend/data/private_trader_learning.sqlite3'),('open','backend/.env'),('sqlite3.connect',(Path.cwd()/'backend/data/private_trader_learning.sqlite3').as_uri().replace('/backend/','/%62ackend/')+'?mode=ro'),('sqlite3.connect',(Path.cwd()/'backend/data/private_trader_learning.sqlite3').as_uri()+'?mode=ro')]:
    try: guard(event,(path,))
    except PermissionError: pass
    else: raise AssertionError('Guard self-test failed')
print('GUARD_SYNTHETIC_EVENT_SELFTESTS',len(blocked))
blocked.clear()
sys.addaudithook(guard)
import pytest
code=pytest.main(['backend/tests/test_current_profile_operator.py', 'backend/tests/test_p3_readonly_bootstrap.py', 'backend/tests/test_v1_completion.py', 'backend/tests/test_v1_operator_audit.py', 'backend/tests/test_operator_profile_removal.py', 'backend/tests/test_registry_publication.py', 'backend/tests/test_p8_research.py', 'backend/tests/test_v1_operations.py', 'backend/tests/test_p7_tournament.py', 'backend/tests/test_p6_research.py', 'backend/tests/test_p5_alternative_provider.py', 'backend/tests/test_p5_feed_calendar.py', 'backend/tests/test_p5_sessions.py', 'backend/tests/test_p5_market_data.py', 'backend/tests/test_p5_qualification.py', 'backend/tests/test_p5_continuity.py', 'backend/tests/test_p5_histdata_audit.py', 'backend/tests/test_p4_sources.py', 'backend/tests/test_p3_execution.py', 'backend/tests/test_p3_mt5_boundary.py', 'backend/tests/test_p3_native_semantic_gate.py', 'backend/tests/test_p3_observation_revisions.py', 'backend/tests/test_p3_native_evidence.py', 'backend/tests/test_p3_operator_verification.py', 'backend/tests/test_p3_native_operator.py', 'backend/tests/test_p3_operator_setup.py', 'backend/tests/test_p2_safety.py', 'backend/tests/test_p1_lifecycle.py', 'backend/tests/test_phase0_preservation.py', 'backend/tests/test_phase1_integrity.py', 'backend/tests/test_phase2_integrity.py', 'backend/tests/test_rebuild_core.py', 'backend/tests/test_signal_parser.py', 'backend/tests/test_chat_import_service.py', 'backend/tests/test_p1_historical_bridge.py', 'backend/tests/test_p1_m2_incident_review.py', '-q', '-p', 'no:cacheprovider', '--tb=short'])
print('SENSITIVE_OR_OPERATOR_ACCESS_ATTEMPTS',len(blocked))
print('FORBIDDEN_RUNTIME_MODULES',[m for m in sys.modules if m in {'main','legacy_application','MetaTrader5'} or m.startswith('agents.')])
sys.exit(code)
