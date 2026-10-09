"""Operator-injected MT5 boundary. No MT5 import, initialize, login or secrets.

The owner must separately qualify the session and evidence reader. Native MT5
cannot atomically bind order_send to an account; an isolated, exclusively owned
demo terminal remains an operator prerequisite, not a configurable live unlock.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR, localcontext

from .execution_contracts import Attestation, BrokerSnapshot, SubmissionResult
from .ledger import hashed
from .safety import fresh, number
from .mt5_evidence import account as normalize_account

D = Decimal


class MT5DemoAdapter:
    scope = 'MT5_DEMO'

    def __init__(self, client, account, *, session_id, snapshot_reader, clock=None):
        if account.evidence_source != 'MT5_DEMO' or not session_id.strip():
            raise ValueError('Explicit operator-bound demo session required')
        self.client, self.account = client, account
        self.session_id, self.snapshot_reader = session_id, snapshot_reader
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.observations = []

    def attest(self):
        c = self.client
        a, t = c.account_info(), c.terminal_info()
        attestation, _ = normalize_account(c,a,t,self.account,self.session_id,self.clock())
        return attestation

    def snapshot(self, since):
        before = self.attest()
        # Reader is an explicitly trusted adapter, never HTTP evidence. It must
        # attest complete broker inventories, cash flows, costs and conversion.
        self.observations = []
        try:
            raw = self.snapshot_reader(self.client, since, before)
        finally:
            self.observations = list(getattr(self.snapshot_reader, 'observations', ()))
        if isinstance(raw, dict) and 'native_observations' in raw:
            self.attest()
            return raw  # Journal persistence/projection belongs to the engine transaction.
        snapshot = BrokerSnapshot.model_validate(raw.model_dump() if isinstance(raw, BrokerSnapshot) else raw)
        after = self.attest()
        if (snapshot.attestation.account_key != before.account_key or snapshot.attestation.session_id != before.session_id
                or after.session_id != before.session_id or snapshot.attestation.scope != self.scope):
            raise ValueError('Snapshot crossed account/session boundary')
        return snapshot

    def submit(self, command):
        with localcontext() as ctx:
            ctx.prec = 40
            return self._submit(command)

    def _submit(self, command):
        before = self.attest()
        if command['account_key'] != before.account_key or command['session_id'] != before.session_id:
            raise ValueError('Command account/session mismatch')
        c = self.client
        info, tick = c.symbol_info(command['symbol']), c.symbol_info_tick(command['symbol'])
        if info is None or tick is None:
            raise ValueError('Missing instrument/quote')
        fresh(datetime.fromtimestamp(tick.time_msc / 1000, timezone.utc), self.clock(), 3)
        point, bid, ask = number(info.point), number(tick.bid), number(tick.ask)
        if ask < bid:
            raise ValueError('Crossed quote')
        buy = command['direction'] == 'BUY'
        if command['direction'] not in {'BUY','SELL'} or command['entry_type'] not in {'MARKET','LIMIT'}:
            raise ValueError('Unsupported economic action')
        base = number(command['base_entry'])
        stop, target, volume = number(command['stop']), number(command['nearest_tp']), number(command['volume'])
        side = ask if buy else bid
        distance = abs(base-stop)
        if distance <= 0 or abs(side-base) > distance*D('0.05') or ask-bid > distance*D('0.10'):
            raise ValueError('Execution quality changed')
        if side != base:
            raise ValueError('Quote changed after P2 gate; fresh admission required')
        if not (stop < side < target if buy else target < side < stop):
            raise ValueError('Invalid executable geometry')
        if not number(info.volume_min) <= volume <= number(info.volume_max) or volume % number(info.volume_step):
            raise ValueError('Broker volume metadata changed')
        if command.get('minimum_volume_only') is True and volume != number(info.volume_min):
            raise ValueError('Operator smoke must use current broker minimum volume')
        if any(v % number(info.trade_tick_size) for v in (stop,target)):
            raise ValueError('Broker price metadata changed')
        if info.trade_mode != c.SYMBOL_TRADE_MODE_FULL:
            raise ValueError('Unsupported restricted trading mode')
        if info.trade_stops_level < 0 or min(abs(side-stop),abs(target-side)) < D(str(info.trade_stops_level))*point:
            raise ValueError('Broker stops constraint')
        is_limit = command['entry_type']=='LIMIT'
        price = number(command['limit_entry']) if is_limit else side
        if is_limit and (abs(side-price)>distance*D('0.05') or not (stop<price<=ask if buy else bid<=price<stop)):
            raise ValueError('Contradictory LIMIT')
        # Floor points: conversion must not increase the authorized allowance.
        deviation = int((distance*D('0.05')/point).to_integral_value(rounding=ROUND_FLOOR))
        if is_limit:
            filling = c.ORDER_FILLING_RETURN
        elif info.filling_mode & 1:
            filling = c.ORDER_FILLING_FOK
        elif info.filling_mode & 2:
            filling = c.ORDER_FILLING_IOC
        else:
            raise ValueError('Unsupported fill policy; no fallback')
        request = dict(action=c.TRADE_ACTION_PENDING if is_limit else c.TRADE_ACTION_DEAL,
                       symbol=command['symbol'], volume=float(volume), sl=float(stop),tp=float(target),
                       type=(c.ORDER_TYPE_BUY_LIMIT if buy else c.ORDER_TYPE_SELL_LIMIT) if is_limit else
                            (c.ORDER_TYPE_BUY if buy else c.ORDER_TYPE_SELL),
                       deviation=deviation,magic=command['magic'],comment=command['correlation'],
                       type_time=c.ORDER_TIME_GTC,type_filling=filling)
        if is_limit or info.trade_exemode != c.SYMBOL_TRADE_EXECUTION_MARKET:
            request['price'] = float(price)
        # Refuse decimal values that cannot survive the Python/MT5 numeric boundary.
        if any(D(str(request[k])) != value for k,value in (('volume',volume),('sl',stop),('tp',target))):
            raise ValueError('Unsupported broker numeric representation')
        if 'price' in request and D(str(request['price'])) != price:
            raise ValueError('Unsupported broker price representation')
        self.attest()
        if self.clock() >= datetime.fromisoformat(command['valid_until']):
            raise ValueError('Admission evidence expired before transport send')
        result = c.order_send(request)  # One call only. No retry/requote loop.
        after = self.attest()
        if result is None:
            outcome, order, retcode = 'AMBIGUOUS', None, None
        else:
            retcode = result.retcode
            order = str(result.order) if result.order else None
            if retcode in {c.TRADE_RETCODE_DONE,c.TRADE_RETCODE_DONE_PARTIAL,c.TRADE_RETCODE_PLACED} and order:
                outcome = 'ACKNOWLEDGED'
            elif retcode == c.TRADE_RETCODE_REJECT and not order and not result.deal:
                outcome = 'REJECTED'
            else:
                # Timeout, connection error, unknown and mixed results retain risk.
                outcome = 'AMBIGUOUS'
        return SubmissionResult(evidence_id=hashed([command['attempt_id'],retcode,order]),observed_at=self.clock(),
                                attestation=after,outcome=outcome,broker_order_id=order,retcode=retcode)
