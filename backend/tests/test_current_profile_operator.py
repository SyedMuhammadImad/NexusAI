"""Cooperative boundary tests: fake broker shapes, temp files, no real credentials."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import runpy

import pytest

from core.rebuild import current_profile as cp
from core.rebuild import native_operator as op
from core.rebuild.operator_verification import OperatorBlocked
from test_p3_native_evidence import Native
from test_p2_safety import TIME


def host(**changes):
    value = dict(version=cp.HOST_VERSION, current_identity=True, session_match=True,
                 non_admin=True, exclusive_terminal=True, protected_acl=True, terminal_pid=42)
    value.update(changes)
    return value


@pytest.mark.parametrize('key', ['current_identity', 'session_match', 'non_admin', 'exclusive_terminal', 'protected_acl'])
def test_current_profile_cannot_relax_failed_host_evidence(key):
    with pytest.raises(OperatorBlocked):
        cp.validate_host(host(**{key: False}), phase='READ', terminal_pid=42)


@pytest.mark.parametrize('change', [dict(version='p3-system-attestor-v1'), dict(terminal_pid=True),
                                  dict(terminal_pid=43), dict(session_zero=True)])
def test_removed_profile_receipts_and_mismatched_processes_reject(change):
    with pytest.raises(OperatorBlocked):
        cp.validate_host(host(**change), phase='READ', terminal_pid=42)


def test_prepare_and_execution_are_distinct():
    assert cp.validate_host(host(terminal_pid=0), phase='PREPARE', terminal_pid=0)
    with pytest.raises(OperatorBlocked):
        cp.validate_host(host(terminal_pid=0), phase='EXECUTION', terminal_pid=0)


def setup(tmp_path, monkeypatch):
    private = tmp_path / 'fixture-operator'
    private.mkdir()
    terminal = private / 'current-profile-terminal/terminal64.exe'
    terminal.parent.mkdir()
    terminal.write_bytes(b'fixture-only-not-executable')
    monkeypatch.setattr(cp, 'TERMINAL', terminal)
    monkeypatch.setattr(op, 'PRIVATE', private)
    seed = cp.BootstrapSettings(account=dict(account_id='123', server='demo-fixture',
        currency='<THREE_LETTER_ACCOUNT_CURRENCY>', mode='DEMO', evidence_source='MT5_DEMO'),
        password='fixture-only', terminal_exe=str(terminal), terminal_sha256=hashlib.sha256(terminal.read_bytes()).hexdigest(),
        service_sid='S-1-5-21-111-222-333-1001', broker_company='<EXACT_BROKER_COMPANY>',
        terminal_company='<EXACT_TERMINAL_COMPANY>', source_id='<AUTHORIZED_MANUAL_SOURCE_ID>',
        symbols={'XAUUSDm', 'XAGUSDm', 'USOILm'}, policy_version='P2-DEMO-1.0')
    native = Native()
    native.a.update(company='fixture-broker', leverage=100, server='demo-fixture')
    native.t.update(company='fixture-terminal', path=str(terminal.parent), data_path=str(terminal.parent), build=1)
    owner = dict(sid='S-1-5-21-111-222-333-1002', session_id=1, non_admin=True)
    return seed, native, owner


def test_derives_only_metadata_after_positive_demo_binding(tmp_path, monkeypatch):
    seed, native, owner = setup(tmp_path, monkeypatch)
    seed.validate_seed()
    settings, report = cp.attested_settings(seed, native, owner, seed.terminal_sha256, current=TIME)
    assert settings.account.currency == 'USD'
    assert settings.service_sid == owner['sid']
    assert settings.source_id == 'current-profile-manual'
    assert settings.password.get_secret_value() == 'fixture-only'
    assert report['account_match'] is True and report['account'] == 'ATTESTED_DEMO'
    assert 'fixture-only' not in json.dumps(report)
    assert 'session_zero' not in report and 'dedicated_identity' not in report


@pytest.mark.parametrize('change', ['real', 'account', 'server', 'terminal', 'currency', 'broker'])
def test_native_mismatch_rejects_before_baseline_or_submission(tmp_path, monkeypatch, change):
    seed, native, owner = setup(tmp_path, monkeypatch)
    if change == 'real': native.a['trade_mode'] = native.ACCOUNT_TRADE_MODE_REAL
    if change == 'account': native.a['login'] = 999
    if change == 'server': native.a['server'] = 'other'
    if change == 'terminal': native.t['data_path'] = 'other'
    if change == 'currency': seed = seed.model_copy(update={'account': seed.account.model_copy(update={'currency': 'EUR'})})
    if change == 'broker': seed = seed.model_copy(update={'broker_company': 'different'})
    with pytest.raises(OperatorBlocked):
        cp.attested_settings(seed, native, owner, seed.terminal_sha256, current=TIME)


def test_unresolved_metadata_is_not_permission_to_default_credentials(tmp_path, monkeypatch):
    seed, _, _ = setup(tmp_path, monkeypatch)
    for update in ({'policy_version': 'unknown'}, {'symbols': {'EURUSDm'}}, {'password': '<SUPPLY_LOCALLY_DO_NOT_SHARE>'}):
        with pytest.raises(ValueError):
            cp.BootstrapSettings.model_validate({**seed.model_dump(), **update}).validate_seed()


def test_default_cli_does_not_read_private_files_or_connect():
    script = Path(__file__).resolve().parents[2] / 'scripts/p3_current_profile_audit.py'
    result = subprocess.run([str(Path(__file__).resolve().parents[1] / '.venv/Scripts/python.exe'),
                             '-B', str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value['status'] == 'PLAN_ONLY' and value['broker_actions'] == 0
    assert value['broker_execution'] == 'HARD_DISABLED'


def test_host_collector_parses_without_execution():
    script = Path(__file__).resolve().parents[2] / 'scripts/p3_current_profile_host.ps1'
    command = f"$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$t,[ref]$e);if($e.Count){{exit 2}}"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, timeout=15)
    assert result.returncode == 0


def test_system_powershell_environment_and_actual_venv_worker_identity():
    assert cp._windows_environment()['PSModulePath'] == str(
        Path(os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/Modules')
    owner = cp.actor()
    # Process metadata only: no protected paths, native SDK, credentials or terminal.
    value = cp._powershell(cp.HOST_SCRIPT, dict(actor_sid=owner['sid'], session_id=owner['session_id'],
        python_exe=sys._base_executable, python_pid=os.getpid(), terminal_exe='fixture-unused.exe',
        terminal_pid=0, phase='PREPARE', protected_paths=[]))
    assert value['current_identity'] is True and value['session_match'] is True
    assert value['non_admin'] is True


def test_readonly_entry_has_no_economic_path():
    text = Path(cp.__file__).read_text(encoding='utf-8')
    assert 'order_send(' not in text and 'submit_once(' not in text and 'reset_halt(' not in text
    assert 'ReadOnlyNativeAPI(native)' in text
    assert 'qualified' not in cp.ReadOnlyNativeAPI.METHODS


def test_worker_lease_excludes_second_worker_and_releases(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, 'REPOSITORY', tmp_path)
    with cp.worker_lease():
        with pytest.raises(OperatorBlocked, match='WORKER_ALREADY_ACTIVE'):
            with cp.worker_lease():
                pytest.fail('Second worker entered')
    with cp.worker_lease():
        pass


def readonly_setup(tmp_path, monkeypatch):
    from core.rebuild import operator_verification
    seed, native, owner = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cp, 'REPOSITORY', tmp_path)
    monkeypatch.setattr(operator_verification, 'REPOSITORY', tmp_path)
    monkeypatch.setattr(cp, 'PRIVATE', cp.TERMINAL.parent.parent)
    monkeypatch.setattr(cp, 'CONFIG_PATH', cp.PRIVATE / 'fixture-config.json')
    monkeypatch.setattr(cp, 'MARKER', tmp_path / '.p3-verification/current-profile-run.json')
    monkeypatch.setattr(cp, 'TERMINAL_RECEIPT', tmp_path / '.p3-verification/current-profile-terminal.json')
    public = tmp_path / 'public-fixture.exe'
    public.write_bytes(cp.TERMINAL.read_bytes())
    monkeypatch.setattr(cp, 'PUBLIC_TERMINAL', public)
    monkeypatch.setattr(cp, '_load_private', lambda *args: seed)
    monkeypatch.setattr(cp, 'actor', lambda: owner)
    phases = []
    monkeypatch.setattr(cp, 'host_check', lambda actor, phase, pid, paths: phases.append(phase))
    monkeypatch.setattr(cp.time, 'sleep', lambda _: None)
    class Child:
        pid = 42
        stopped = False
        def poll(self): return 0 if self.stopped else None
        def terminate(self): self.stopped = True
        def wait(self, timeout): return 0
    child = Child()
    monkeypatch.setattr(cp.subprocess, 'Popen', lambda *args, **kwargs: child)
    native.initialize_calls = []
    native.initialize = lambda *args, **kw: native.initialize_calls.append((args, kw)) or True
    native.shutdown = lambda: None
    native.symbol_select = lambda *args: True
    return seed, native, child, phases


def test_readonly_whole_path_keeps_halt_cost_unknown_and_zero_attempts(tmp_path, monkeypatch):
    seed, native, child, phases = readonly_setup(tmp_path, monkeypatch)
    value = cp.readonly_audit(native_factory=lambda: native)
    assert value['status'] == 'READONLY_AUDIT_COMPLETE'
    assert value['qualification'] == 'NOT_QUALIFIED' and value['commission'] == 'UNVERIFIED'
    assert value['broker_actions'] == 0 and value['broker_execution'] == 'HARD_DISABLED'
    assert child.stopped and len(native.initialize_calls) == 1
    assert native.initialize_calls[0][1]['server'] == seed.account.server
    assert native.initialize_calls[0][1]['login'] == int(seed.account.account_id)
    assert phases[:2] == ['PREPARE', 'PREPARE'] and phases[-1] == 'READ'
    from core.rebuild.operator_verification import VerificationLedger
    ledger = VerificationLedger.resume(value['run_id'], cp.DemoAccount(account_id=seed.account.account_id,
        server=seed.account.server, currency='USD', evidence_source='MT5_DEMO'), workspace=tmp_path)
    with ledger.connect() as conn:
        assert conn.execute('SELECT count(*) FROM p3_attempts').fetchone()[0] == 0
        assert conn.execute('SELECT state FROM halt_state').fetchone()[0] == 'HALTED'


def test_host_failure_never_imports_or_initializes_native(tmp_path, monkeypatch):
    seed, native, _, _ = readonly_setup(tmp_path, monkeypatch)
    def denied(*args): raise OperatorBlocked('CURRENT_PROFILE_HOST_NOT_QUALIFIED')
    monkeypatch.setattr(cp, 'host_check', denied)
    with pytest.raises(OperatorBlocked):
        cp.readonly_audit(native_factory=lambda: pytest.fail('Native factory invoked'))
    assert native.initialize_calls == []


@pytest.mark.parametrize('field,value', [('trade_allowed', False), ('trade_expert', False)])
def test_missing_account_algo_permission_blocks_initialization(tmp_path, monkeypatch, field, value):
    _, native, child, _ = readonly_setup(tmp_path, monkeypatch)
    native.a[field] = value
    report = cp.readonly_audit(native_factory=lambda: native)
    assert report['blocker'] == 'CURRENT_PROFILE_ALGO_PERMISSION_NOT_PROVEN'
    assert report['broker_actions'] == 0 and child.stopped
    assert not cp.MARKER.exists()


def test_shutdown_failure_still_stops_owned_readonly_child(tmp_path, monkeypatch):
    _, native, child, _ = readonly_setup(tmp_path, monkeypatch)
    def broken_shutdown():
        raise RuntimeError('fixture shutdown failure')
    native.shutdown = broken_shutdown
    with pytest.raises(RuntimeError):
        cp.readonly_audit(native_factory=lambda: native)
    assert child.stopped


@pytest.mark.parametrize('code,expected', [(-6, 'CURRENT_PROFILE_AUTHENTICATION_FAILED'),
    (-10005, 'CURRENT_PROFILE_IPC_TIMEOUT'), (-10003, 'CURRENT_PROFILE_IPC_INITIALIZATION_FAILED'),
    (-1, 'CURRENT_PROFILE_CONNECTION_FAILED')])
def test_connection_diagnostics_never_publish_native_descriptions(tmp_path, monkeypatch, code, expected):
    _, native, child, _ = readonly_setup(tmp_path, monkeypatch)
    native.initialize = lambda *args, **kwargs: False
    native.last_error = lambda: (code, 'fixture-sensitive-description')
    report = cp.readonly_audit(native_factory=lambda: native)
    assert report['blocker'] == expected and report['broker_actions'] == 0
    assert child.stopped and not cp.MARKER.exists()
    assert 'fixture-sensitive-description' not in json.dumps(report)


def test_terminal_receipt_replay_and_identity_mismatch(tmp_path, monkeypatch):
    seed, _, _, _ = readonly_setup(tmp_path, monkeypatch)
    cp.TERMINAL_RECEIPT.parent.mkdir()
    owner = dict(sid='S-1-5-21-111-222-333-1002')
    cp.terminal_receipt(seed, owner, seed.terminal_sha256)
    original = cp.TERMINAL_RECEIPT.read_bytes()
    (cp.TERMINAL.parent / 'fixture-native-state').write_bytes(b'not credentials')
    cp.terminal_receipt(seed, owner, seed.terminal_sha256)
    assert cp.TERMINAL_RECEIPT.read_bytes() == original
    other = seed.model_copy(update={'account': seed.account.model_copy(update={'account_id': '999'})})
    with pytest.raises(OperatorBlocked, match='RECEIPT_MISMATCH'):
        cp.terminal_receipt(other, owner, seed.terminal_sha256)


def test_startup_confirmation_precedes_native_import_and_refreshes_host(tmp_path, monkeypatch):
    _, native, child, phases = readonly_setup(tmp_path, monkeypatch)
    steps = []
    def ready():
        assert native.initialize_calls == []
        steps.append('ready')
    def factory():
        assert steps == ['ready'] and phases[-1] == 'READ'
        steps.append('native')
        return native
    report = cp.readonly_audit(native_factory=factory, startup_ready=ready)
    assert steps == ['ready', 'native'] and report['broker_actions'] == 0
    assert len(native.initialize_calls) == 1 and child.stopped


def test_startup_confirmation_failure_never_invokes_native(tmp_path, monkeypatch):
    _, native, child, _ = readonly_setup(tmp_path, monkeypatch)
    def denied():
        raise OperatorBlocked('CURRENT_PROFILE_STARTUP_CANCEL_NOT_CONFIRMED')
    report = cp.readonly_audit(native_factory=lambda: pytest.fail('Native invoked before confirmation'),
                               startup_ready=denied)
    assert report['blocker'] == 'CURRENT_PROFILE_STARTUP_CANCEL_NOT_CONFIRMED'
    assert report['stage'] == 'STARTUP_CANCEL_CONFIRMATION' and report['broker_actions'] == 0
    assert native.initialize_calls == [] and child.stopped


def test_host_freshness_failure_is_specific_and_still_blocks(monkeypatch):
    monkeypatch.setattr(cp, '_powershell', lambda *args: host(terminal_pid=0))
    def stale(*args):
        raise cp.Veto('STALE_OR_FUTURE_EVIDENCE')
    monkeypatch.setattr(cp, 'fresh', stale)
    with pytest.raises(OperatorBlocked, match='CURRENT_PROFILE_HOST_EVIDENCE_STALE'):
        cp.host_check(dict(sid='fixture', session_id=1), 'PREPARE', 0, [])


def test_post_cancel_host_failure_never_invokes_sdk(tmp_path, monkeypatch):
    _, native, child, phases = readonly_setup(tmp_path, monkeypatch)
    def checked(actor, phase, pid, paths):
        phases.append(phase)
        if len(phases) == 4:
            raise OperatorBlocked('CURRENT_PROFILE_HOST_EVIDENCE_STALE')
    monkeypatch.setattr(cp, 'host_check', checked)
    report = cp.readonly_audit(native_factory=lambda: pytest.fail('Native invoked after stale host'),
                               startup_ready=lambda: None)
    assert report['stage'] == 'POST_CANCEL_HOST_CHECK'
    assert report['blocker'] == 'CURRENT_PROFILE_HOST_EVIDENCE_STALE'
    assert report['broker_actions'] == 0 and native.initialize_calls == [] and child.stopped


def audit_cli():
    script = Path(__file__).resolve().parents[2] / 'scripts/p3_current_profile_audit.py'
    return runpy.run_path(str(script), run_name='fixture_audit_cli')


@pytest.mark.parametrize('confirmation', ['', 'CANCELLED', 'DEMO_LOGIN_COMPLETED'])
def test_manual_confirmation_requires_its_own_exact_token(monkeypatch, capsys, confirmation):
    helper = audit_cli()['manual_demo_confirmation']
    monkeypatch.setattr(sys, 'stdin', io.StringIO(confirmation))
    if confirmation == 'DEMO_LOGIN_COMPLETED':
        helper()
    else:
        with pytest.raises(OperatorBlocked, match='MANUAL_DEMO_LOGIN_NOT_CONFIRMED'):
            helper()
    assert 'No native SDK connection has started' in capsys.readouterr().out


@pytest.mark.parametrize('arguments', [
    ['--wait-for-manual-demo-login'],
    ['--audit', '--wait-for-manual-demo-login', '--wait-for-startup-cancel'],
])
def test_manual_cli_invalid_flags_do_not_access_operator_boundary(monkeypatch, arguments):
    cli = audit_cli()
    monkeypatch.setattr(sys, 'argv', ['fixture-audit', *arguments])
    monkeypatch.setattr(cp, 'readonly_audit', lambda **kwargs: pytest.fail('Operator boundary entered'))
    with pytest.raises(SystemExit) as error:
        cli['main']()
    assert error.value.code == 2


def test_manual_confirmation_does_not_replace_native_account_proof(tmp_path, monkeypatch):
    _, native, child, phases = readonly_setup(tmp_path, monkeypatch)
    native.a['trade_mode'] = native.ACCOUNT_TRADE_MODE_REAL
    report = cp.readonly_audit(native_factory=lambda: native, startup_ready=lambda: None,
                               startup_kind='MANUAL_DEMO_LOGIN')
    assert report['blocker'] == 'CURRENT_PROFILE_NATIVE_ACCOUNT_OR_TERMINAL_MISMATCH'
    assert len(native.initialize_calls) == 1 and phases[3] == 'READ'
    assert child.stopped and report['broker_actions'] == 0 and not cp.MARKER.exists()


def test_manual_host_failure_blocks_sdk(tmp_path, monkeypatch):
    _, native, child, phases = readonly_setup(tmp_path, monkeypatch)
    def checked(*args):
        phases.append('READ')
        if len(phases) == 4:
            raise OperatorBlocked('CURRENT_PROFILE_HOST_EVIDENCE_STALE')
    monkeypatch.setattr(cp, 'host_check', checked)
    report = cp.readonly_audit(native_factory=lambda: pytest.fail('Native invoked'),
                               startup_ready=lambda: None, startup_kind='MANUAL_DEMO_LOGIN')
    assert report['stage'] == 'POST_MANUAL_LOGIN_HOST_CHECK'
    assert report['blocker'] == 'CURRENT_PROFILE_HOST_EVIDENCE_STALE'
    assert child.stopped and not native.initialize_calls


def test_manual_handshake_without_callback_rejects_before_credentials(monkeypatch):
    monkeypatch.setattr(cp, '_load_private', lambda *args: pytest.fail('Credentials loaded'))
    with pytest.raises(OperatorBlocked, match='STARTUP_HANDSHAKE_INVALID'):
        cp.readonly_audit(startup_kind='MANUAL_DEMO_LOGIN')


def test_manual_cli_selects_only_manual_readonly_handshake(monkeypatch, capsys):
    cli = audit_cli()
    monkeypatch.setattr(sys, 'argv', ['fixture-audit', '--audit', '--wait-for-manual-demo-login'])
    calls = []
    def readonly(**kwargs):
        calls.append(kwargs)
        return dict(status='NOT_QUALIFIED', broker_execution='HARD_DISABLED', broker_actions=0)
    monkeypatch.setattr(cp, 'readonly_audit', readonly)
    assert cli['main']() == 2
    assert calls == [dict(startup_ready=cli['manual_demo_confirmation'], startup_kind='MANUAL_DEMO_LOGIN')]
    assert json.loads(capsys.readouterr().out)['broker_actions'] == 0
