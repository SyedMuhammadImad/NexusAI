"""Native operator providers. Importing this module never connects or loads secrets.

Only the explicit operator entry point loads the fixed private configuration.
Recorded equity/cost evidence remains mandatory: deal history cannot recover
unobserved historical floating equity or prospective commission schedules.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, AwareDatetime

from .ledger import DemoAccount, hashed
from .mt5_demo import MT5DemoAdapter
from .mt5_evidence import NativeEvidenceReader, account as normalize_account, record
from .operator_verification import OperatorBlocked, OperatorVerification, VerificationLedger, REPOSITORY, _plain_path
from .safety import VERSION, SafetyEngine, fresh, number
from .safety_contracts import Positive, Nonnegative, SafetyInputs, SafetyConfiguration

D = Decimal
PRIVATE = REPOSITORY / 'backend/private/mt5'
CONFIG_PATH = PRIVATE / 'p3-operator.json'
BASIS_PATH = PRIVATE / 'p3-risk-basis.json'
COST_PATH = PRIVATE / 'p3-costs.json'
GATES = ('credential_boundary','isolated_verification_db','policy_version','exact_account_allowlist',
         'demo_attestation','server_company_terminal','no_live_acceptance','instrument_eligibility',
         'fresh_p2_context','minimum_volume','halt_state')


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class OperatorSettings(StrictRecord):
    account: DemoAccount = Field(repr=False)
    password: SecretStr = Field(repr=False)
    terminal_exe: str
    terminal_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    service_sid: str = Field(pattern=r'^S-1-5-21-(\d+-){2}\d+-\d+$')
    broker_company: str = Field(min_length=1)
    terminal_company: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    symbols: frozenset[str] = Field(min_length=1)
    policy_version: str
    host_attestation: Literal['LOCAL','SYSTEM_FILES'] = 'LOCAL'

    def validate_operator(self):
        if (self.account.evidence_source != 'MT5_DEMO' or not self.account.account_id.isdecimal()
                or int(self.account.account_id) <= 0 or not self.password.get_secret_value()
                or self.policy_version != VERSION):
            raise OperatorBlocked('INVALID_OPERATOR_BINDING_OR_POLICY')
        SafetyConfiguration(approved_account_key=self.account.key,authorized_sources={self.source_id},instruments=self.symbols)
        exe = Path(self.terminal_exe)
        if not exe.is_absolute() or not exe.is_relative_to(PRIVATE) or exe.name.lower() not in {'terminal64.exe','terminal.exe'}:
            raise OperatorBlocked('TERMINAL_OUTSIDE_APPROVED_BOUNDARY')
        _plain_path(exe)


class RiskBasis(StrictRecord):
    evidence_id: str = Field(min_length=1)
    account_key: str
    currency: str
    observed_at: AwareDatetime
    day_start: AwareDatetime
    week_start: AwareDatetime
    day_equity: Positive
    week_equity: Positive
    high_water_equity: Positive
    cash_flow_total: Decimal = Field(allow_inf_nan=False)
    cash_flow_evidence_id: str = Field(min_length=1)


class CostBasis(StrictRecord):
    evidence_id: str = Field(min_length=1)
    account_key: str
    currency: str
    observed_at: AwareDatetime
    valid_until: AwareDatetime
    commission_per_lot: dict[str, Nonnegative]


def _load_private(path, model):
    # Exact fixed files only. Never accept a user-supplied path or dump validation.
    if path not in (CONFIG_PATH,BASIS_PATH,COST_PATH):
        raise OperatorBlocked('UNAPPROVED_PRIVATE_PATH')
    _plain_path(path)
    if not path.is_file():
        raise OperatorBlocked('REQUIRED_OPERATOR_FILE_MISSING')
    if path.stat().st_size > 65536 or path.stat().st_nlink != 1:
        raise OperatorBlocked('INVALID_OPERATOR_FILE')
    try:
        def unique(items):
            result = {}
            for key,value in items:
                if key in result: raise ValueError()
                result[key] = value
            return result
        return model.model_validate(json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique))
    except Exception:
        raise OperatorBlocked('INVALID_OPERATOR_FILE') from None


def load_settings():
    settings = _load_private(CONFIG_PATH,OperatorSettings)
    settings.validate_operator()
    return settings


def windows_host_snapshot(settings, directory):
    """Read-only OS metadata collector. No account password or login in arguments."""
    if os.name != 'nt': raise OperatorBlocked('WINDOWS_OPERATOR_REQUIRED')
    if settings.host_attestation == 'SYSTEM_FILES':
        return windows_privileged_snapshot(settings,directory)
    command = Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = REPOSITORY/'scripts/p3_windows_host.ps1'
    payload = dict(terminal_exe=settings.terminal_exe, service_sid=settings.service_sid,
                   python_exe=sys.executable, python_pid=os.getpid(),
                   protected_paths=[str(PRIVATE),str(CONFIG_PATH),str(BASIS_PATH),str(COST_PATH),
                                    str(Path(settings.terminal_exe).parent),str(directory)])
    result = subprocess.run([str(command),'-NoProfile','-NonInteractive','-File',str(script)],
                            input=json.dumps(payload),capture_output=True,text=True,timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0: raise OperatorBlocked('HOST_METADATA_UNAVAILABLE')
    try: return json.loads(result.stdout)
    except Exception: raise OperatorBlocked('HOST_METADATA_INVALID') from None


def windows_privileged_snapshot(settings,directory):
    from .host_attestation import validate_receipt
    directory=Path(directory)
    if directory.parent != REPOSITORY/'.p3-verification':
        raise OperatorBlocked('ISOLATION_STATE_OUTSIDE_BOUNDARY')
    nonce=uuid.uuid4().hex
    payload=dict(nonce=nonce,account_key=settings.account.key,run_id=directory.name,
        python_pid=os.getpid(),service_sid=settings.service_sid)
    command=Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result=subprocess.run([str(command),'-NoProfile','-NonInteractive','-File',
        str(REPOSITORY/'scripts/p3_attestor_client.ps1')],input=json.dumps(payload),
        capture_output=True,text=True,timeout=6,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0: raise OperatorBlocked('HOST_ATTESTOR_UNAVAILABLE')
    try:
        receipt=json.loads(result.stdout)
        return validate_receipt(receipt,nonce=nonce,account_key=settings.account.key,
            run_id=directory.name,python_pid=os.getpid(),current=datetime.now(timezone.utc))
    except Exception:
        raise OperatorBlocked('HOST_ATTESTOR_RECEIPT_INVALID') from None


class WindowsTerminalIsolation:
    def __init__(self, settings, *, clock=None, host_reader=windows_host_snapshot):
        settings.validate_operator()
        self.settings, self.host_reader = settings, host_reader
        self.clock = clock or (lambda:datetime.now(timezone.utc))
        self.client = None
        self.session_id = None
        self.directory = None
        self.terminal_evidence = None

    def require_safe(self, account, session_id, directory, phase):
        if account.key != self.settings.account.key or (self.session_id is not None and session_id != self.session_id):
            raise OperatorBlocked('ISOLATION_ACCOUNT_OR_SESSION_MISMATCH')
        directory = Path(directory)
        _plain_path(directory)
        if not directory.is_relative_to(REPOSITORY/'.p3-verification'):
            raise OperatorBlocked('ISOLATION_STATE_OUTSIDE_BOUNDARY')
        start = self.clock()
        host = self.host_reader(self.settings,directory)
        fresh(start,self.clock(),5)
        if (set(host) != {'dedicated_identity','session_zero','non_admin','exclusive_processes','protected_acl','terminal_pid'}
                or any(host[k] is not True for k in host if k != 'terminal_pid')
                or type(host['terminal_pid']) is not int or host['terminal_pid'] <= 0):
            raise OperatorBlocked('HOST_ISOLATION_NOT_PROVEN')
        exe = Path(self.settings.terminal_exe)
        _plain_path(exe)
        with exe.open('rb') as handle:
            digest = hashlib.file_digest(handle,'sha256').hexdigest()
        if digest != self.settings.terminal_sha256:
            raise OperatorBlocked('TERMINAL_BINARY_MISMATCH')
        if self.client is not None:
            self.attest_native()
        fresh(start,self.clock(),5)
        self.session_id, self.directory = session_id,directory
        return hashed([account.key,session_id,host,digest,start.isoformat(),phase])

    def attest_native(self):
        if self.client is None: raise OperatorBlocked('NATIVE_SESSION_NOT_CONNECTED')
        start = self.clock()
        a,t = self.client.account_info(),self.client.terminal_info()
        attestation,_ = normalize_account(self.client,a,t,self.settings.account,self.session_id,start)
        ar = record(a,('company',))
        tr = record(t,('company','path','data_path','build'))
        root = Path(self.settings.terminal_exe).parent
        if (ar['company'] != self.settings.broker_company or tr['company'] != self.settings.terminal_company
                or Path(tr['path']) != root or Path(tr['data_path']) != root
                or type(tr['build']) is not int or tr['build'] <= 0):
            raise OperatorBlocked('NATIVE_TERMINAL_IDENTITY_MISMATCH')
        fresh(start,self.clock(),5)
        # Public reports get only this digest and booleans, never login/path records.
        self.terminal_evidence = hashed([attestation.evidence_id,ar,tr])
        return attestation


class NativeP2Context:
    """Current native data + mandatory recorded risk/cost basis, for one min-lot run."""
    def __init__(self, client, ledger, settings, *, basis_reader=None, costs_reader=None, clock=None):
        settings.validate_operator()
        if ledger.account.key != settings.account.key:
            raise OperatorBlocked('CONTEXT_ACCOUNT_MISMATCH')
        self.client,self.ledger,self.settings = client,ledger,settings
        self.basis_reader = basis_reader or (lambda:_load_private(BASIS_PATH,RiskBasis))
        self.costs_reader = costs_reader or (lambda:_load_private(COST_PATH,CostBasis))
        self.clock = clock or (lambda:datetime.now(timezone.utc))

    def __call__(self,batch,orders,deals,positions):
        with localcontext() as ctx:
            ctx.prec = 40
            return self._context(batch,orders,positions)

    def _context(self,batch,orders,positions):
        current = self.clock()
        fresh(batch['observed_at'],current,5)
        basis = RiskBasis.model_validate(self.basis_reader().model_dump(warnings=False))
        costs = CostBasis.model_validate(self.costs_reader().model_dump(warnings=False))
        for evidence in (basis,costs):
            if (evidence.account_key,evidence.currency) != (self.settings.account.key,self.settings.account.currency):
                raise OperatorBlocked('RISK_BASIS_ACCOUNT_MISMATCH')
        fresh(basis.observed_at,current,5)
        if costs.observed_at > current or costs.valid_until <= current or costs.valid_until <= costs.observed_at:
            raise OperatorBlocked('COST_EVIDENCE_EXPIRED')
        day = current.replace(hour=0,minute=0,second=0,microsecond=0)
        if basis.day_start != day or basis.week_start != day-timedelta(days=day.weekday()):
            raise OperatorBlocked('RISK_PERIOD_EVIDENCE_MISSING')
        selected = {}
        for o in batch['native_observations']:
            if o.broker_entity_type in {'ACCOUNT','SYMBOL','QUOTE','INVENTORY'}:
                key=(o.broker_entity_type,o.broker_entity_id)
                if o.error or key in selected: raise OperatorBlocked('CONTRADICTORY_NATIVE_CONTEXT')
                selected[key]=o
        raw = selected['ACCOUNT',self.settings.account.key].normalized_payload
        inventory = selected['INVENTORY','current'].normalized_payload
        if inventory['complete'] is not True: raise OperatorBlocked('INCOMPLETE_NATIVE_INVENTORY')
        fresh(selected['ACCOUNT',self.settings.account.key].observed_at,current,5)
        fresh(selected['INVENTORY','current'].observed_at,current,5)
        owners = {}
        with self.ledger.connect() as conn:
            for order in orders:
                match=conn.execute('SELECT intent_id FROM p3_attempts WHERE correlation=? AND magic=? AND started_at IS NOT NULL',
                                   (order['correlation'],order['magic'])).fetchone()
                if not match: raise OperatorBlocked('UNKNOWN_NATIVE_ORDER')
                owners[order['broker_order_id']]=match[0]
            if not set(inventory['orders']) <= set(owners):
                raise OperatorBlocked('UNKNOWN_NATIVE_PENDING_ORDER')
        exposures=[]
        for p in positions:
            if D(p['open_volume']) > 0:
                if p['opening_order_id'] not in owners: raise OperatorBlocked('UNKNOWN_NATIVE_POSITION')
                exposures.append(dict(exposure_id=p['broker_position_id'],symbol=p['symbol'],direction=p['direction'],
                    volume=p['open_volume'],stop_loss=p['stop_loss'],kind='POSITION',reservation_intent_id=owners[p['opening_order_id']]))
        quotes,instruments={},{}
        for symbol in self.settings.symbols:
            meta,quote=selected['SYMBOL',symbol],selected['QUOTE',symbol]
            p,q=meta.normalized_payload,quote.normalized_payload
            fresh(meta.observed_at,current,3600)
            fresh(quote.broker_reported_at,current,3)
            if (p['name'] != symbol or p['currency_profit'] != raw['currency']
                    or p['trade_mode'] != self.client.SYMBOL_TRADE_MODE_FULL):
                raise OperatorBlocked('UNSUPPORTED_INSTRUMENT_OR_CONVERSION')
            volume=number(p['volume_min'])
            if volume % number(p['volume_step']): raise OperatorBlocked('INVALID_MINIMUM_VOLUME_STEP')
            margins=[]
            for direction,price in ((self.client.ORDER_TYPE_BUY,q['ask']),(self.client.ORDER_TYPE_SELL,q['bid'])):
                native_volume,native_price = float(volume),float(number(price))
                if D(str(native_volume)) != volume or D(str(native_price)) != number(price):
                    raise OperatorBlocked('UNSUPPORTED_NATIVE_NUMBER')
                margins.append(number(self.client.order_calc_margin(direction,symbol,native_volume,native_price)))
            fresh(batch['observed_at'],self.clock(),5)
            fresh(quote.broker_reported_at,self.clock(),3)
            quotes[symbol]=dict(evidence_id=quote.observation_id,observed_at=quote.broker_reported_at,**q)
            instruments[symbol]=dict(evidence_id=hashed([meta.observation_id,costs.evidence_id,[str(m) for m in margins]]),
                observed_at=meta.observed_at,symbol=symbol,account_currency=raw['currency'],calculation='LINEAR_ACCOUNT_CURRENCY',
                tick_size=number(p['trade_tick_size']),
                value_per_price_unit_per_lot=max(number(p['trade_tick_value_profit']),number(p['trade_tick_value_loss']))/number(p['trade_tick_size']),
                notional_per_price_unit_per_lot=number(p['trade_contract_size']),margin_per_lot=max(margins)/volume,
                commission_per_lot=costs.commission_per_lot[symbol],conversion_at=quote.broker_reported_at,
                volume_min=volume,volume_max=number(p['volume_max']),volume_step=number(p['volume_step']),tradable=True,market_available=True)
        return SafetyInputs(account=dict(evidence_id=hashed([basis.evidence_id,selected['ACCOUNT',self.settings.account.key].observation_id]),
            observed_at=batch['observed_at'],account_key=self.settings.account.key,currency=raw['currency'],mode='DEMO',
            equity=raw['equity'],balance=raw['balance'],used_margin=raw['margin'],positions_at=batch['observed_at'],orders_at=batch['observed_at'],
            complete=True,reconciled=True,exposures=exposures,
            **{k:getattr(basis,k) for k in ('day_start','week_start','day_equity','week_equity','high_water_equity','cash_flow_total','cash_flow_evidence_id')}),
            quotes=quotes,instruments=instruments)


class _AttestedAdapter(MT5DemoAdapter):
    def __init__(self,*args,isolation,**kwargs):
        super().__init__(*args,**kwargs)
        self.isolation=isolation

    def attest(self):
        return self.isolation.attest_native()

    def _submit(self, command):
        self.attest()
        if command.get('minimum_volume_only') is not True or command.get('entry_type') != 'MARKET':
            raise OperatorBlocked('NATIVE_OPERATOR_MINIMUM_MARKET_ONLY')
        info = self.client.symbol_info(command['symbol'])
        volume = number(command['volume'])
        if info is None or volume != number(info.volume_min) or D(str(float(volume))) != volume:
            raise OperatorBlocked('NATIVE_OPERATOR_MINIMUM_VOLUME_CHANGED')
        direction = {'BUY':self.client.ORDER_TYPE_BUY,'SELL':self.client.ORDER_TYPE_SELL}.get(command['direction'])
        if direction is None:
            raise OperatorBlocked('NATIVE_OPERATOR_UNKNOWN_DIRECTION')
        price = number(command['base_entry'])
        if D(str(float(price))) != price:
            raise OperatorBlocked('UNSUPPORTED_NATIVE_NUMBER')
        margin = number(self.client.order_calc_margin(direction,command['symbol'],float(volume),float(price)))
        a = record(self.client.account_info(),('equity','margin'))
        used = D(str(a['margin']))
        if not used.is_finite() or used < 0 or (used+margin)/number(a['equity']) > D('0.25'):
            raise OperatorBlocked('NATIVE_OPERATOR_MARGIN_RECHECK_FAILED')
        # Super repeats account/quote/volume/geometry/expiry immediately before send.
        return super()._submit(command)


class NativeConnector:
    def __init__(self,settings,isolation,ledger,*,native_factory=None,context_factory=NativeP2Context):
        self.settings,self.isolation,self.ledger=settings,isolation,ledger
        self.native_factory,self.context_factory=native_factory,context_factory
        self._started = False

    def __call__(self,account,session_id):
        if self._started:
            raise OperatorBlocked('NATIVE_CONNECT_ALREADY_ATTEMPTED')
        if account.key != self.settings.account.key or self.isolation.directory is None:
            raise OperatorBlocked('CONNECTOR_BINDING_NOT_QUALIFIED')
        self.isolation.require_safe(account,session_id,self.isolation.directory,'CONNECTOR')
        self._started = True
        try:
            if self.native_factory is None:
                import MetaTrader5  # OPERATOR-ONLY, after host validation; never imported by default.
                client=MetaTrader5
            else:
                client=self.native_factory()
            if client.initialize(self.settings.terminal_exe,login=int(account.account_id),
                password=self.settings.password.get_secret_value(),server=account.server,portable=True) is not True:
                raise OperatorBlocked('NATIVE_CONNECTION_FAILED')
            self.isolation.client=client
            self.isolation.attest_native()
            context=self.context_factory(client,self.ledger,self.settings,clock=self.isolation.clock)
            reader=NativeEvidenceReader(account,symbols=self.settings.symbols,context_provider=context,clock=self.isolation.clock)
            return _AttestedAdapter(client,account,session_id=session_id,snapshot_reader=reader,
                                    clock=self.isolation.clock,isolation=self.isolation)
        except BaseException:
            raise OperatorBlocked('NATIVE_CONNECTION_OR_ATTESTATION_FAILED') from None


def operator_file_preflight():
    """Explicit operator metadata inspection; no reading of credentials or databases."""
    result={name:'FAIL' for name in GATES}
    files={}
    for name,path in (('configuration',CONFIG_PATH),('risk_basis',BASIS_PATH),('cost_basis',COST_PATH)):
        try:
            _plain_path(path)
            files[name]=path.is_file()
        except (ValueError,OSError):
            files[name]=False
    return dict(status='FAIL',gates=result,operator_files_present=files,broker_actions=0,
                blocker='MISSING_OPERATOR_EVIDENCE' if not all(files.values()) else 'NATIVE_PREFLIGHT_REQUIRED')


def connected_preflight(run):
    """Report all gates; never reset HALT, create intent, submit, or resize a trade."""
    result={name:'FAIL' for name in GATES}
    try:
        run._check('PREFLIGHT')
        result.update(credential_boundary='PASS',isolated_verification_db='PASS',no_live_acceptance='PASS')
        if run.engine is None: raise OperatorBlocked('OPERATOR_SESSION_NOT_BOUND')
        run.engine.broker.attest()
        result.update(exact_account_allowlist='PASS',demo_attestation='PASS',server_company_terminal='PASS')
        with run.ledger.transaction() as conn:
            try:
                snapshot=run.engine._snapshot(conn)
                run.engine._project(conn,snapshot)
                run.safety._baselines(conn,snapshot.safety.account,run.engine._time())
                for symbol in run.safety.config.instruments:
                    run.safety._market(snapshot.safety,symbol,run.engine._time())
                result.update(instrument_eligibility='PASS',fresh_p2_context='PASS')
                if all(m.volume_min % m.volume_step == 0 for m in snapshot.safety.instruments.values()):
                    result['minimum_volume']='PASS'
                policy=conn.execute('SELECT policy_hash FROM p2_policy WHERE singleton=1').fetchone()[0]
                if run.safety.policy_hash==policy: result['policy_version']='PASS'
                if conn.execute('SELECT state FROM halt_state WHERE singleton=1').fetchone()[0]=='ACTIVE':
                    result['halt_state']='PASS'
            except Exception:
                run.engine._fail_safe(conn,None,'OPERATOR_PREFLIGHT_FAILED')
    except Exception:
        run.stop()
    passed=all(value=='PASS' for value in result.values())
    if not passed: run.stop()
    return dict(status='PASS' if passed else 'FAIL',gates=result,broker_actions=0,
                submission_authorized=False)  # Only submit_once + final P2 gate can authorize.


class NativeOperatorVerification(OperatorVerification):
    def submit_once(self, request_id):
        if connected_preflight(self)['status'] != 'PASS':
            self.stop()
            raise OperatorBlocked('NATIVE_PREFLIGHT_REQUIRED_BEFORE_SUBMISSION')
        return super().submit_once(request_id)


def open_native_operator():
    """Explicit operator entry point; fresh HALTED state, never creates or sends a trade."""
    settings = load_settings()
    ledger = VerificationLedger.create(settings.account)
    safety = SafetyEngine(ledger,SafetyConfiguration(approved_account_key=settings.account.key,
                          authorized_sources={settings.source_id},instruments=settings.symbols))
    isolation = WindowsTerminalIsolation(settings)
    run = NativeOperatorVerification(safety,session_id=ledger.path.parent.name,isolation=isolation)
    run.connect(NativeConnector(settings,isolation,ledger))
    return run


def native_readonly_preflight():
    """No HALT reset. Reports are redacted even when a private loader fails."""
    report = operator_file_preflight()
    if not all(report['operator_files_present'].values()):
        return report
    run = None
    try:
        run = open_native_operator()
        return connected_preflight(run)
    except Exception:
        return dict(report,blocker='OPERATOR_QUALIFICATION_FAILED')
    finally:
        if run is not None:
            run.stop()
