"""Operator orchestration with fake isolation/session and temporary ledgers only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import json
import os
import runpy
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from core.rebuild.ledger import DemoAccount, Ledger
from core.rebuild.lifecycle_service import LifecycleService
from core.rebuild.operator_verification import (
    OperatorBlocked, OperatorVerification, VerificationLedger, USE_EVENT, preflight,
)
from core.rebuild.safety import SafetyEngine
from core.rebuild.safety_contracts import SafetyConfiguration
from test_p2_safety import ACCOUNT, TIME, inputs, intent
from test_p3_execution import FakeBroker, Crash, reservation
from test_p3_mt5_boundary import adapter_fixture
from test_p3_native_evidence import install_native_batch


class FixtureIsolation:
    """Not real machine attestation. Never imported by an operator connector."""
    def __init__(self):
        self.calls = []
        self.fail_at = None

    def require_safe(self, account, session_id, directory, phase):
        assert account.evidence_source == 'FIXTURE'
        self.calls.append((account.key, session_id, directory, phase))
        if phase == self.fail_at:
            raise RuntimeError('sensitive-transport-text-must-not-escape')
        return 'fixture-isolation-evidence'


def prepared(tmp_path, *, risk=.00016, source='MANUAL', entry_type='MARKET'):
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    config = SafetyConfiguration(approved_account_key=ACCOUNT.key, authorized_sources={'operator'})
    safety = SafetyEngine(ledger, config)
    safety.reset_halt(inputs(), operator_id='fixture-operator', reason='fixture smoke only', current=TIME)
    identity = intent(ledger, risk=risk, source=source, entry_type=entry_type,
                      entry=99.9 if entry_type == 'LIMIT' else None)
    result = safety.evaluate(identity, 'operator-decision', inputs(), current=TIME)
    assert result['decision'] == 'APPROVED', result
    request = safety.eligible_request(identity, 'operator-decision', current=TIME)['execution_request_id']
    broker, isolation = FakeBroker(), FixtureIsolation()
    run = OperatorVerification(safety, session_id='fixture-session', isolation=isolation, clock=lambda: broker.time)
    run.connect(lambda *_: broker)
    return ledger, safety, run, broker, isolation, request


def test_default_preflight_no_native_import_or_state(tmp_path):
    assert preflight() == dict(operator_path='NOT_QUALIFIED', demo_verification='NOT_RUN',
        blocker='MACHINE_ISOLATION_VERIFIER_AND_OPERATOR_CONTEXT_NOT_QUALIFIED', broker_actions=0, secrets='NONE')
    assert list(tmp_path.iterdir()) == []


def test_preflight_cli_cannot_unlock_or_connect(capsys):
    script = Path(__file__).resolve().parents[2]/'scripts/p3_operator_preflight.py'
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(script),run_name='__main__')
    assert result.value.code == 2
    assert json.loads(capsys.readouterr().out) == preflight()


def test_default_blocks_before_connector_and_secrets(tmp_path):
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    safety = SafetyEngine(ledger, SafetyConfiguration(approved_account_key=ACCOUNT.key, authorized_sources={'operator'}))
    run = OperatorVerification(safety, session_id='fixture-session')
    called = []
    with pytest.raises(OperatorBlocked, match='MACHINE_ISOLATION_NOT_QUALIFIED'):
        run.connect(lambda *_: called.append('credential-or-broker-access'))
    assert not called
    assert ledger.status()['halt']['state'] == 'HALTED'


def test_new_ledger_default_halt_and_no_existing_database_touch(tmp_path):
    sentinel = tmp_path / 'existing.sqlite3'
    sentinel.write_bytes(b'not an operator database; isolation sentinel')
    before = sentinel.stat().st_mtime_ns
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    assert ledger.path != sentinel
    assert ledger.status()['halt']['state'] == 'HALTED'
    assert sentinel.read_bytes() == b'not an operator database; isolation sentinel'
    assert sentinel.stat().st_mtime_ns == before
    reopened = VerificationLedger.resume(ledger.path.parent.name, ACCOUNT, workspace=tmp_path)
    assert reopened.path == ledger.path


def test_ordinary_ledger_not_accepted(tmp_path):
    safety = SafetyEngine(Ledger(tmp_path/'ordinary.sqlite', account=ACCOUNT),
                         SafetyConfiguration(approved_account_key=ACCOUNT.key, authorized_sources={'operator'}))
    with pytest.raises(OperatorBlocked, match='ISOLATED_VERIFICATION_LEDGER_REQUIRED'):
        OperatorVerification(safety, session_id='fixture-session')


def test_reparse_root_rejected_before_creation(tmp_path, monkeypatch):
    original = Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda p:p==tmp_path/'.p3-verification' or original(p))
    with pytest.raises(OperatorBlocked,match='LINKED_VERIFICATION_PATH'):
        VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('run_id', ['../other', '..', 'not-a-uuid', '/absolute', ''])
def test_resume_rejects_arbitrary_paths_without_open(tmp_path, run_id):
    with pytest.raises(ValueError):
        VerificationLedger.resume(run_id, ACCOUNT, workspace=tmp_path)
    assert not list(tmp_path.iterdir())


def test_file_replacement_detected_before_sqlite(tmp_path, monkeypatch):
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    ledger.path.rename(ledger.path.with_name('preserved.sqlite3'))
    ledger.path.write_bytes(b'not SQLite')
    monkeypatch.setattr(sqlite3, 'connect', lambda *_args, **_kw: pytest.fail('Opened replacement'))
    with pytest.raises(OperatorBlocked, match='FILE_IDENTITY_CHANGED'):
        ledger.status()


def test_hardlinked_database_and_sidecar_rejected(tmp_path):
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    other = tmp_path/'alias'
    other.hardlink_to(ledger.path)
    with pytest.raises(OperatorBlocked):
        ledger.status()
    other.unlink()  # Fixture-only link cleanup.
    sentinel = tmp_path/'sentinel'
    sentinel.write_bytes(b'unchanged')
    Path(str(ledger.path)+'-journal').hardlink_to(sentinel)
    with pytest.raises(OperatorBlocked, match='SIDECAR'):
        ledger.status()
    assert sentinel.read_bytes() == b'unchanged'


def test_wrong_resume_account_rejected(tmp_path):
    ledger = VerificationLedger.create(ACCOUNT, workspace=tmp_path)
    wrong = ACCOUNT.model_copy(update={'account_id':'other'})
    with pytest.raises(OperatorBlocked, match='RUN_BINDING_MISMATCH'):
        VerificationLedger.resume(ledger.path.parent.name, wrong, workspace=tmp_path)


def test_native_workspace_cannot_be_redirected(tmp_path):
    account = DemoAccount(account_id='123', server='fixture-native', currency='USD', evidence_source='MT5_DEMO')
    with pytest.raises(OperatorBlocked, match='NATIVE_WORKSPACE_NOT_ALLOWED'):
        VerificationLedger.create(account, workspace=tmp_path)
    assert not list(tmp_path.iterdir())


def test_success_minimum_lineage_halt_and_replay(tmp_path):
    ledger, safety, run, broker, _, request = prepared(tmp_path)
    assert run.submit_once(request)['state'] == 'FILLED'
    assert len(broker.calls) == 1
    assert Decimal(broker.calls[0]['volume']) == Decimal('.01')
    assert broker.calls[0]['minimum_volume_only'] is True
    assert reservation(ledger)['state'] == 'CONVERTED'
    assert ledger.status()['halt']['state'] == 'HALTED'
    for _ in range(2):
        run.reconcile()
    trace = LifecycleService(ledger).trace('source-one')['lifecycles'][0]
    assert trace['p3_attempts'][0]['execution_request_id'] == request
    assert trace['p3_orders'][0]['attempt_id'] == trace['p3_attempts'][0]['attempt_id']
    assert trace['p3_deals'][0]['broker_position_id'] == trace['p3_positions'][0]['broker_position_id']
    assert trace['outcomes'] == []
    assert len(trace['p3_deals']) == 1
    reopened = VerificationLedger.resume(ledger.path.parent.name, ACCOUNT, workspace=tmp_path)
    restarted = OperatorVerification(SafetyEngine(reopened,safety.config), session_id='fixture-session',
                                     isolation=FixtureIsolation(), clock=lambda:TIME)
    restarted.connect(lambda *_:broker)
    with pytest.raises(OperatorBlocked, match='SMOKE_ALREADY_USED'):
        restarted.submit_once(request)
    restarted.reconcile()
    assert len(broker.calls) == 1


@pytest.mark.parametrize('bad', ['oversized','halt','stale','account','live','scope','missing_quote','missing_reservation','policy','external'])
def test_failure_gates_never_send(tmp_path, bad):
    ledger, safety, run, broker, _, request = prepared(tmp_path, risk=None if bad=='oversized' else .00016)
    if bad == 'halt': ledger.halt('fixture manual stop')
    if bad == 'stale': broker.time += timedelta(seconds=61)
    if bad == 'account': broker.attestation_changes['account_id'] = 'wrong'
    if bad == 'live': broker.attestation_changes['mode'] = 'LIVE'
    if bad == 'scope': broker.attestation_changes['scope'] = 'MT5_DEMO'
    if bad == 'missing_quote': broker.data['quotes'].clear()
    if bad == 'missing_reservation':
        with ledger.transaction() as c: c.execute("UPDATE p2_reservations SET state='RELEASED'")
    if bad == 'policy':
        safety.activate_configuration(safety.config, revision='2', operator_id='fixture', reason='fixture update')
    if bad == 'external':
        broker.orders.append(dict(evidence_id='external', observed_at=TIME,broker_order_id='external',
            correlation='external',magic=1,symbol='XAUUSDm',direction='BUY',entry_type='MARKET',requested_volume='.01',
            filled_volume='0',stop_loss='90',take_profit='130',status='PLACED'))
    run.submit_once(request)
    assert not broker.calls
    assert ledger.status()['halt']['state'] == 'HALTED'


def test_limit_is_not_used_for_smoke(tmp_path):
    ledger, _, run, broker, _, request = prepared(tmp_path, entry_type='LIMIT')
    run.submit_once(request)
    assert not broker.calls
    assert ledger.status()['halt']['state'] == 'HALTED'


def test_nonmanual_source_is_not_used_for_smoke(tmp_path):
    ledger, _, run, broker, _, request = prepared(tmp_path, source='WHATSAPP_HUMAN')
    run.submit_once(request)
    assert not broker.calls
    assert ledger.status()['halt']['state'] == 'HALTED'


def test_native_shaped_observations_reconcile_once(tmp_path):
    ledger, _, run, broker, _, request = prepared(tmp_path)
    install_native_batch(broker)
    assert run.submit_once(request)['state'] == 'FILLED'
    with ledger.connect() as c:
        observations = c.execute('SELECT count(*) FROM p3_observations').fetchone()[0]
        assert observations > 0
        assert c.execute('SELECT count(*) FROM p3_observation_links').fetchone()[0] > 0
    run.reconcile()
    run.reconcile()
    with ledger.connect() as c:
        assert c.execute('SELECT count(*) FROM p3_observations').fetchone()[0] == observations
        assert c.execute('SELECT count(*) FROM p3_deals').fetchone()[0] == 1
    assert len(broker.calls) == 1


@pytest.mark.parametrize('phase', ['BEFORE_REQUEST','ATTEST','ATTEST_RETURN','SEND'])
def test_revoked_lease_no_send_no_secret_in_error(tmp_path, phase):
    ledger, _, run, broker, isolation, request = prepared(tmp_path)
    isolation.fail_at = phase
    if phase == 'BEFORE_REQUEST':
        with pytest.raises(OperatorBlocked) as error:
            run.submit_once(request)
        assert 'sensitive-transport' not in str(error.value)
    else:
        run.submit_once(request)
    assert not broker.calls
    assert ledger.status()['halt']['state'] == 'HALTED'
    if phase == 'SEND': assert reservation(ledger)['state'] == 'AMBIGUOUS'


def test_bad_connector_redacted_and_never_reconnected(tmp_path):
    ledger, safety, _, _, _, _ = prepared(tmp_path)
    run = OperatorVerification(safety,session_id='fixture-session',isolation=FixtureIsolation(),clock=lambda:TIME)
    def bad(*_): raise OperatorBlocked('sensitive-transport-text-must-not-escape')
    with pytest.raises(OperatorBlocked, match='OPERATOR_SESSION_FAILED') as error:
        run.connect(bad)
    assert 'sensitive-transport' not in str(error.value)
    with pytest.raises(OperatorBlocked, match='SESSION_ALREADY_BOUND'):
        run.connect(bad)
    assert ledger.status()['halt']['state'] == 'HALTED'


def test_p2_request_is_mandatory(tmp_path):
    ledger, _, run, broker, _, _ = prepared(tmp_path)
    with pytest.raises(OperatorBlocked,match='P2_REQUEST_REQUIRED'):
        run.submit_once('not-a-p2-request')
    assert not broker.calls
    assert not (ledger.path.parent.parent/'smoke-used.json').exists()
    assert ledger.status()['halt']['state'] == 'HALTED'


def test_attestation_mismatch_at_connect_no_submission(tmp_path):
    ledger, safety, _, broker, _, _ = prepared(tmp_path)
    broker.attestation_changes['mode'] = 'LIVE'
    run = OperatorVerification(safety,session_id='fixture-session',isolation=FixtureIsolation(),clock=lambda:TIME)
    with pytest.raises(OperatorBlocked,match='OPERATOR_SESSION_FAILED'):
        run.connect(lambda *_:broker)
    assert run.engine is None and not broker.calls
    assert ledger.status()['halt']['state'] == 'HALTED'


def test_exact_allowlist_required_before_connection(tmp_path):
    ledger = VerificationLedger.create(ACCOUNT,workspace=tmp_path)
    safety = SafetyEngine(ledger,SafetyConfiguration(approved_account_key='other',authorized_sources={'operator'}))
    with pytest.raises(OperatorBlocked,match='OPERATOR_ACCOUNT_NOT_ALLOWLISTED'):
        OperatorVerification(safety,session_id='fixture-session',isolation=FixtureIsolation())


@pytest.mark.parametrize('crash', ['before','after','timeout'])
def test_ambiguity_burns_budget_retains_risk_no_resubmit(tmp_path, crash):
    ledger, _, run, broker, _, request = prepared(tmp_path)
    broker.crash = crash
    if crash != 'timeout':
        with pytest.raises(Crash): run.submit_once(request)
    else:
        run.submit_once(request)
    # Timeout is followed by the existing engine's read-only reconciliation:
    # the fake confirms a fill, so exposure conversion is correct, not release.
    assert reservation(ledger)['state'] in ({'CONVERTED'} if crash=='timeout' else {'SUBMISSION_BEGUN','AMBIGUOUS'})
    assert ledger.status()['halt']['state'] == 'HALTED'
    with pytest.raises(OperatorBlocked, match='SMOKE_ALREADY_USED'):
        run.submit_once(request)
    broker.crash = None
    run.reconcile()
    assert len(broker.calls) == 1


def test_new_run_cannot_reset_workspace_budget(tmp_path):
    _, _, run, broker, _, request = prepared(tmp_path)
    broker.outcome = 'REJECTED'
    run.submit_once(request)
    ledger2, _, run2, broker2, _, request2 = prepared(tmp_path)
    with pytest.raises(OperatorBlocked, match='WORKSPACE_SMOKE_ALREADY_USED'):
        run2.submit_once(request2)
    assert len(broker.calls) == 1 and not broker2.calls
    assert ledger2.status()['halt']['state'] == 'HALTED'


def test_crash_before_engine_call_burns_budget(tmp_path, monkeypatch):
    ledger, _, run, broker, _, request = prepared(tmp_path)
    def crash(*_): raise Crash()
    monkeypatch.setattr(run.engine,'submit',crash)
    with pytest.raises(Crash): run.submit_once(request)
    with ledger.connect() as conn:
        assert json.loads(conn.execute('SELECT payload FROM audit_events WHERE event_id=?',(USE_EVENT,)).fetchone()[0])['execution_request_id'] == request
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('DELETE FROM audit_events WHERE event_id=?',(USE_EVENT,))
    assert not broker.calls
    with pytest.raises(OperatorBlocked): run.submit_once(request)


def test_concurrent_callers_cannot_submit_twice(tmp_path):
    _, _, run, broker, _, request = prepared(tmp_path)
    def invoke():
        try: return run.submit_once(request)
        except OperatorBlocked: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:invoke(),range(2)))
    assert len(broker.calls) <= 1  # Losing caller may commit HALT before winner sends.


def test_native_final_metadata_minimum_check(tmp_path):
    native, adapter, command = adapter_fixture(tmp_path)
    command.update(minimum_volume_only=True,volume='.01')
    assert adapter.submit(command).outcome == 'ACKNOWLEDGED'
    assert len(native.sent) == 1
    native.sent.clear()
    command['volume'] = '.02'
    with pytest.raises(ValueError,match='current broker minimum'):
        adapter.submit(command)
    assert not native.sent


def test_process_death_after_claim_cannot_restart_submission(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    keep = {'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP','LOCALAPPDATA','APPDATA',
            'USERPROFILE','HOMEDRIVE','HOMEPATH','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE'}
    env = {k:v for k,v in os.environ.items() if k.upper() in keep}
    env.update(PYTHONPATH=os.pathsep.join([str(backend),str(backend/'tests')]),
               PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONDONTWRITEBYTECODE='1')
    # Reviewed child: synthetic fixture, explicit temp path, no runtime or MT5.
    script = '''import os,sys
from pathlib import Path
from test_p3_operator_verification import prepared
ledger,safety,run,broker,isolation,request=prepared(Path(sys.argv[1]))
run.engine.submit=lambda *_:os._exit(73)
run.submit_once(request)
'''
    result = subprocess.run([sys.executable,'-B','-c',script,str(tmp_path)],env=env,cwd=backend,
                            capture_output=True,timeout=30)
    assert result.returncode == 73
    root = tmp_path/'.p3-verification'
    marker = json.loads((root/'smoke-used.json').read_text())
    ledger = VerificationLedger.resume(marker['run_id'],ACCOUNT,workspace=tmp_path)
    safety = SafetyEngine(ledger,SafetyConfiguration(approved_account_key=ACCOUNT.key,authorized_sources={'operator'}))
    run = OperatorVerification(safety,session_id='fixture-session',isolation=FixtureIsolation(),clock=lambda:TIME)
    broker = FakeBroker()
    run.connect(lambda *_:broker)
    with pytest.raises(OperatorBlocked,match='SMOKE_ALREADY_USED'):
        run.submit_once(marker['execution_request_id'])
    assert not broker.calls
    assert ledger.status()['halt']['state'] == 'HALTED'
