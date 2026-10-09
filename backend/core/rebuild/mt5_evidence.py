"""Read-only injected MT5 evidence normalization. No import/login/secret discovery.

API records provide facts, not missing historical equity baselines or a universal
commission schedule. An explicit qualified safety-context provider supplies those;
all overlapping native account/inventory/metadata facts must agree.
"""
from datetime import datetime, timezone
from decimal import Decimal
from collections import defaultdict

from .broker_observations import observation
from .execution_contracts import Attestation
from .ledger import hashed
from .safety_contracts import SafetyInputs

D = Decimal
VERSION = 'mt5-native-v1'


def record(value, fields):
    if value is None:
        raise ValueError('Missing native record')
    source = value if isinstance(value, dict) else value._asdict() if hasattr(value, '_asdict') else vars(value)
    return {key: source[key] for key in fields}  # No defaults for absent fields.


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('Invalid native integer')
    return value


def number(value, minimum=None):
    if isinstance(value, bool):
        raise ValueError('Boolean numeric field')
    result = D(str(value))
    if not result.is_finite() or minimum is not None and result < minimum:
        raise ValueError('Invalid native number')
    return result


def positive(value):
    result = number(value)
    if result <= 0:
        raise ValueError('Nonpositive native number')
    return result


def stamp(value):
    value = integer(value, 1)
    return datetime.fromtimestamp(value // 1000, timezone.utc).replace(microsecond=(value % 1000) * 1000)


def enum(client, value, names):
    integer(value)
    matches = [name for name in names if hasattr(client, name) and getattr(client, name) == value]
    if len(matches) != 1:
        raise ValueError('Unsupported or contradictory native enum')
    return matches[0]


def account(client, value, terminal, binding, session, now):
    a = record(value, ('login','server','currency','trade_mode','margin_mode','trade_allowed','trade_expert','equity','balance','margin'))
    t = record(terminal, ('connected','trade_allowed','tradeapi_disabled'))
    if (str(integer(a['login'], 1)) != binding.account_id or a['server'] != binding.server
            or a['currency'] != binding.currency or binding.evidence_source != 'MT5_DEMO'
            or enum(client,a['trade_mode'],['ACCOUNT_TRADE_MODE_DEMO','ACCOUNT_TRADE_MODE_REAL','ACCOUNT_TRADE_MODE_CONTEST']) != 'ACCOUNT_TRADE_MODE_DEMO'
            or enum(client,a['margin_mode'],['ACCOUNT_MARGIN_MODE_RETAIL_HEDGING','ACCOUNT_MARGIN_MODE_RETAIL_NETTING','ACCOUNT_MARGIN_MODE_EXCHANGE']) != 'ACCOUNT_MARGIN_MODE_RETAIL_HEDGING'
            or any(v is not True for v in (a['trade_allowed'],a['trade_expert'],t['connected'],t['trade_allowed']))
            or t['tradeapi_disabled'] is not False):
        raise ValueError('Native demo account/environment mismatch')
    for field in ('equity','balance'):
        positive(a[field])
    number(a['margin'], D(0))
    return Attestation(evidence_id=hashed([session,a,t]),observed_at=now,account_key=binding.key,
        account_id=binding.account_id,server=binding.server,currency=binding.currency,mode='DEMO',
        scope='MT5_DEMO',session_id=session,connected=True,trade_allowed=True,expert_allowed=True,hedging=True), a


class NativeNormalizer:
    def __init__(self, client, account_key, now):
        self.client, self.account_key, self.now = client, account_key, now

    def emit(self, kind, identity, payload, raw, reported=None, ordering='UNORDERED'):
        return observation(self.account_key,kind,str(identity),payload,raw,self.now,
                           reported_at=reported,ordering=ordering,normalizer=VERSION)

    def symbol(self, value):
        r = record(value, ('name','trade_mode','trade_calc_mode','trade_tick_size','trade_tick_value_profit',
            'trade_tick_value_loss','trade_contract_size','volume_min','volume_max','volume_step','currency_profit',
            'currency_margin','point','digits','trade_stops_level','filling_mode','trade_exemode'))
        if not isinstance(r['name'],str) or not r['name']:
            raise ValueError('Invalid native symbol')
        for key in ('trade_tick_size','trade_tick_value_profit','trade_tick_value_loss','trade_contract_size',
                    'volume_min','volume_max','volume_step','point'):
            positive(r[key])
        for key in ('trade_mode','trade_calc_mode','digits','trade_stops_level','filling_mode','trade_exemode'):
            integer(r[key])
        if number(r['volume_min']) > number(r['volume_max']):
            raise ValueError('Invalid lot bounds')
        enum(self.client,r['trade_calc_mode'],['SYMBOL_CALC_MODE_FOREX','SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE',
             'SYMBOL_CALC_MODE_CFD','SYMBOL_CALC_MODE_CFDLEVERAGE'])
        return self.emit('SYMBOL',r['name'],r,r)

    def quote(self, symbol, value):
        r = record(value, ('time_msc','bid','ask'))
        when = stamp(r['time_msc'])
        if positive(r['ask']) < positive(r['bid']):
            raise ValueError('Crossed native quote')
        return self.emit('QUOTE',symbol,dict(bid=str(number(r['bid'])),ask=str(number(r['ask']))),r,when,'BROKER_UPDATE')

    def order(self, value):
        r = record(value, ('ticket','time_setup_msc','time_done_msc','type','state','magic','position_id',
                          'reason','volume_initial','volume_current','price_open','sl','tp','symbol','comment'))
        identity = str(integer(r['ticket'],1))
        direction_type = enum(self.client,r['type'],['ORDER_TYPE_BUY','ORDER_TYPE_SELL','ORDER_TYPE_BUY_LIMIT','ORDER_TYPE_SELL_LIMIT'])
        status = enum(self.client,r['state'],['ORDER_STATE_STARTED','ORDER_STATE_PLACED','ORDER_STATE_CANCELED',
            'ORDER_STATE_PARTIAL','ORDER_STATE_FILLED','ORDER_STATE_REJECTED','ORDER_STATE_EXPIRED',
            'ORDER_STATE_REQUEST_ADD','ORDER_STATE_REQUEST_MODIFY','ORDER_STATE_REQUEST_CANCEL'])
        volume, remaining = positive(r['volume_initial']),number(r['volume_current'],D(0))
        if remaining > volume:
            raise ValueError('Native remaining volume exceeds request')
        integer(r['magic']); integer(r['position_id']); integer(r['reason'])
        reported = stamp(r['time_done_msc']) if integer(r['time_done_msc']) else stamp(r['time_setup_msc'])
        payload = dict(broker_order_id=identity,correlation=r['comment'],magic=r['magic'],symbol=r['symbol'],
            direction='BUY' if 'BUY' in direction_type else 'SELL',entry_type='LIMIT' if 'LIMIT' in direction_type else 'MARKET',
            requested_volume=str(volume),remaining_volume=str(remaining),stop_loss=str(number(r['sl'],D(0))),
            take_profit=str(number(r['tp'],D(0))),limit_price=str(number(r['price_open'],D(0))),
            native_status=status,native_reason=r['reason'],position_id=str(r['position_id']))
        return self.emit('ORDER',identity,payload,r,reported,'BROKER_UPDATE')

    def deal(self, value):
        r = record(value, ('ticket','order','time_msc','type','entry','position_id','volume','price',
                          'profit','commission','swap','fee','symbol','magic','reason'))
        identity = str(integer(r['ticket'],1))
        native_type = enum(self.client,r['type'],['DEAL_TYPE_BUY','DEAL_TYPE_SELL','DEAL_TYPE_BUY_CANCELED',
            'DEAL_TYPE_SELL_CANCELED','DEAL_TYPE_BALANCE','DEAL_TYPE_CREDIT','DEAL_TYPE_CHARGE',
            'DEAL_TYPE_CORRECTION','DEAL_TYPE_BONUS','DEAL_TYPE_COMMISSION','DEAL_TYPE_INTEREST',
            'DEAL_TYPE_COMMISSION_DAILY','DEAL_TYPE_COMMISSION_MONTHLY','DEAL_TYPE_COMMISSION_AGENT_DAILY',
            'DEAL_TYPE_COMMISSION_AGENT_MONTHLY','DEAL_DIVIDEND','DEAL_DIVIDEND_FRANKED','DEAL_TAX'])
        is_trade = native_type in {'DEAL_TYPE_BUY','DEAL_TYPE_SELL'}
        entry = enum(self.client,r['entry'],['DEAL_ENTRY_IN','DEAL_ENTRY_OUT','DEAL_ENTRY_INOUT','DEAL_ENTRY_OUT_BY']) if is_trade else None
        for field in ('order','position_id','magic','reason'):
            integer(r[field],1 if is_trade and field in {'order','position_id'} else 0)
        values = {key:str(number(r[key])) for key in ('profit','commission','swap','fee')}
        values.update(volume=str(positive(r['volume']) if is_trade else number(r['volume'],D(0))),
                      price=str(positive(r['price']) if is_trade else number(r['price'],D(0))))
        payload = dict(broker_deal_id=identity,broker_order_id=str(r['order']),broker_position_id=str(r['position_id']),
            symbol=r['symbol'],direction=native_type.removeprefix('DEAL_TYPE_') if is_trade else None,
            entry=entry.removeprefix('DEAL_ENTRY_') if entry else None,native_type=native_type,**values)
        # time_msc is execution time, NOT a correction sequence. Never order revisions by receipt time.
        return self.emit('DEAL',identity,payload,r,stamp(r['time_msc']))

    def position(self, value):
        r = record(value, ('ticket','identifier','time_msc','time_update_msc','type','magic','volume',
                          'price_open','price_current','sl','tp','symbol'))
        integer(r['ticket'],1); integer(r['magic']); positive(r['price_open']); positive(r['price_current'])
        identity = str(integer(r['identifier'],1))
        direction = enum(self.client,r['type'],['POSITION_TYPE_BUY','POSITION_TYPE_SELL']).removeprefix('POSITION_TYPE_')
        reported = stamp(r['time_update_msc'])
        if reported < stamp(r['time_msc']):
            raise ValueError('Position update precedes creation')
        payload = dict(broker_position_id=identity,symbol=r['symbol'],direction=direction,
                       open_volume=str(positive(r['volume'])),stop_loss=str(positive(r['sl'])),take_profit=str(positive(r['tp'])))
        return self.emit('POSITION',identity,payload,r,reported,'BROKER_UPDATE')


class NativeEvidenceReader:
    """Only reads an already-attested injected session; no initialization or send.

    context_provider supplies qualified cash-flow/baseline/cost/conversion evidence
    and exact reservation attribution. It cannot override observed broker facts.
    """
    def __init__(self, binding, *, symbols, context_provider, clock):
        self.binding, self.symbols = binding, tuple(symbols)
        self.context_provider, self.clock = context_provider, clock
        self.observations = []

    def __call__(self, client, since, attestation):
        self.observations = []
        now = self.clock()
        before, account_raw = account(client,client.account_info(),client.terminal_info(),self.binding,attestation.session_id,now)
        if before.account_key != attestation.account_key or attestation.scope != 'MT5_DEMO':
            raise ValueError('Reader attestation binding mismatch')
        n = NativeNormalizer(client,self.binding.key,now)
        self.observations.append(n.emit('ACCOUNT',self.binding.key,account_raw,account_raw))
        raw_orders = client.history_orders_get(since,now)
        raw_deals = client.history_deals_get(since,now)
        pending = client.orders_get()
        raw_positions = client.positions_get()
        if any(v is None for v in (raw_orders,raw_deals,pending,raw_positions)):
            raise ValueError('Incomplete native inventory/history')
        for kind, values, normalize in (('ORDER',tuple(raw_orders)+tuple(pending),n.order),('DEAL',raw_deals,n.deal),('POSITION',raw_positions,n.position)):
            for index,value in enumerate(values):
                try:
                    self.observations.append(normalize(value))
                except Exception:
                    # Preserve only broker-record data, never exception strings or client/session internals.
                    raw = value if isinstance(value,dict) else value._asdict() if hasattr(value,'_asdict') else vars(value)
                    safe = {k:v for k,v in raw.items() if k in {'ticket','identifier','order','position_id','type','entry',
                        'volume','price','sl','tp','symbol','time_msc','time_update_msc','state','profit','commission','swap','fee'}}
                    safe = {k:str(v) if isinstance(v,float) and not D(str(v)).is_finite() else v for k,v in safe.items()}
                    identity = str(raw.get('identifier' if kind=='POSITION' else 'ticket',f'invalid-{index}'))
                    self.observations.append(observation(self.binding.key,kind,identity,{},safe,now,error='INVALID_NATIVE_RECORD'))
        for symbol in self.symbols:
            for kind, value, normalize in (
                ('SYMBOL',client.symbol_info(symbol),n.symbol),
                ('QUOTE',client.symbol_info_tick(symbol),lambda value:n.quote(symbol,value))):
                try:
                    self.observations.append(normalize(value))
                except Exception:
                    raw = {} if value is None else value if isinstance(value,dict) else value._asdict() if hasattr(value,'_asdict') else vars(value)
                    allowed = {'name','trade_mode','trade_calc_mode','trade_tick_size','trade_tick_value_profit',
                        'trade_tick_value_loss','trade_contract_size','volume_min','volume_max','volume_step','currency_profit',
                        'currency_margin','point','digits','trade_stops_level','filling_mode','trade_exemode','time_msc','bid','ask'}
                    safe = {k:str(v) if isinstance(v,float) and not D(str(v)).is_finite() else v for k,v in raw.items() if k in allowed}
                    self.observations.append(observation(self.binding.key,kind,symbol,{},safe,now,error='INVALID_NATIVE_RECORD'))
        account(client,client.account_info(),client.terminal_info(),self.binding,attestation.session_id,self.clock())
        inventory = dict(positions=[str(integer(record(p,('identifier',))['identifier'],1)) for p in raw_positions],
                         orders=[str(integer(record(o,('ticket',))['ticket'],1)) for o in pending],
                         history_since=since.isoformat(),complete=True)
        self.observations.append(n.emit('INVENTORY','current',inventory,inventory,now,'BROKER_UPDATE'))
        return dict(native_observations=self.observations,attestation=before,history_since=since,
                    observed_at=now,safety_provider=self.context_provider,
                    exit_reasons={client.ORDER_REASON_SL:'SL',client.ORDER_REASON_TP:'TP'},
                    full_trade_mode=client.SYMBOL_TRADE_MODE_FULL)


def project_native(conn, journal, batch):
    """Derive one economic entity per broker ID. Engine performs command/risk reconciliation."""
    observations = batch['native_observations']
    if any(o.error for o in observations):
        raise ValueError('Invalid native batch retained for review')
    keys = {(o.broker_entity_type,o.broker_entity_id) for o in observations}
    current = {(k,i):journal.current(conn,k,i) for k,i in keys if k not in {'ACCOUNT','SYMBOL','INVENTORY'}}
    # Account/metadata are fresh snapshots, not sequenced trade mutations. Their
    # evidence remains journaled; the current batch must supply coherent values.
    def latest(kind):
        return {o.broker_entity_id:o for o in observations if o.broker_entity_type==kind}
    by_kind = {kind:{i:o for (k,i),o in current.items() if k==kind} for kind in ('ORDER','DEAL','POSITION','QUOTE')}
    def contract(o, extra=None):
        return dict(evidence_id=o.observation_id,observed_at=o.broker_reported_at or o.observed_at,
                    **(extra if extra is not None else o.normalized_payload))
    deals, totals, entries, closing = [],defaultdict(lambda:D(0)),defaultdict(set),defaultdict(lambda:D(0))
    for o in by_kind['DEAL'].values():
        p = dict(o.normalized_payload)
        native = p.pop('native_type')
        if native not in {'DEAL_TYPE_BUY','DEAL_TYPE_SELL'}:
            # Cash flows/canceled trades remain evidence, never fabricated fills.
            # Context provider must attest cash-flow baselines; cancellations need
            # consistent revised inventory before economic projection is possible.
            if native.endswith('_CANCELED'):
                raise ValueError('Canceled deal economic reconciliation ambiguous')
            continue
        deals.append(contract(o,p))
        totals[p['broker_order_id']] += D(p['volume'])
        if p['entry']=='IN':
            entries[p['broker_position_id']].add(p['broker_order_id'])
        elif p['entry']=='OUT':
            closing[p['broker_position_id']] += D(p['volume'])
        else:
            raise ValueError('Unsupported native netting/close-by')
    orders, exits = [],[]
    for identity,o in by_kind['ORDER'].items():
        p = dict(o.normalized_payload)
        reason,position = p.pop('native_reason'),p.pop('position_id')
        status,remaining = p.pop('native_status'),D(p.pop('remaining_volume'))
        p.pop('limit_price')
        volume = totals[identity]
        if D(p['requested_volume'])-remaining != volume:
            raise ValueError('Native order/deal volume disagreement')
        statuses = {'ORDER_STATE_PLACED':'PLACED','ORDER_STATE_PARTIAL':'PARTIALLY_FILLED','ORDER_STATE_FILLED':'FILLED',
                    'ORDER_STATE_CANCELED':'CANCELLED','ORDER_STATE_EXPIRED':'CANCELLED','ORDER_STATE_REJECTED':'REJECTED'}
        if status not in statuses:
            raise ValueError('Native order transition in progress')
        p.update(status=statuses[status],filled_volume=str(volume))
        exit_reason = batch.get('exit_reasons',{}).get(reason)
        if exit_reason:
            exits.append(contract(o,dict(broker_order_id=identity,broker_position_id=position,symbol=p['symbol'],
                direction=p['direction'],reason=exit_reason,requested_volume=p['requested_volume'],filled_volume=str(volume),status=p['status'])))
        else:
            orders.append(contract(o,p))
    positions=[]
    inventory = latest('INVENTORY')['current']
    present = set(inventory.normalized_payload['positions'])
    for identity,opening in entries.items():
        if len(opening)!=1:
            raise ValueError('Native position has multiple opening orders')
        order_id = next(iter(opening))
        if identity in present:
            p = dict(by_kind['POSITION'][identity].normalized_payload)
            p['opening_order_id'] = order_id
            positions.append(dict(contract(by_kind['POSITION'][identity],p),observed_at=batch['observed_at']))
        else:
            order = next((o for o in orders if o['broker_order_id']==order_id),None)
            if not order or totals[order_id] != closing[identity] or not closing[identity]:
                raise ValueError('Absent position has no complete broker closing evidence')
            positions.append(dict(evidence_id=inventory.observation_id,observed_at=batch['observed_at'],broker_position_id=identity,
                opening_order_id=order_id,symbol=order['symbol'],direction=order['direction'],open_volume='0',
                stop_loss=order['stop_loss'],take_profit=order['take_profit'],confirmed_absent=True,absence_evidence_id=inventory.observation_id))
    if present != {p['broker_position_id'] for p in positions if D(p['open_volume'])>0}:
        raise ValueError('Unknown external native position')
    context = batch['safety_provider'](batch,orders,deals,positions)
    safety = SafetyInputs.model_validate(context)
    a = latest('ACCOUNT')[journal.account_key].normalized_payload
    if (safety.account.account_key!=journal.account_key or safety.account.equity!=number(a['equity'])
            or safety.account.balance!=number(a['balance']) or safety.account.used_margin!=number(a['margin'])
            or safety.account.currency!=a['currency']):
        raise ValueError('Context overrides native account evidence')
    observed_inventory = {(p['broker_position_id'],p['symbol'],p['direction'],D(p['open_volume']),D(p['stop_loss']))
                          for p in positions if D(p['open_volume'])>0}
    supplied_inventory = {(p.exposure_id,p.symbol,p.direction,p.volume,p.stop_loss) for p in safety.account.exposures if p.kind=='POSITION'}
    if observed_inventory != supplied_inventory or len(supplied_inventory)!=len(safety.account.exposures):
        raise ValueError('Context overrides native position inventory')
    for symbol,o in latest('SYMBOL').items():
        p,meta = o.normalized_payload,safety.instruments[symbol]
        if meta.symbol!=symbol or meta.account_currency!=a['currency'] or any(getattr(meta,key)!=number(p[native]) for key,native in
            (('tick_size','trade_tick_size'),('volume_min','volume_min'),('volume_max','volume_max'),('volume_step','volume_step'))):
            raise ValueError('Context overrides native metadata')
        if (p['currency_profit'] != a['currency'] or p['trade_mode'] != batch['full_trade_mode']
                or not meta.tradable or not meta.market_available
                or meta.value_per_price_unit_per_lot < max(number(p['trade_tick_value_profit']),number(p['trade_tick_value_loss'])) / number(p['trade_tick_size'])
                or meta.notional_per_price_unit_per_lot < number(p['trade_contract_size'])):
            raise ValueError('Unqualified native valuation/tradability context')
        quote = by_kind['QUOTE'][symbol]
        if safety.quotes[symbol].bid!=D(quote.normalized_payload['bid']) or safety.quotes[symbol].ask!=D(quote.normalized_payload['ask']) or safety.quotes[symbol].observed_at!=quote.broker_reported_at:
            raise ValueError('Context overrides native quote')
    return dict(evidence_id=hashed(sorted(o.observation_id for o in observations)),observed_at=batch['observed_at'],
        attestation=batch['attestation'],history_since=batch['history_since'],complete=True,orders=orders,deals=deals,
        positions=positions,protective_exit_orders=exits,safety=safety)
