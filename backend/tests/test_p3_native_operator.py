"""Synthetic native/Windows providers only. Never inspect the operator's machine."""
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from types import SimpleNamespace

import pytest

from core.rebuild import native_operator as op
from core.rebuild.broker_observations import ObservationJournal
from core.rebuild.execution_contracts import BrokerSnapshot
from core.rebuild.ledger import Ledger
from core.rebuild.mt5_evidence import NativeEvidenceReader, account, project_native
from test_p2_safety import TIME
from test_p3_native_evidence import Native, binding
from test_p3_operator_verification import prepared

D=Decimal


@pytest.fixture
def setup(tmp_path,monkeypatch):
    private=tmp_path/'operator-fixture'
    private.mkdir()
    monkeypatch.setattr(op,'REPOSITORY',tmp_path)
    monkeypatch.setattr(op,'PRIVATE',private)
    for name,filename in [('CONFIG_PATH','p3-operator.json'),('BASIS_PATH','p3-risk-basis.json'),('COST_PATH','p3-costs.json')]:
        monkeypatch.setattr(op,name,private/filename)
    exe=private/'terminal64.exe'
    exe.write_bytes(b'fixture-not-an-executable')
    settings=op.OperatorSettings(account=binding(),password='fixture-only',terminal_exe=str(exe),
        terminal_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),service_sid='S-1-5-21-111-222-333-1001',
        broker_company='fixture-broker',terminal_company='fixture-terminal',source_id='manual-fixture',
        symbols={'XAUUSDm'},policy_version=op.VERSION)
    c=Native()
    c.a['company']=settings.broker_company
    c.t.update(company=settings.terminal_company,path=str(private),data_path=str(private),build=5000)
    c.margin_calls=[]
    def margin(*args):
        c.margin_calls.append(args)
        return 1
    c.order_calc_margin=margin
    c.initialize_calls=[]
    def initialize(*args,**kwargs):
        c.initialize_calls.append((args,kwargs))
        return True
    c.initialize=initialize
    ledger=Ledger(tmp_path/'fixture.sqlite3',account=settings.account)
    day=TIME.replace(hour=0,minute=0,second=0,microsecond=0)
    basis=op.RiskBasis(evidence_id='fixture-history',account_key=settings.account.key,currency='USD',
        observed_at=TIME,day_start=day,week_start=day-timedelta(days=day.weekday()),day_equity=100000,
        week_equity=100000,high_water_equity=100000,cash_flow_total=0,cash_flow_evidence_id='fixture-flow')
    costs=op.CostBasis(evidence_id='fixture-costs',account_key=settings.account.key,currency='USD',observed_at=TIME,
        valid_until=TIME+timedelta(hours=1),commission_per_lot={'XAUUSDm':0})
    context=op.NativeP2Context(c,ledger,settings,basis_reader=lambda:basis,costs_reader=lambda:costs,clock=lambda:TIME)
    attestation,_=account(c,c.account_info(),c.terminal_info(),settings.account,'fixture-session',TIME)
    reader=NativeEvidenceReader(settings.account,symbols=settings.symbols,context_provider=context,clock=lambda:TIME)
    batch=reader(c,TIME,attestation)
    host=dict(dedicated_identity=True,session_zero=True,non_admin=True,exclusive_processes=True,protected_acl=True,terminal_pid=42)
    isolation=op.WindowsTerminalIsolation(settings,clock=lambda:TIME,host_reader=lambda *args:host)
    directory=tmp_path/'.p3-verification'/'fixture'
    directory.mkdir(parents=True)
    return SimpleNamespace(**locals())


def test_real_context_maps_native_reader_into_canonical_projection(setup):
    s=setup
    journal=ObservationJournal(s.settings.account.key)
    with s.ledger.transaction() as conn:
        journal.append(conn,s.batch['native_observations'])
        result=BrokerSnapshot.model_validate(project_native(conn,journal,s.batch))
    assert result.safety.account.equity==100000
    assert result.safety.account.used_margin==0
    assert result.safety.account.exposures==()
    assert result.safety.instruments['XAUUSDm'].margin_per_lot==100
    assert s.c.margin_calls==[(0,'XAUUSDm',.01,100.0),(1,'XAUUSDm',.01,99.99)]
    assert not s.c.initialize_calls


