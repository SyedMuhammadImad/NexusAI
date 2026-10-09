"""ADR-020 tests use native-shaped fixtures only; no secrets or native imports."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from core.rebuild import operator_verification
from core.rebuild.host_attestation import validate_bootstrap_receipt, validate_receipt
from core.rebuild.operator_bootstrap import ReadOnlyNativeAPI, collect_bootstrap
from core.rebuild.operator_verification import OperatorBlocked, VerificationLedger
from test_p3_native_evidence import Native, binding, deal_record, order_record
from test_p2_safety import TIME


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(operator_verification, 'REPOSITORY', tmp_path)
    ledger = VerificationLedger.create(binding(), workspace=tmp_path)
    client = Native()
    client.a.update(company='fixture-broker', leverage=100)
    client.t.update(company='fixture-terminal', path=str(tmp_path), data_path=str(tmp_path), build=1)
    settings = SimpleNamespace(account=binding(), symbols={'XAUUSDm', 'XAGUSDm', 'USOILm'},
                               terminal_exe=str(tmp_path / 'terminal64.exe'))
    return settings, ledger, client


def receipt(phase='BOOTSTRAP_PREPARE', terminal_pid=0):
    return dict(version='p3-bootstrap-attestor-v1', phase=phase, nonce='a' * 32,
                account_key='fixture', run_id='fixture-run', python_pid=12,
                started_at=TIME.isoformat(), completed_at=TIME.isoformat(),
                host=dict(dedicated_identity=True, session_zero=True, non_admin=True,
                          exclusive_processes=True, protected_acl=True, terminal_pid=terminal_pid))


def kwargs():
    return dict(nonce='a' * 32, account_key='fixture', run_id='fixture-run', python_pid=12, current=TIME)


def test_bootstrap_receipt_cannot_be_used_as_execution_receipt():
    r = receipt()
    assert validate_bootstrap_receipt(r, phase='BOOTSTRAP_PREPARE', **kwargs())['terminal_pid'] == 0
    with pytest.raises(OperatorBlocked):
        validate_receipt(r, **kwargs())


@pytest.mark.parametrize('change', ['phase', 'account', 'terminal', 'owner', 'stale'])
def test_bootstrap_attestation_rejects_wrong_binding_or_isolation(change):
    r = receipt()
    if change == 'phase': r['phase'] = 'BOOTSTRAP_READ'
    if change == 'account': r['account_key'] = 'other'
    if change == 'terminal': r['host']['terminal_pid'] = 99
    if change == 'owner': r['host']['exclusive_processes'] = False
    if change == 'stale': r['started_at'] = (TIME - timedelta(seconds=6)).isoformat()
    with pytest.raises(OperatorBlocked):
        validate_bootstrap_receipt(r, phase='BOOTSTRAP_PREPARE', **kwargs())


@pytest.mark.parametrize('method', ['order_send', 'order_check', 'login', 'market_book_add'])
def test_readonly_facade_has_no_economic_or_account_switch_api(method):
    with pytest.raises(OperatorBlocked):
        getattr(ReadOnlyNativeAPI(Native()), method)


def test_unused_account_initializes_without_commission_invention_or_execution(tmp_path, monkeypatch):
    settings, ledger, client = fixture(tmp_path, monkeypatch)
    client.ds = [deal_record(type=client.DEAL_TYPE_BALANCE, order=0, position_id=0,
                             volume=0, price=0, profit=100000, symbol='')]
    basis, report = collect_bootstrap(settings, ledger, ReadOnlyNativeAPI(client), clock=lambda: TIME)
    assert basis.cash_flow_total == 100000 and basis.high_water_equity == 100000
    assert report['commission'] == 'UNVERIFIED'
    assert report['trading_authorized'] is False and report['broker_actions'] == 0
    with ledger.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM p3_attempts').fetchone()[0] == 0
        assert conn.execute('SELECT state FROM halt_state').fetchone()[0] == 'HALTED'
        count = conn.execute('SELECT COUNT(*) FROM p3_observations').fetchone()[0]
    again, _ = collect_bootstrap(settings, ledger, ReadOnlyNativeAPI(client), clock=lambda: TIME)
    assert again == basis
    with ledger.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM p3_observations').fetchone()[0] == count


@pytest.mark.parametrize('change', ['real', 'account', 'inventory', 'history', 'cashflow', 'terminal'])
def test_bad_native_evidence_never_initializes_baselines(tmp_path, monkeypatch, change):
    settings, ledger, client = fixture(tmp_path, monkeypatch)
    if change == 'real': client.a['trade_mode'] = client.ACCOUNT_TRADE_MODE_REAL
    if change == 'account': client.a['login'] = 999
    if change == 'inventory': client.pending = [SimpleNamespace(**order_record())]
    if change == 'history': client.ds = None
    if change == 'cashflow': client.ds = [deal_record(type=client.DEAL_TYPE_CHARGE, order=0, position_id=0, volume=0, price=0)]
    if change == 'terminal': client.t['data_path'] = 'other-terminal'
    with pytest.raises((OperatorBlocked, ValueError)):
        collect_bootstrap(settings, ledger, ReadOnlyNativeAPI(client), clock=lambda: TIME)
    with ledger.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM p3_attempts').fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='P3_QUALIFICATION_BASELINE'").fetchone()[0] == 0
