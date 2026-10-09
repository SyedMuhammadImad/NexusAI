"""ADR-022 operator-only, read-only qualification. Imports never load credentials."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from pydantic import Field

from .ledger import DemoAccount, canonical, hashed
from .mt5_evidence import enum, integer, number, positive, record
from .native_operator import (CONFIG_PATH, PRIVATE, BASIS_PATH, COST_PATH,
                              OperatorSettings, StrictRecord, _load_private)
from .operator_bootstrap import ReadOnlyNativeAPI, collect_bootstrap
from .operator_verification import OperatorBlocked, REPOSITORY, VerificationLedger, _plain_path
from .safety import VERSION, Veto, fresh
from .safety_contracts import SafetyConfiguration

HOST_VERSION = 'p3-current-profile-host-v1'
PUBLIC_TERMINAL = Path('C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe')
HOST_SCRIPT = REPOSITORY / 'scripts/p3_current_profile_host.ps1'
TERMINAL = PRIVATE / 'current-profile-terminal-v1/terminal64.exe'
MARKER = REPOSITORY / '.p3-verification/current-profile-run.json'
TERMINAL_RECEIPT = REPOSITORY / '.p3-verification/current-profile-terminal.json'


def placeholder(value):
    return isinstance(value, str) and re.fullmatch(r'<[A-Z0-9_]+>', value) is not None


class SeedAccount(StrictRecord):
    account_id: str = Field(pattern=r'^[1-9][0-9]{0,19}$')
    server: str = Field(min_length=1)
    currency: str
    mode: str
    evidence_source: str


class BootstrapSettings(OperatorSettings):
    account: SeedAccount = Field(repr=False)

    def validate_seed(self):
        a = self.account
        if (a.mode != 'DEMO' or a.evidence_source != 'MT5_DEMO'
                or not a.server.strip() or a.server != a.server.strip() or placeholder(a.server)
                or not self.password.get_secret_value() or placeholder(self.password.get_secret_value())
                or self.policy_version != VERSION):
            raise OperatorBlocked('CURRENT_PROFILE_CONFIGURED_DEMO_BINDING_INVALID')
        if not placeholder(a.currency) and not re.fullmatch(r'[A-Z]{3}', a.currency):
            raise OperatorBlocked('CURRENT_PROFILE_CURRENCY_INVALID')
        # Identity-only validation: no placeholder currency is used for money/risk.
        SafetyConfiguration(approved_account_key='not-yet-attested',
                            authorized_sources={'current-profile-manual'}, instruments=self.symbols)


def _windows_environment():
    env = dict(os.environ)
    # PS7's inherited module path can prevent PS5 security cmdlet autoloading.
    env['PSModulePath'] = str(Path(os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/Modules')
    return env


def _powershell(script, payload=None):
    exe = Path(os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(exe), '-NoProfile', '-NonInteractive', '-File', str(script)],
                            input=json.dumps(payload) if payload else '', capture_output=True,
                            text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
                            env=_windows_environment())
    if result.returncode != 0:
        code = result.stderr.strip()
        if re.fullmatch(r'CURRENT_PROFILE_HOST_(IDENTITY|WORKER|TERMINALS|PATH_ANCESTORS|ACL_READ|ACL_OWNER|ACL_ENTRIES)_FAILED', code):
            raise OperatorBlocked(code)
        raise OperatorBlocked('CURRENT_PROFILE_HOST_METADATA_UNAVAILABLE')
    try:
        return json.loads(result.stdout)
    except Exception:
        raise OperatorBlocked('CURRENT_PROFILE_HOST_METADATA_INVALID') from None


def actor():
    value = _powershell(HOST_SCRIPT)
    if (set(value) != {'sid', 'session_id', 'non_admin'} or value['non_admin'] is not True
            or type(value['session_id']) is not int or value['session_id'] < 0
            or not isinstance(value['sid'], str) or not re.fullmatch(r'S-1-5-21-(\d+-){2}\d+-\d+', value['sid'])):
        raise OperatorBlocked('CURRENT_PROFILE_NONADMIN_IDENTITY_REQUIRED')
    return value


def validate_host(host, *, phase, terminal_pid):
    keys = {'version', 'current_identity', 'session_match', 'non_admin',
            'exclusive_terminal', 'protected_acl', 'terminal_pid'}
    if (not isinstance(host, dict) or set(host) != keys or host['version'] != HOST_VERSION
            or phase not in {'PREPARE', 'READ', 'EXECUTION'}
            or any(host[k] is not True for k in keys - {'version', 'terminal_pid'})
            or type(host['terminal_pid']) is not int or type(terminal_pid) is not int
            or host['terminal_pid'] != terminal_pid
            or (phase == 'PREPARE' and terminal_pid != 0)
            or (phase != 'PREPARE' and terminal_pid <= 0)):
        raise OperatorBlocked('CURRENT_PROFILE_HOST_NOT_QUALIFIED')
    return host


def host_check(owner, phase, terminal_pid, paths):
    start = datetime.now(timezone.utc)
    host = _powershell(HOST_SCRIPT, dict(actor_sid=owner['sid'], session_id=owner['session_id'],
        python_exe=sys._base_executable, python_pid=os.getpid(), terminal_exe=str(TERMINAL),
        terminal_pid=terminal_pid, phase=phase, protected_paths=[str(p) for p in paths]))
    try:
        fresh(start, datetime.now(timezone.utc), 5)
    except Veto:
        raise OperatorBlocked('CURRENT_PROFILE_HOST_EVIDENCE_STALE') from None
    return validate_host(host, phase=phase, terminal_pid=terminal_pid)


@contextmanager
def worker_lease():
    # Windows kernel lock excludes another cooperative worker, including after crash.
    import msvcrt
    root = REPOSITORY / '.p3-verification'
    _plain_path(root)
    root.mkdir(exist_ok=True)
    path = root / 'current-profile-worker.lock'
    _plain_path(path)
    if path.exists() and path.stat().st_nlink != 1:
        raise OperatorBlocked('CURRENT_PROFILE_WORKER_LOCK_LINKED')
    with path.open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise OperatorBlocked('CURRENT_PROFILE_WORKER_ALREADY_ACTIVE') from None
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def attested_settings(seed, client, owner, digest, *, current):
    """Derive placeholder metadata only after exact native DEMO login/server proof."""
    a = record(client.account_info(), ('login', 'server', 'currency', 'trade_mode',
        'margin_mode', 'company', 'leverage', 'balance', 'equity', 'margin', 'trade_allowed', 'trade_expert'))
    t = record(client.terminal_info(), ('path', 'data_path', 'company', 'build',
        'connected', 'trade_allowed', 'tradeapi_disabled'))
    if (str(integer(a['login'], 1)) != seed.account.account_id or a['server'] != seed.account.server
            or enum(client, a['trade_mode'], ['ACCOUNT_TRADE_MODE_DEMO', 'ACCOUNT_TRADE_MODE_REAL',
                                            'ACCOUNT_TRADE_MODE_CONTEST']) != 'ACCOUNT_TRADE_MODE_DEMO'
            or t['connected'] is not True or Path(t['path']) != TERMINAL.parent
            or Path(t['data_path']) != TERMINAL.parent):
        raise OperatorBlocked('CURRENT_PROFILE_NATIVE_ACCOUNT_OR_TERMINAL_MISMATCH')
    integer(a['leverage'], 1)
    integer(t['build'], 1)
    positive(a['balance']); positive(a['equity']); number(a['margin'], 0)
    for expected, value in ((seed.account.currency, a['currency']),
                            (seed.broker_company, a['company']), (seed.terminal_company, t['company'])):
        if not isinstance(value, str) or not value or (not placeholder(expected) and expected != value):
            raise OperatorBlocked('CURRENT_PROFILE_NATIVE_METADATA_MISMATCH')
    binding = DemoAccount(account_id=seed.account.account_id, server=seed.account.server,
                          currency=a['currency'], evidence_source='MT5_DEMO')
    body = seed.model_dump()
    body.update(account=binding, terminal_exe=str(TERMINAL), terminal_sha256=digest,
                service_sid=owner['sid'], broker_company=a['company'], terminal_company=t['company'],
                source_id='current-profile-manual' if placeholder(seed.source_id) else seed.source_id,
                host_attestation='LOCAL')
    settings = OperatorSettings.model_validate(body)
    settings.validate_operator()
    # Do not express current-profile evidence as legacy session-zero/dedicated flags.
    safe = dict(account='ATTESTED_DEMO', account_match=True, server_match=True,
                currency=binding.currency, balance=str(number(a['balance'])), equity=str(number(a['equity'])),
                leverage=a['leverage'], terminal_build=t['build'], account_key=binding.key,
                account_trade_allowed=a['trade_allowed'], account_expert_allowed=a['trade_expert'],
                terminal_trade_allowed=t['trade_allowed'], external_trade_api_disabled=t['tradeapi_disabled'],
                observed_at=current.isoformat(), host_model='COOPERATIVE_CURRENT_PROFILE_ADR_022')
    return settings, safe


def audit_ledger(settings):
    _plain_path(MARKER)
    if MARKER.exists():
        if MARKER.stat().st_nlink != 1 or MARKER.stat().st_size > 4096:
            raise OperatorBlocked('CURRENT_PROFILE_RUN_MARKER_INVALID')
        value = json.loads(MARKER.read_text(encoding='utf-8'))
        if set(value) != {'version', 'account_key', 'run_id'} or value['version'] != 'current-profile-v1' or value['account_key'] != settings.account.key:
            raise OperatorBlocked('CURRENT_PROFILE_RUN_BINDING_MISMATCH')
        return VerificationLedger.resume(value['run_id'], settings.account)
    ledger = VerificationLedger.create(settings.account, workspace=REPOSITORY)
    with MARKER.open('x', encoding='utf-8') as handle:
        handle.write(canonical(dict(version='current-profile-v1', account_key=settings.account.key,
                                    run_id=ledger.path.parent.name)))
        handle.flush(); os.fsync(handle.fileno())
    return ledger


def terminal_receipt(seed, owner, digest):
    """Bind pristine provisioning before launch, including failed read-only startup."""
    _plain_path(TERMINAL_RECEIPT)
    expected = dict(version='current-profile-terminal-v1', terminal_exe=str(TERMINAL),
        terminal_sha256=digest, actor_sid=owner['sid'], configured_binding=hashed(dict(
            account_id=seed.account.account_id, server=seed.account.server, mode='DEMO')))
    if TERMINAL_RECEIPT.exists():
        if TERMINAL_RECEIPT.stat().st_nlink != 1 or TERMINAL_RECEIPT.stat().st_size > 4096:
            raise OperatorBlocked('CURRENT_PROFILE_TERMINAL_RECEIPT_INVALID')
        try:
            actual = json.loads(TERMINAL_RECEIPT.read_text(encoding='utf-8'))
        except Exception:
            raise OperatorBlocked('CURRENT_PROFILE_TERMINAL_RECEIPT_INVALID') from None
        if actual != expected:
            raise OperatorBlocked('CURRENT_PROFILE_TERMINAL_RECEIPT_MISMATCH')
    else:
        if {p.name for p in TERMINAL.parent.iterdir()} != {'terminal64.exe'}:
            raise OperatorBlocked('CURRENT_PROFILE_TERMINAL_NOT_PRISTINE')
        with TERMINAL_RECEIPT.open('x', encoding='utf-8') as handle:
            handle.write(canonical(expected))
            handle.flush(); os.fsync(handle.fileno())


def connection_failure(client):
    """Never publish native descriptions, which may contain account/path details."""
    codes = {-6: 'CURRENT_PROFILE_AUTHENTICATION_FAILED', -5: 'CURRENT_PROFILE_SDK_VERSION_UNSUPPORTED',
        -2: 'CURRENT_PROFILE_CONNECTION_PARAMETERS_INVALID', -10000: 'CURRENT_PROFILE_IPC_FAILED',
        -10001: 'CURRENT_PROFILE_IPC_SEND_FAILED', -10002: 'CURRENT_PROFILE_IPC_RECEIVE_FAILED',
        -10003: 'CURRENT_PROFILE_IPC_INITIALIZATION_FAILED', -10005: 'CURRENT_PROFILE_IPC_TIMEOUT'}
    try:
        value = client.last_error()
        code = value[0] if isinstance(value, tuple) and len(value) == 2 and type(value[0]) is int else None
    except Exception:
        code = None
    return codes.get(code, 'CURRENT_PROFILE_CONNECTION_FAILED')


def readonly_audit(*, native_factory=None, startup_ready=None, startup_kind='CANCEL'):
    """Explicit operator call. No order API, HALT reset or default-app composition."""
    if os.name != 'nt':
        raise OperatorBlocked('CURRENT_PROFILE_WINDOWS_REQUIRED')
    if startup_kind not in {'CANCEL', 'MANUAL_DEMO_LOGIN'} or (
            startup_kind == 'MANUAL_DEMO_LOGIN' and startup_ready is None):
        raise OperatorBlocked('CURRENT_PROFILE_STARTUP_HANDSHAKE_INVALID')
    seed = _load_private(CONFIG_PATH, BootstrapSettings)
    seed.validate_seed()
    owner = actor()
    stage = 'PREPARE'
    client = None
    terminal = None
    report = dict(status='NOT_QUALIFIED', broker_execution='HARD_DISABLED', live='LOCKED',
                  broker_actions=0, broker_connected=False, risk_initialization='NOT_PROVEN',
                  cost_evidence='COST_UNVERIFIED', qualification='NOT_QUALIFIED')
    with worker_lease():
        paths = [PRIVATE, CONFIG_PATH, REPOSITORY / '.p3-verification']
        host_check(owner, 'PREPARE', 0, paths)
        _plain_path(TERMINAL)
        if not TERMINAL.parent.exists():
            _plain_path(PUBLIC_TERMINAL)
            # Authenticode validation occurs before copying the fixed public installation.
            exe = Path(os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            check = subprocess.run([str(exe), '-NoProfile', '-NonInteractive', '-Command',
                r"$s=Get-AuthenticodeSignature -LiteralPath 'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe';"
                "if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'MetaQuotes'){exit 2}"],
                capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
                env=_windows_environment())
            if check.returncode != 0:
                raise OperatorBlocked('CURRENT_PROFILE_TERMINAL_SIGNATURE_UNPROVEN')
            TERMINAL.parent.mkdir(exist_ok=False)
            shutil.copyfile(PUBLIC_TERMINAL, TERMINAL)
        if not TERMINAL.is_file() or TERMINAL.stat().st_nlink != 1:
            raise OperatorBlocked('CURRENT_PROFILE_TERMINAL_INVALID')
        with TERMINAL.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        with PUBLIC_TERMINAL.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != digest:
                raise OperatorBlocked('CURRENT_PROFILE_TERMINAL_BINARY_MISMATCH')
        # No adoption of an unproven existing terminal or a saved-account fallback.
        terminal_receipt(seed, owner, digest)
        paths.append(TERMINAL.parent)
        host_check(owner, 'PREPARE', 0, paths)
        try:
            stage = 'CONNECT'
            terminal = subprocess.Popen([str(TERMINAL), '/portable'], cwd=TERMINAL.parent,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(2)
            host_check(owner, 'READ', terminal.pid, paths)
            if startup_ready is not None:
                stage = ('STARTUP_MANUAL_DEMO_LOGIN_CONFIRMATION'
                         if startup_kind == 'MANUAL_DEMO_LOGIN' else 'STARTUP_CANCEL_CONFIRMATION')
                startup_ready()
                stage = ('POST_MANUAL_LOGIN_HOST_CHECK'
                         if startup_kind == 'MANUAL_DEMO_LOGIN' else 'POST_CANCEL_HOST_CHECK')
                host_check(owner, 'READ', terminal.pid, paths)
            stage = 'CONNECT'
            if native_factory is None:
                import MetaTrader5  # Operator-only after reviewed host/binary checks.
                native = MetaTrader5
            else:
                native = native_factory()
            client = ReadOnlyNativeAPI(native)
            if client.initialize(str(TERMINAL), login=int(seed.account.account_id),
                                 password=seed.password.get_secret_value(), server=seed.account.server,
                                 portable=True, timeout=60000) is not True:
                raise OperatorBlocked(connection_failure(client))
            report['broker_connected'] = True
            host_check(owner, 'READ', terminal.pid, paths)
            stage = 'ACCOUNT_ATTESTATION'
            settings, safe = attested_settings(seed, client, owner, digest, current=datetime.now(timezone.utc))
            report.update(safe)
            if (safe['account_trade_allowed'] is not True or safe['account_expert_allowed'] is not True
                    or safe['terminal_trade_allowed'] is not True or safe['external_trade_api_disabled'] is not False):
                raise OperatorBlocked('CURRENT_PROFILE_ALGO_PERMISSION_NOT_PROVEN')
            ledger = audit_ledger(settings)
            ledger.halt('CURRENT_PROFILE_READONLY_QUALIFICATION')
            paths.append(ledger.path.parent)
            host_check(owner, 'READ', terminal.pid, paths)
            stage = 'HISTORY_AND_METADATA'
            for symbol in settings.symbols:
                if client.symbol_select(symbol, True) is not True:
                    raise OperatorBlocked('CURRENT_PROFILE_SYMBOL_UNAVAILABLE')
            basis, evidence = collect_bootstrap(settings, ledger, client)
            report.update(evidence)
            stage = 'FINAL_HOST_CHECK'
            host_check(owner, 'READ', terminal.pid, paths)
            with ledger.transaction() as conn:
                ledger.audit(conn, 'CURRENT_PROFILE_READONLY_AUDIT', None, report)
            # No fabricated cost evidence or execution unlock follows from a clean bootstrap.
            report.update(status='READONLY_AUDIT_COMPLETE', qualification='NOT_QUALIFIED',
                          broker_execution='HARD_DISABLED', commission='UNVERIFIED')
            return report
        except Exception as error:
            code = str(error) if isinstance(error, OperatorBlocked) else 'CURRENT_PROFILE_NATIVE_EVIDENCE_NOT_QUALIFIED'
            if not re.fullmatch(r'[A-Z0-9_]+', code):
                code = 'CURRENT_PROFILE_NATIVE_EVIDENCE_NOT_QUALIFIED'
            return dict(report, stage=stage, blocker=code)
        finally:
            try:
                if client is not None:
                    client.shutdown()
            finally:
                # This read-only worker has no position close API. Stop only its own child.
                if terminal is not None and terminal.poll() is None:
                    terminal.terminate()
                    terminal.wait(timeout=15)