@pytest.mark.parametrize('field,value',[
    ('account_key','wrong'),('currency','EUR'),('observed_at',TIME-timedelta(seconds=6)),
    ('day_start',TIME-timedelta(days=1)),('week_start',TIME-timedelta(days=7)),
    ('high_water_equity',float('nan')),('day_equity',0),('cash_flow_total',float('inf'))])
def test_missing_stale_or_invalid_risk_history_rejects(setup,field,value):
    s=setup
    s.context.basis_reader=lambda:s.basis.model_copy(update={field:value})
    with pytest.raises((ValueError,KeyError)):
        s.context(s.batch,[],[],[])


@pytest.mark.parametrize('field,value',[
    ('account_key','wrong'),('valid_until',TIME),('observed_at',TIME+timedelta(seconds=1)),
    ('commission_per_lot',{}),('commission_per_lot',{'XAUUSDm':-1})])
def test_costs_never_default_to_zero(setup,field,value):
    s=setup
    s.context.costs_reader=lambda:s.costs.model_copy(update={field:value})
    with pytest.raises((ValueError,KeyError)):
        s.context(s.batch,[],[],[])


@pytest.mark.parametrize('kind,field,value',[
    ('INVENTORY','complete',False),('INVENTORY','orders',['external']),
    ('SYMBOL','currency_profit','EUR'),('SYMBOL','trade_mode',0),('SYMBOL','volume_step','0.03'),
    ('SYMBOL','trade_tick_value_loss','NaN'),('QUOTE','ask','Infinity')])
def test_context_rejects_unqualified_native_evidence(setup,kind,field,value):
    s=setup
    original=next(o for o in s.batch['native_observations'] if o.broker_entity_type==kind)
    revised=original.model_copy(update={'normalized_payload':dict(original.normalized_payload,**{field:value})})
    s.batch['native_observations']=[revised if o is original else o for o in s.batch['native_observations']]
    with pytest.raises((ValueError,KeyError)):
        s.context(s.batch,[],[],[])


@pytest.mark.parametrize('kind,field,age',[('INVENTORY','observed_at',6),('ACCOUNT','observed_at',6),
    ('SYMBOL','observed_at',3601),('QUOTE','broker_reported_at',4)])
def test_each_native_timestamp_is_checked(setup,kind,field,age):
    s=setup
    s.batch['native_observations']=[o.model_copy(update={field:TIME-timedelta(seconds=age)})
        if o.broker_entity_type==kind else o for o in s.batch['native_observations']]
    with pytest.raises(ValueError): s.context(s.batch,[],[],[])


@pytest.mark.parametrize('value',[None,0,-1,True,float('nan'),float('inf')])
def test_margin_errors_reject(setup,value):
    s=setup
    s.c.order_calc_margin=lambda *args:value
    with pytest.raises(ValueError): s.context(s.batch,[],[],[])


def test_duplicate_context_observation_rejects(setup):
    s=setup
    s.batch['native_observations'].append(s.batch['native_observations'][0])
    with pytest.raises(op.OperatorBlocked): s.context(s.batch,[],[],[])


def test_context_rejects_unknown_external_orders_and_positions(setup):
    s=setup
    with pytest.raises(op.OperatorBlocked):
        s.context(s.batch,[dict(correlation='unknown',magic=3,broker_order_id='external')],[],[])
    with pytest.raises(op.OperatorBlocked):
        s.context(s.batch,[],[],[dict(open_volume='1',opening_order_id='external')])


def test_host_checks_and_native_attestation(setup):
    s=setup
    assert s.isolation.require_safe(s.settings.account,'fixture-session',s.directory,'TEST')
    s.isolation.client=s.c
    a=s.isolation.attest_native()
    assert a.account_key==s.settings.account.key
    assert len(s.isolation.terminal_evidence)==64


