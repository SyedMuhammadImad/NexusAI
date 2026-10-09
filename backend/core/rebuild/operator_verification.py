"""Operator-only one-shot composition. No credential loading or native connection.

An injected isolation verifier is trusted operator code, not a JSON permission.
No machine-specific verifier/connector is supplied: the default cannot connect.
Fixture acceptance of this contract does not qualify a terminal or VM.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
from typing import Protocol
from uuid import UUID, uuid4

from .execution import ExecutionEngine
from .execution_contracts import Attestation
from .ledger import DemoAccount, Ledger, canonical
from .safety import fresh, number


RUN_EVENT = 'p3-operator-run-v1'
USE_EVENT = 'p3-operator-single-use-v1'
REPOSITORY = Path(__file__).resolve().parents[3]


class OperatorBlocked(ValueError):
    """Fixed public codes only; never relay operator/transport exception text."""


class IsolationVerifier(Protocol):
    def require_safe(self, account, session_id, directory, phase) -> str:
        """Return an opaque evidence ID or raise, WITHOUT connecting to MT5.

        Must independently qualify exact allowed demo binding, exclusive terminal
        ownership/no live route, approved credential locations, context provider,
        isolated filesystem ownership and the stop procedure. Recheck lease health
        on every call. A configuration flag is not implementation of this contract.
        """


def preflight():
    return dict(operator_path='NOT_QUALIFIED', demo_verification='NOT_RUN',
                blocker='MACHINE_ISOLATION_VERIFIER_AND_OPERATOR_CONTEXT_NOT_QUALIFIED',
                broker_actions=0, secrets='NONE')


def _plain_path(path):
    # Refuse existing symlink/junction/reparse ancestors before resolving or opening.
    for part in reversed((path, *path.parents)):
        if part.is_symlink() or part.is_junction():
            raise OperatorBlocked('LINKED_VERIFICATION_PATH')
        if part.exists():
            info = part.lstat()
            if getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise OperatorBlocked('REPARSE_VERIFICATION_PATH')


class VerificationLedger(Ledger):
    """Fresh fixed-location ledger, never an arbitrary user-selected SQLite file.

    File identity checks catch replacement/links, not hostile concurrent OS access.
    Exclusive filesystem ownership is still part of the external isolation lease.
    """
    @classmethod
    def create(cls, account, *, workspace=REPOSITORY):
        account = DemoAccount.model_validate(account.model_dump())
        workspace = Path(workspace).absolute()
        if account.evidence_source != 'FIXTURE' and workspace != REPOSITORY:
            raise OperatorBlocked('NATIVE_WORKSPACE_NOT_ALLOWED')
        _plain_path(workspace)
        root = workspace / '.p3-verification'
        _plain_path(root)
        root.mkdir(exist_ok=True)
        directory = root / str(uuid4())
        directory.mkdir(exist_ok=False)
        path = directory / 'ledger.sqlite3'
        with path.open('xb'):
            pass
        info = path.stat()
        identity = (info.st_dev, info.st_ino)
        result = cls(path, account=account, identity=identity)
        marker = dict(version=1, run_id=directory.name, account_key=account.key,
                      device=identity[0], inode=identity[1])
        with result.transaction() as conn:
            conn.execute('INSERT INTO audit_events(event_id,event_type,payload,timestamp) VALUES(?,?,?,?)',
                         (RUN_EVENT, 'P3_OPERATOR_RUN', canonical(marker), datetime.now(timezone.utc).isoformat()))
        result.halt('P3_NEW_VERIFICATION_RUN_NOT_AUTHORIZED')
        with (directory / 'run.json').open('x', encoding='utf-8') as handle:
            handle.write(canonical(marker))
        return result

    @classmethod
    def resume(cls, run_id, account, *, workspace=REPOSITORY):
        account = DemoAccount.model_validate(account.model_dump())
        if str(UUID(run_id)) != run_id:
            raise OperatorBlocked('INVALID_RUN_ID')
        workspace = Path(workspace).absolute()
        if account.evidence_source != 'FIXTURE' and workspace != REPOSITORY:
            raise OperatorBlocked('NATIVE_WORKSPACE_NOT_ALLOWED')
        directory = workspace / '.p3-verification' / run_id
        _plain_path(directory / 'run.json')
        marker = json.loads((directory / 'run.json').read_text(encoding='utf-8'))
        if (set(marker) != {'version','run_id','account_key','device','inode'} or
                marker['version'] != 1 or marker['run_id'] != run_id or marker['account_key'] != account.key):
            raise OperatorBlocked('RUN_BINDING_MISMATCH')
        result = cls(directory / 'ledger.sqlite3', account=account,
                     identity=(marker['device'], marker['inode']))
        with result.connect() as conn:
            row = conn.execute('SELECT payload FROM audit_events WHERE event_id=?', (RUN_EVENT,)).fetchone()
            if not row or json.loads(row[0]) != marker:
                raise OperatorBlocked('RUN_EVIDENCE_MISMATCH')
        return result

    def __init__(self, path, *, account, identity):
        self._identity = identity
        self._scope = account.evidence_source
        self.path = Path(path).absolute()
        self.check_path()
        super().__init__(path, account=account)

    def check_path(self):
        if (self.path.name != 'ledger.sqlite3' or self.path.parent.parent.name != '.p3-verification'
                or str(UUID(self.path.parent.name)) != self.path.parent.name
                or self._scope != 'FIXTURE' and self.path.parents[2] != REPOSITORY):
            raise OperatorBlocked('VERIFICATION_LAYOUT_REQUIRED')
        _plain_path(self.path)
        info = self.path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                (info.st_dev, info.st_ino) != self._identity):
            raise OperatorBlocked('VERIFICATION_FILE_IDENTITY_CHANGED')
        for suffix in ('-journal', '-wal', '-shm'):
            sidecar = Path(str(self.path) + suffix)
            _plain_path(sidecar)
            if sidecar.exists() and (not sidecar.is_file() or sidecar.stat().st_nlink != 1):
                raise OperatorBlocked('LINKED_VERIFICATION_SIDECAR')

    @contextmanager
    def connect(self):
        self.check_path()
        with super().connect() as conn:
            yield conn


class _GuardedBroker:
    def __init__(self, broker, check, account, session_id, clock):
        self._broker, self._check = broker, check
        self.account, self.session_id, self.clock = account, session_id, clock
        self.scope = account.evidence_source
        if broker.scope != self.scope:
            raise OperatorBlocked('OPERATOR_BROKER_SCOPE_MISMATCH')

    @property
    def observations(self):
        return getattr(self._broker, 'observations', ())

    def attest(self):
        self._check('ATTEST')
        value = self._broker.attest()
        a = Attestation.model_validate(value.model_dump() if isinstance(value, Attestation) else value)
        if ((a.account_key,a.account_id,a.server,a.currency,a.scope,a.session_id) !=
                (self.account.key,self.account.account_id,self.account.server,self.account.currency,self.scope,self.session_id)
                or not all((a.connected,a.trade_allowed,a.expert_allowed,a.hedging))):
            raise OperatorBlocked('OPERATOR_ACCOUNT_MISMATCH')
        fresh(a.observed_at, self.clock(), 5)
        self._check('ATTEST_RETURN')
        return a

    def snapshot(self, since):
        self.attest()
        result = self._broker.snapshot(since)
        self.attest()
        return result

    def submit(self, command):
        self.attest()
        if (command.get('minimum_volume_only') is not True or
                command.get('account_key') != self.account.key or command.get('session_id') != self.session_id):
            raise OperatorBlocked('INVALID_OPERATOR_COMMAND')
        self._check('SEND')
        return self._broker.submit(command)


class _MinimumVolumeEngine(ExecutionEngine):
    def _gate(self, conn, attempt, snapshot, *, begun=False):
        command = super()._gate(conn, attempt, snapshot, begun=begun)
        signal = json.loads(conn.execute('SELECT s.payload FROM signals s JOIN order_intents i ON i.signal_id=s.signal_id WHERE i.intent_id=?',
                                         (attempt['intent_id'],)).fetchone()[0])
        if signal['source_type'] != 'MANUAL' or command['entry_type'] != 'MARKET':
            raise OperatorBlocked('SMOKE_REQUIRES_MANUAL_MARKET')
        meta = snapshot.safety.instruments[command['symbol']]
        if number(command['volume']) != meta.volume_min:
            raise OperatorBlocked('SMOKE_REQUIRES_EXACT_MINIMUM_VOLUME')
        if len(snapshot.safety.account.exposures):
            raise OperatorBlocked('SMOKE_REQUIRES_EMPTY_ACCOUNT')
        command['minimum_volume_only'] = True
        return command


class OperatorVerification:
    """One request per isolated ledger. Requires a separately qualified connector.

    No implicit HALT reset, source generation, sizing override, reconnect or close.
    Never pass an ordinary/operator historical Ledger here.
    """
    def __init__(self, safety, *, session_id, isolation=None, clock=None):
        if not isinstance(safety.ledger, VerificationLedger):
            raise OperatorBlocked('ISOLATED_VERIFICATION_LEDGER_REQUIRED')
        if safety.ledger.account.key != safety.config.approved_account_key:
            raise OperatorBlocked('OPERATOR_ACCOUNT_NOT_ALLOWLISTED')
        if not re.fullmatch(r'[A-Za-z0-9._:-]{8,128}', session_id):
            raise OperatorBlocked('EXPLICIT_SESSION_ID_REQUIRED')
        self.safety, self.ledger = safety, safety.ledger
        self.session_id, self.isolation = session_id, isolation
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.engine = None
        self._connection_started = False

    def _check(self, phase):
        self.ledger.check_path()
        if self.isolation is None:
            raise OperatorBlocked('MACHINE_ISOLATION_NOT_QUALIFIED')
        try:
            evidence = self.isolation.require_safe(self.ledger.account, self.session_id, self.ledger.path.parent, phase)
            if not isinstance(evidence, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{8,128}', evidence):
                raise ValueError()
        except Exception:
            raise OperatorBlocked('MACHINE_ISOLATION_NOT_QUALIFIED') from None
        return evidence

    def connect(self, connector):
        if self._connection_started:
            raise OperatorBlocked('SESSION_ALREADY_BOUND')
        # No credential or terminal operation is reachable before this check.
        try:
            self._check('BEFORE_CONNECT')
        except BaseException:
            self.stop()
            raise
        self._connection_started = True
        try:
            broker = connector(self.ledger.account, self.session_id)
            wrapped = _GuardedBroker(broker, self._check, self.ledger.account, self.session_id, self.clock)
            wrapped.attest()
            self.engine = _MinimumVolumeEngine(self.safety, wrapped, clock=self.clock)
        except BaseException:
            self.stop()
            raise OperatorBlocked('OPERATOR_SESSION_FAILED') from None

    def stop(self):
        # HALT is not a broker close/cancel, nor cancellation of an in-flight send.
        return self.ledger.halt('P3_OPERATOR_STOP_RECONCILE_ONLY')

    def submit_once(self, request_id):
        if self.engine is None:
            raise OperatorBlocked('OPERATOR_SESSION_NOT_BOUND')
        try:
            receipt = self._check('BEFORE_REQUEST')
            with self.ledger.transaction() as conn:
                prior = conn.execute('SELECT payload FROM audit_events WHERE event_id=?', (USE_EVENT,)).fetchone()
                if prior:
                    raise OperatorBlocked('SMOKE_ALREADY_USED_RECONCILE_ONLY')
                request = conn.execute('SELECT * FROM p2_execution_requests WHERE execution_request_id=?', (request_id,)).fetchone()
                if not request:
                    raise OperatorBlocked('P2_REQUEST_REQUIRED')
                if conn.execute('SELECT 1 FROM p3_attempts').fetchone():
                    raise OperatorBlocked('EXISTING_ATTEMPT_RECONCILE_ONLY')
                payload = dict(execution_request_id=request_id, account_key=self.ledger.account.key,
                               session_id=self.session_id, isolation_evidence_id=receipt)
                # A new ledger/run must not reset the one-test budget. Never remove
                # this exclusive marker on failure, rejection, crash or completion.
                claim = self.ledger.path.parent.parent / 'smoke-used.json'
                try:
                    with claim.open('x', encoding='utf-8') as handle:
                        handle.write(canonical(dict(payload, run_id=self.ledger.path.parent.name)))
                        handle.flush()
                        os.fsync(handle.fileno())
                except FileExistsError:
                    raise OperatorBlocked('WORKSPACE_SMOKE_ALREADY_USED') from None
                conn.execute('INSERT INTO audit_events(event_id,event_type,intent_id,payload,timestamp) VALUES(?,?,?,?,?)',
                             (USE_EVENT,'P3_OPERATOR_SINGLE_USE',request['intent_id'],canonical(payload),self.clock().isoformat()))
            # The immutable marker commits first, even a pre-send crash burns this run.
            return self.engine.submit(request_id)
        finally:
            self.stop()

    def reconcile(self):
        if self.engine is None:
            raise OperatorBlocked('OPERATOR_SESSION_NOT_BOUND')
        self.stop()
        return self.engine.reconcile()
