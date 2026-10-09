"""ADR-020 operator-only evidence collection. No submission or HALT-reset path."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from .broker_observations import ObservationJournal
from .host_attestation import validate_bootstrap_receipt
from .ledger import canonical, hashed
from .mt5_evidence import NativeEvidenceReader, account, number, positive, record
from .native_operator import BASIS_PATH, CONFIG_PATH, COST_PATH, OperatorBlocked, load_settings
from .operator_verification import REPOSITORY, VerificationLedger, _plain_path
from .qualification_basis import EPOCH, QualificationEvidence, qualification_basis
from .safety import fresh


class ReadOnlyNativeAPI:
    METHODS = frozenset({'initialize', 'shutdown', 'last_error', 'account_info', 'terminal_info',
                         'history_orders_get', 'history_deals_get', 'orders_get',
                         'positions_get', 'symbol_info', 'symbol_info_tick', 'symbol_select'})

    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        if name in self.METHODS or name.startswith(('ACCOUNT_', 'SYMBOL_', 'ORDER_', 'DEAL_', 'POSITION_')):
            if name.lower() in {'order_send', 'order_check'}:
                raise OperatorBlocked('BOOTSTRAP_ECONOMIC_API_FORBIDDEN')
            value = getattr(self._client, name)
            if name not in self.METHODS and type(value) is not int:
                raise OperatorBlocked('BOOTSTRAP_UNEXPECTED_NATIVE_ATTRIBUTE')
            return value
        raise OperatorBlocked('BOOTSTRAP_ECONOMIC_API_FORBIDDEN')


def bootstrap_host(settings, ledger, phase):
    nonce = uuid.uuid4().hex
    payload = dict(nonce=nonce, account_key=settings.account.key, run_id=ledger.path.parent.name,
                   python_pid=os.getpid(), service_sid=settings.service_sid, phase=phase)
    exe = Path(os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(exe), '-NoProfile', '-NonInteractive', '-ExecutionPolicy',
                             'RemoteSigned', '-File', str(REPOSITORY / 'scripts/p3_attestor_client.ps1')],
                            input=json.dumps(payload), capture_output=True, text=True, timeout=6,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        raise OperatorBlocked('BOOTSTRAP_HOST_ATTESTOR_UNAVAILABLE')
    try:
        return validate_bootstrap_receipt(json.loads(result.stdout), phase=phase,
            nonce=nonce, account_key=settings.account.key, run_id=ledger.path.parent.name,
            python_pid=os.getpid(), current=datetime.now(timezone.utc))
    except Exception:
        raise OperatorBlocked('BOOTSTRAP_HOST_ATTESTATION_FAILED') from None


def bootstrap_ledger(settings):
    marker = REPOSITORY / '.p3-verification/bootstrap-marker.json'
    _plain_path(marker)
    if marker.exists():
        value = json.loads(marker.read_text(encoding='utf-8'))
        if set(value) != {'version', 'account_key', 'run_id'} or value['version'] != 'p3-bootstrap-v1' or value['account_key'] != settings.account.key:
            raise OperatorBlocked('BOOTSTRAP_MARKER_MISMATCH')
        return VerificationLedger.resume(value['run_id'], settings.account)
    ledger = VerificationLedger.create(settings.account)
    with marker.open('x', encoding='utf-8') as handle:
        handle.write(canonical(dict(version='p3-bootstrap-v1', account_key=settings.account.key,
                                    run_id=ledger.path.parent.name)))
        handle.flush()
        os.fsync(handle.fileno())
    return ledger


def collect_bootstrap(settings, ledger, client, *, clock=lambda: datetime.now(timezone.utc)):
    """Already connected injected read-only session; fixture-safe normalization and persistence."""
    now = clock()
    a, t = client.account_info(), client.terminal_info()
    attestation, raw = account(client, a, t, settings.account, ledger.path.parent.name, now)
    company = record(a, ('company', 'leverage'))
    terminal = record(t, ('company', 'path', 'data_path', 'build'))
    if not isinstance(company['company'], str) or not company['company'] or type(company['leverage']) is not int or company['leverage'] <= 0:
        raise OperatorBlocked('BOOTSTRAP_ACCOUNT_METADATA_INVALID')
    root = Path(settings.terminal_exe).parent
    if Path(terminal['path']) != root or Path(terminal['data_path']) != root or type(terminal['build']) is not int or terminal['build'] <= 0:
        raise OperatorBlocked('BOOTSTRAP_TERMINAL_IDENTITY_MISMATCH')
    reader = NativeEvidenceReader(settings.account, symbols=settings.symbols, context_provider=None, clock=clock)
    batch = reader(client, EPOCH, attestation)
    observations = batch['native_observations']
    with ledger.transaction() as conn:
        if conn.execute('SELECT state FROM halt_state WHERE singleton=1').fetchone()[0] != 'HALTED':
            raise OperatorBlocked('BOOTSTRAP_HALT_REQUIRED')
        ObservationJournal(settings.account.key).append(conn, observations)
        ambiguous = conn.execute("SELECT 1 FROM p3_observation_heads WHERE account_key=? AND state='AMBIGUOUS' LIMIT 1",
                                 (settings.account.key,)).fetchone() is not None
        ledger.audit(conn, 'P3_READONLY_BOOTSTRAP', None,
                     dict(version='p3-bootstrap-v1', observation_ids=[o.observation_id for o in observations]))
    if ambiguous or any(o.error for o in observations):
        raise OperatorBlocked('BOOTSTRAP_NATIVE_EVIDENCE_INVALID')
    groups = {kind: [o for o in observations if o.broker_entity_type == kind]
              for kind in ('ACCOUNT', 'INVENTORY', 'ORDER', 'DEAL', 'POSITION', 'SYMBOL', 'QUOTE')}
    raw = groups['ACCOUNT'][0].normalized_payload
    inventory = groups['INVENTORY'][0]
    trades = [o for o in groups['DEAL'] if o.normalized_payload['native_type'] in {'DEAL_TYPE_BUY', 'DEAL_TYPE_SELL'}]
    if groups['ORDER'] or groups['POSITION'] or trades:
        with ledger.transaction() as conn:
            ledger.audit(conn, 'P3_BOOTSTRAP_EXTERNAL_ENTITIES_QUARANTINED', None,
                         dict(observation_ids=[o.observation_id for o in groups['ORDER'] + groups['POSITION'] + trades]))
        raise OperatorBlocked('BOOTSTRAP_ACCOUNT_NOT_UNUSED')
    if any(o.normalized_payload['native_type'] not in {'DEAL_TYPE_BALANCE', 'DEAL_TYPE_CREDIT'} for o in groups['DEAL']):
        raise OperatorBlocked('BOOTSTRAP_CASH_FLOW_UNSUPPORTED')
    flow = sum((sum(number(o.normalized_payload[k]) for k in ('profit', 'commission', 'swap', 'fee'))
                for o in groups['DEAL']), number(0))
    fresh(batch['observed_at'], clock(), 5)
    evidence = QualificationEvidence(attestation=batch['attestation'], observed_at=batch['observed_at'],
        equity=positive(raw['equity']), history_from=EPOCH, history_complete=True,
        history_evidence_id=hashed([o.observation_id for o in groups['ORDER'] + groups['DEAL']]),
        ever_traded=False, inventory_complete=inventory.normalized_payload['complete'],
        inventory_evidence_id=inventory.observation_id,
        open_position_ids=tuple(inventory.normalized_payload['positions']),
        pending_order_ids=tuple(inventory.normalized_payload['orders']), cash_flow_total=flow,
        cash_flow_evidence_id=hashed([o.observation_id for o in groups['DEAL']]))
    basis = qualification_basis(ledger, evidence, current=clock())
    return basis, dict(account='ATTESTED_DEMO', history='BROKER_API_COMPLETE', inventory='EMPTY',
        balance=str(number(raw['balance'])), equity=str(number(raw['equity'])),
        broker_company=company['company'], terminal_company=terminal['company'], leverage=company['leverage'],
        symbols={o.broker_entity_id: o.normalized_payload for o in groups['SYMBOL']},
        quotes={o.broker_entity_id: o.normalized_payload for o in groups['QUOTE']},
        observation_count=len(observations), run_id=ledger.path.parent.name,
        risk_initialization='QUALIFICATION_START_PROVEN', commission='UNVERIFIED',
        broker_actions=0, trading_authorized=False)


def native_bootstrap():
    settings = load_settings()
    if settings.host_attestation != 'SYSTEM_FILES':
        raise OperatorBlocked('BOOTSTRAP_PRIVILEGED_ATTESTOR_REQUIRED')
    ledger = bootstrap_ledger(settings)
    bootstrap_host(settings, ledger, 'BOOTSTRAP_PREPARE')
    root = Path(settings.terminal_exe).parent
    if {p.name for p in root.iterdir()} != {Path(settings.terminal_exe).name}:
        raise OperatorBlocked('BOOTSTRAP_TERMINAL_NOT_PRISTINE')
    with Path(settings.terminal_exe).open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != settings.terminal_sha256:
            raise OperatorBlocked('BOOTSTRAP_TERMINAL_BINARY_MISMATCH')
    terminal = subprocess.Popen([settings.terminal_exe, '/portable'], cwd=root,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW)
    client = None
    try:
        time.sleep(2)
        host = bootstrap_host(settings, ledger, 'BOOTSTRAP_READ')
        if host['terminal_pid'] != terminal.pid:
            raise OperatorBlocked('BOOTSTRAP_TERMINAL_PID_MISMATCH')
        import MetaTrader5  # Approved operator boundary only, after host validation.
        client = ReadOnlyNativeAPI(MetaTrader5)
        if client.initialize(settings.terminal_exe, login=int(settings.account.account_id),
            server=settings.account.server, password=settings.password.get_secret_value(), portable=True) is not True:
            raise OperatorBlocked('BOOTSTRAP_CONNECTION_FAILED')
        bootstrap_host(settings, ledger, 'BOOTSTRAP_READ')
        # Selection changes only the isolated market-watch view, never an order.
        account(client, client.account_info(), client.terminal_info(), settings.account,
                ledger.path.parent.name, datetime.now(timezone.utc))
        for symbol in settings.symbols:
            if client.symbol_select(symbol, True) is not True:
                raise OperatorBlocked('BOOTSTRAP_SYMBOL_UNAVAILABLE')
        basis, report = collect_bootstrap(settings, ledger, client)
        _plain_path(BASIS_PATH)
        # Never overwrite another producer's evidence or silently refresh an old account.
        if BASIS_PATH.exists():
            raise OperatorBlocked('BOOTSTRAP_RISK_FILE_ALREADY_EXISTS')
        with BASIS_PATH.open('x', encoding='utf-8') as handle:
            handle.write(basis.model_dump_json())
            handle.flush()
            os.fsync(handle.fileno())
        return report
    finally:
        if client is not None:
            client.shutdown()
        # No position close/cancel exists here. Preserve terminal state for operator review.