@pytest.mark.parametrize('field,value',[('dedicated_identity',False),('session_zero',False),('non_admin',False),
    ('exclusive_processes',False),('protected_acl',False),('terminal_pid',0),('terminal_pid',True),('protected_acl',1)])
def test_host_isolation_fails_closed_before_native_factory(setup,field,value):
    s=setup
    s.host[field]=value
    s.isolation.directory=s.directory
    called=[]
    connector=op.NativeConnector(s.settings,s.isolation,s.ledger,native_factory=lambda:called.append(True))
    with pytest.raises(op.OperatorBlocked): connector(s.settings.account,'fixture-session')
    assert not called and not s.c.initialize_calls


@pytest.mark.parametrize('record,field,value',[
    ('a','login',124),('a','server','other'),('a','trade_mode',2),('a','company','other'),
    ('t','company','other'),('t','path','other'),('t','data_path','other'),('t','build',True),
    ('t','connected',False),('t','tradeapi_disabled',True)])
def test_attestation_rejects_account_and_terminal_mismatch(setup,record,field,value):
    s=setup
    s.isolation.session_id='fixture-session'
    s.isolation.client=s.c
    getattr(s.c,record)[field]=value
    with pytest.raises((ValueError,KeyError)): s.isolation.attest_native()


def test_changed_binary_and_stale_host_receipt_reject(setup):
    s=setup
    s.exe.write_bytes(b'changed')
    with pytest.raises(op.OperatorBlocked): s.isolation.require_safe(s.settings.account,'fixture-session',s.directory,'TEST')
    s.exe.write_bytes(b'fixture-not-an-executable')
    clock=iter([TIME,TIME+timedelta(seconds=6)])
    s.isolation.clock=lambda:next(clock)
    with pytest.raises(ValueError): s.isolation.require_safe(s.settings.account,'fixture-session',s.directory,'TEST')


def test_connector_is_explicit_attested_one_shot(setup):
    s=setup
    s.isolation.require_safe(s.settings.account,'fixture-session',s.directory,'TEST')
    connector=op.NativeConnector(s.settings,s.isolation,s.ledger,native_factory=lambda:s.c)
    adapter=connector(s.settings.account,'fixture-session')
    assert adapter.account.key==s.settings.account.key
    args,kwargs=s.c.initialize_calls[0]
    assert args==(s.settings.terminal_exe,)
    assert kwargs==dict(login=123,password='fixture-only',server='fixture-server',portable=True)
    with pytest.raises(op.OperatorBlocked): connector(s.settings.account,'fixture-session')
    assert len(s.c.initialize_calls)==1


def test_connection_errors_are_redacted_and_not_retried(setup):
    s=setup
    s.isolation.require_safe(s.settings.account,'fixture-session',s.directory,'TEST')
    def fail(): raise RuntimeError('fixture-secret-must-not-escape')
    connector=op.NativeConnector(s.settings,s.isolation,s.ledger,native_factory=fail)
    with pytest.raises(op.OperatorBlocked) as error: connector(s.settings.account,'fixture-session')
    assert str(error.value)=='NATIVE_CONNECTION_OR_ATTESTATION_FAILED'
    with pytest.raises(op.OperatorBlocked): connector(s.settings.account,'fixture-session')


def test_fixed_private_file_reader_sanitizes_errors(setup):
    op.CONFIG_PATH.write_text('{"password":"fixture-secret", "password":"duplicate"}')
    with pytest.raises(op.OperatorBlocked) as error: op.load_settings()
    assert str(error.value)=='INVALID_OPERATOR_FILE'
    with pytest.raises(op.OperatorBlocked): op._load_private(setup.tmp_path/'unknown',op.OperatorSettings)


def test_metadata_preflight_missing_files_never_connects(setup,monkeypatch):
    def forbidden(): pytest.fail('Connection must not be reachable')
    monkeypatch.setattr(op,'open_native_operator',forbidden)
    result=op.native_readonly_preflight()
    assert result['status']=='FAIL'
    assert result['operator_files_present']==dict(configuration=False,risk_basis=False,cost_basis=False)
    assert result['broker_actions']==0
    assert 'fixture-only' not in json.dumps(result)


def test_connected_preflight_is_read_only_and_halt_authoritative(tmp_path):
    ledger,safety,run,broker,isolation,request=prepared(tmp_path)
    result=op.connected_preflight(run)
    assert result['status']=='PASS'
    assert result['submission_authorized'] is False
    assert broker.calls==[]
    run.stop()
    result=op.connected_preflight(run)
    assert result['status']=='FAIL' and result['gates']['halt_state']=='FAIL'
    assert broker.calls==[]


@pytest.mark.parametrize('mutation', ['size','market','direction','margin','equity','missing_margin','exact_cap'])
def test_final_native_margin_and_minimum_volume_checks(setup,monkeypatch,mutation):
    s=setup
    s.isolation.client=s.c
    s.isolation.session_id='fixture-session'
    adapter=op._AttestedAdapter(s.c,s.settings.account,session_id='fixture-session',snapshot_reader=None,
                                isolation=s.isolation,clock=lambda:TIME)
    command=dict(symbol='XAUUSDm',volume='.01',base_entry='100',direction='BUY',entry_type='MARKET',minimum_volume_only=True)
    continued=[]
    monkeypatch.setattr(op.MT5DemoAdapter,'_submit',lambda self,c:continued.append(c))
    if mutation=='size': command['volume']='.02'
    if mutation=='market': command['entry_type']='LIMIT'
    if mutation=='direction': command['direction']='UNKNOWN'
    if mutation=='margin': s.c.order_calc_margin=lambda *args:25001
    if mutation=='equity': s.c.a['equity']=0
    if mutation=='missing_margin': s.c.order_calc_margin=lambda *args:None
    if mutation=='exact_cap': s.c.order_calc_margin=lambda *args:25000
    if mutation=='exact_cap':
        adapter.submit(command)
        assert continued==[command]
    else:
        with pytest.raises(ValueError): adapter.submit(command)
        assert continued==[]


def test_readonly_preflight_does_not_disclose_private_failure(setup,monkeypatch):
    for path in (op.CONFIG_PATH,op.BASIS_PATH,op.COST_PATH): path.write_text('{}')
    def fail(): raise RuntimeError('fixture-secret-must-not-escape')
    monkeypatch.setattr(op,'open_native_operator',fail)
    report=op.native_readonly_preflight()
    assert report['blocker']=='OPERATOR_QUALIFICATION_FAILED'
    assert 'fixture-secret' not in json.dumps(report)


def test_context_ledger_account_cannot_be_substituted(setup):
    s=setup
    from test_p2_safety import ACCOUNT
    wrong=Ledger(s.tmp_path/'wrong.sqlite3',account=ACCOUNT)
    with pytest.raises(op.OperatorBlocked): op.NativeP2Context(s.c,wrong,s.settings)


@pytest.mark.parametrize('pass_gate',[False,True])
def test_native_composition_requires_preflight_before_one_shot(tmp_path,monkeypatch,pass_gate):
    ledger,safety,prior,broker,isolation,request=prepared(tmp_path)
    run=op.NativeOperatorVerification(safety,session_id=prior.session_id,isolation=isolation,clock=lambda:TIME)
    run.connect(lambda *args:broker)
    if not pass_gate:
        monkeypatch.setattr(op,'connected_preflight',lambda run:dict(status='FAIL'))
        with pytest.raises(op.OperatorBlocked): run.submit_once(request)
        assert broker.calls==[]
        with ledger.connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM p3_attempts').fetchone()[0]==0
    else:
        run.submit_once(request)
        assert len(broker.calls)==1
        with pytest.raises(op.OperatorBlocked): run.submit_once(request)
        assert len(broker.calls)==1
