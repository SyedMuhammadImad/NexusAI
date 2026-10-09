"""P6 offline research, never an execution adapter or an economic approval."""
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal as D, localcontext
from functools import cached_property
import json

from .market_data import Candle, MarketStore, digest, encode, utc
from .research_reader import ResearchDatasetReader
from .research_strategies import Features, FEATURE_SPEC, RULE_SPEC

ENGINE = 'p6-replay-v3'
OUTCOMES = ('WIN', 'LOSS', 'BREAKEVEN', 'TIMEOUT', 'AMBIGUOUS', 'UNKNOWN')


def fixture_store(store):
    from pathlib import Path
    return store.root.resolve() != (Path(__file__).resolve().parents[3] / 'research/p5-market-data').resolve()


def number(value, *, positive=False):
    if isinstance(value, bool): raise ValueError('Boolean is not a price')
    result = D(str(value))
    if not result.is_finite() or result < 0 or positive and result == 0:
        raise ValueError('Finite nonnegative number required')
    return result


@dataclass(frozen=True)
class Costs:
    slippage_stop_fraction: str = '0.05'
    commission_per_unit_round_trip: str | None = None
    commission_evidence: str | None = None
    version: str = 'p6-costs-v1'

    def __post_init__(self):
        if self.version != 'p6-costs-v1' or number(self.slippage_stop_fraction) > 1:
            raise ValueError('Unsupported cost model')
        if self.commission_per_unit_round_trip is not None:
            number(self.commission_per_unit_round_trip)
            if not isinstance(self.commission_evidence, str) or not self.commission_evidence.strip():
                raise ValueError('Commission requires evidence and quote-currency/unit semantics')
        elif self.commission_evidence is not None:
            raise ValueError('Commission evidence without a value')

    @property
    def commission(self):
        return number(self.commission_per_unit_round_trip) if self.commission_per_unit_round_trip is not None else D(0)

    def payload(self):
        return dict(asdict(self), commission_status='EXCLUDED_UNKNOWN' if self.commission_per_unit_round_trip is None else 'EXPLICIT',
                    units='quote currency per one research instrument unit; NOT lots or account PnL')


@dataclass(frozen=True)
class ResearchData:
    dataset_id: str
    qualification_id: str
    start: datetime
    end: datetime
    bars: tuple[Candle, ...]
    provenance: str
    fixture: bool = True

    def __post_init__(self):
        if utc(self.start) >= utc(self.end) or not self.bars:
            raise ValueError('Nonempty qualified range required')
        first = self.bars[0]
        if not self.fixture:
            evidence = json.loads(self.provenance)
            q, m = evidence['qualification'], evidence['manifest']
            if (digest(q) != self.qualification_id or digest(m) != self.dataset_id or
                    q['dataset_id'] != self.dataset_id or not m['real_data'] or not evidence['receipts'] or
                    q['state'] not in {'QUALIFIED','QUALIFIED_WITH_KNOWN_LIMITATIONS'}):
                raise ValueError('Qualified real provenance required')
        for i, b in enumerate(self.bars):
            Candle.model_validate(b.model_dump())
            if b.ask_ohlc is None or b.price_basis != 'BID': raise ValueError('Bid AND ask evidence required')
            if (b.instrument, b.provider, b.timeframe) != (first.instrument, first.provider, first.timeframe):
                raise ValueError('Mixed data identity')
            if not self.start <= b.opened < b.closed <= self.end or i and self.bars[i-1].closed > b.opened:
                raise ValueError('Out of range, duplicate or unordered bars')

    @classmethod
    def load(cls, reader, qualification_id, *, dataset_id, start, end):
        if type(reader) is not ResearchDatasetReader or fixture_store(reader.store):
            raise ValueError('Production research requires the qualified P5 reader')
        view = reader.query(qualification_id, start=start, end=end)
        q, m = view['qualification'], view['manifest']
        if view['dataset_id'] != dataset_id or digest(m) != dataset_id or digest(q) != qualification_id:
            raise ValueError('Pinned identity mismatch')
        if not m['real_data'] or q['state'] not in {'QUALIFIED','QUALIFIED_WITH_KNOWN_LIMITATIONS'}:
            raise ValueError('Real qualified data required')
        # Verify immutable storage content, not merely a trustworthy-looking manifest.
        full = reader.store.query(dataset_id, research=False)
        if digest(full['candles']) != m['content_hash']:
            raise ValueError('Pinned dataset content changed')
        provenance = encode(dict(manifest=m, qualification=q, receipts=view['provenance']))
        return cls(dataset_id, qualification_id, utc(start), utc(end),
                   tuple(Candle.model_validate(b) for b in view['candles']), provenance, fixture=False)

    def identity(self):
        b = self.bars[0]
        source = json.loads(self.provenance)
        return dict(dataset_id=self.dataset_id, qualification_id=self.qualification_id,
                    instrument=b.instrument, provider=b.provider, timeframe=b.timeframe,
                    qualification_state=source.get('qualification',{}).get('state','FIXTURE_ONLY'),
                    price_basis='BID_WITH_SEPARATE_ASK_OHLC',
                    start=self.start.isoformat(), end=self.end.isoformat(),
                    rows_hash=digest([b.payload() for b in self.bars]),
                    provenance_hash=digest(source), fixture=self.fixture)

    @cached_property
    def closed_frames(self):
        return tuple(frames(self))


def frames(data, context=None):
    if context is not None and (context.bars[0].timeframe != '4H' or data.bars[0].timeframe != '1H'
            or context.start > data.start or context.end < data.end
            or context.bars[0].instrument != data.bars[0].instrument or context.bars[0].provider != data.bars[0].provider):
        raise ValueError('Invalid context identity/range')
    if context is not None and context.fixture != data.fixture:
        raise ValueError('Cannot mix fixture and real data')
    builder, j, latest = Features(), 0, None
    for bar in data.bars:
        if context:
            while j < len(context.bars) and context.bars[j].closed <= bar.closed:
                latest = context.bars[j]
                j += 1
        yield builder.push(bar, latest)


def validate_geometry(direction, entry, stop, target, costs=Costs(), slip=D(0)):
    if direction not in {'BUY','SELL'}: raise ValueError('Unknown direction')
    entry, stop, target = (number(x, positive=True) for x in (entry, stop, target))
    if not (stop < entry < target if direction == 'BUY' else target < entry < stop):
        raise ValueError('Invalid geometry')
    # Include adverse exit slippage in both numerator and denominator, not just entry.
    loss = abs(entry-stop)+number(slip)+costs.commission
    reward = abs(target-entry)-number(slip)-costs.commission
    if reward/loss < D('1.5'): raise ValueError('Cost-adjusted R below 1.5')
    return loss, reward/loss


def make_signal(strategy, frame, data):
    direction = strategy.direction(frame)
    if direction is None: return None
    if direction not in {'BUY','SELL'}: raise ValueError('Unknown strategy action')
    atr = frame.features.get('atr')
    if atr is None or not atr.is_finite() or atr <= 0: raise ValueError('Missing/invalid intentional ATR stop')
    parameters = dict(strategy.parameters)
    distance = atr*number(parameters['stop_atr'], positive=True)
    reference = frame.bar.ask_ohlc['close'] if direction == 'BUY' else frame.bar.close
    sign = D(1) if direction == 'BUY' else D(-1)
    stop = reference-sign*distance
    target = reference+sign*distance*number(parameters['reward_r'], positive=True)
    validate_geometry(direction, reference, stop, target)
    result = dict(strategy_id=strategy.strategy_id, strategy_version=strategy.version,
        family=strategy.family, instrument=frame.bar.instrument, timeframe=frame.bar.timeframe,
        signal_timestamp=frame.bar.closed.isoformat(), direction=direction, entry_semantics='NEXT_OBSERVED_BAR_MARKET_OPEN',
        entry_reference=str(reference), stop_loss=str(stop), take_profit=str(target),
        features={k:str(v) for k,v in frame.features.items()}, rationale=strategy.rule,
        context_closed_at=frame.context.closed.isoformat() if frame.context else None,
        dataset_id=data.dataset_id, provider=frame.bar.provider, qualification_id=data.qualification_id,
        execution_eligible=False)
    result['signal_id'] = digest(result)
    return result


def canonical_signal(signal):
    """Representation only: P4 source registry still denies economic strategy use."""
    from .lifecycle_contracts import CanonicalSignal
    t = datetime.fromisoformat(signal['signal_timestamp']).timestamp()
    identity = signal['signal_id']
    return CanonicalSignal(signal_id=identity, source_type='NEXUSAI_STRATEGY',
        source_id=signal['strategy_id']+':'+signal['strategy_version'], source_message_id=identity,
        source_event_id=identity, source_timestamp=t, received_timestamp=t, parsed_timestamp=t,
        symbol=signal['instrument'], direction=signal['direction'], entry_type='MARKET',
        entry=float(signal['entry_reference']), stop_loss=float(signal['stop_loss']),
        take_profit=(float(signal['take_profit']),), timeframe={'1H':'H1','4H':'H4'}[signal['timeframe']],
        raw_source_hash=digest(signal))


def barrier(bar, direction, stop, target):
    side = {k:getattr(bar,k) for k in ('open','high','low','close')} if direction == 'BUY' else bar.ask_ohlc
    if direction == 'BUY':
        if side['open'] <= stop: return 'LOSS', side['open'], 'OPEN_GAP'
        if side['open'] >= target: return 'WIN', target, 'OPEN_TARGET_NO_IMPROVEMENT'
        loss, win = side['low'] <= stop, side['high'] >= target
    else:
        if side['open'] >= stop: return 'LOSS', side['open'], 'OPEN_GAP'
        if side['open'] <= target: return 'WIN', target, 'OPEN_TARGET_NO_IMPROVEMENT'
        loss, win = side['high'] >= stop, side['low'] <= target
    if loss and win: return 'AMBIGUOUS', None, 'BOTH_BARRIERS_IN_BAR'
    if loss: return 'LOSS', stop, 'BARRIER'
    if win: return 'WIN', target, 'BARRIER'
    return None


def finer_bars(bar, lower):
    if lower is None: return ()
    if bar.timeframe != '4H' or lower.bars[0].timeframe != '1H' or lower.bars[0].instrument != bar.instrument or lower.bars[0].provider != bar.provider:
        raise ValueError('Invalid disambiguation series')
    rows = tuple(b for b in lower.bars if bar.opened <= b.opened and b.closed <= bar.closed)
    if not rows: return ()
    # Qualified closure gaps may omit hours, but both OHLC sides must reconstruct exactly.
    for side in ('bid','ask'):
        get = lambda b,k: getattr(b,k) if side == 'bid' else b.ask_ohlc[k]
        aggregate = dict(open=get(rows[0],'open'), close=get(rows[-1],'close'),
                         high=max(get(b,'high') for b in rows), low=min(get(b,'low') for b in rows))
        if any(aggregate[k] != get(bar,k) for k in aggregate): return ()
    return rows


def reconstruct(signal, bars, *, costs=Costs(), horizon=24, lower=None):
    if type(horizon) is not int or not 1 <= horizon <= 10000: raise ValueError('Invalid horizon')
    if not bars: return dict(outcome='UNKNOWN', reason='NO_ENTRY_BAR', r_multiple=None), -1
    first = bars[0]
    if first.opened < datetime.fromisoformat(signal['signal_timestamp']): raise ValueError('Entry before signal')
    direction = signal['direction']
    if direction not in {'BUY','SELL'}: raise ValueError('Unknown direction')
    stop, target = number(signal['stop_loss'],positive=True), number(signal['take_profit'],positive=True)
    base = first.ask_ohlc['open'] if direction == 'BUY' else first.open
    slip = abs(base-stop)*number(costs.slippage_stop_fraction)
    sign = D(1) if direction == 'BUY' else D(-1)
    entry = base+sign*slip
    loss_budget, rr = validate_geometry(direction,entry,stop,target,costs,slip)
    result = dict(entry=str(entry), base_entry=str(base), entry_at=first.opened.isoformat(), stop_loss=str(stop),
                  take_profit=str(target), direction=direction, cost_model=costs.payload(), slippage_per_side=str(slip),
                  initial_loss_per_unit=str(loss_budget), admission_r=str(rr), broker_observed=False,
                  pnl_units='quote currency per instrument unit, not account PnL')
    for i, bar in enumerate(bars[:horizon]):
        hit = barrier(bar, direction, stop, target)
        evidence_bar = bar
        resolution_id = None
        if hit and hit[0] == 'AMBIGUOUS' and lower:
            for small in finer_bars(bar, lower):
                found = barrier(small, direction, stop, target)
                if found:
                    hit, evidence_bar, resolution_id = found, small, lower.dataset_id
                    break
        if not hit and i+1 == horizon:
            mark = bar.close if direction == 'BUY' else bar.ask_ohlc['close']
            hit = ('TIMEOUT', mark, 'FIXED_OBSERVED_BAR_HORIZON')
        if hit:
            outcome, price, reason = hit
            known_exit = (evidence_bar.opened if reason.startswith('OPEN_') else
                          (evidence_bar.closed if outcome == 'TIMEOUT' else None))
            result.update(outcome=outcome, reason=reason, exit_interval_start=evidence_bar.opened.isoformat(),
                          exit_interval_end=evidence_bar.closed.isoformat(),
                          exit_timestamp=known_exit.isoformat() if known_exit else None,
                          lower_dataset_id=resolution_id, evidence_hash=digest(evidence_bar.payload()),
                          held_bars=i+1, holding_hours_upper_bound=str(D(str(((known_exit or evidence_bar.closed)-first.opened).total_seconds()))/3600))
            if price is not None:
                exit_price = price-sign*slip
                if exit_price <= 0: raise ValueError('Modeled exit nonpositive')
                gross = sign*(exit_price-entry)
                pnl = gross-costs.commission
                result.update(exit_price=str(exit_price), gross_pnl_per_unit=str(gross), pnl_per_unit=str(pnl),
                              r_multiple=str(pnl/loss_budget))
            else:
                result.update(exit_price=None, pnl_per_unit=None, r_multiple=None)
            return result, i
    result.update(outcome='UNKNOWN', reason='RIGHT_CENSORED_AT_RESEARCH_SPLIT', r_multiple=None,
                  held_bars=len(bars), exit_timestamp=None)
    return result, len(bars)-1


def metrics(trades, signals, costs):
    counts = Counter(t['outcome'] for t in trades)
    resolved = sum(counts[k] for k in ('WIN','LOSS','BREAKEVEN'))
    priced = [D(t['r_multiple']) for t in trades if t.get('r_multiple') is not None]
    equity = peak = drawdown = D(0)
    streak = longest = 0
    for t in trades:
        value = t.get('r_multiple')
        if value is None:
            streak = 0
            continue
        r = D(value)
        equity += r
        peak = max(peak, equity)
        drawdown = max(drawdown, peak-equity)
        streak = streak+1 if r < 0 else 0
        longest = max(longest, streak)
    positives = sum((r for r in priced if r > 0), D(0))
    negatives = -sum((r for r in priced if r < 0), D(0))
    holding = [D(t['holding_hours_upper_bound']) for t in trades if t.get('holding_hours_upper_bound') is not None]
    exclusions = counts['AMBIGUOUS']+counts['UNKNOWN']
    avg = str(sum(priced)/len(priced)) if priced else None
    return dict(signal_count=len(signals), research_trade_count=len(trades),
        outcomes={k:counts[k] for k in OUTCOMES}, resolved_barrier_denominator=resolved,
        win_rate=str(D(counts['WIN'])/resolved) if resolved else None,
        average_r=avg, expectancy_r=avg, total_r=str(equity), priced_denominator=len(priced),
        max_drawdown_r=str(drawdown), profit_factor=str(positives/negatives) if negatives else None,
        profit_factor_reason=None if negatives else 'NO_NEGATIVE_PRICED_R',
        sharpe=None, sharpe_reason='NO_ACCOUNT_RETURN_SERIES_OR_APPROVED_SAMPLE_THRESHOLD',
        return_to_drawdown=str(equity/drawdown) if drawdown else None,
        risk_adjusted_warning='Descriptive trade-R ratio only; not annualized or statistical qualification',
        average_holding_hours_upper_bound=str(sum(holding)/len(holding)) if holding else None,
        longest_negative_priced_streak=longest,
        excluded_outcome_count=exclusions, excluded_outcome_rate=str(D(exclusions)/len(trades)) if trades else None,
        signal_dispositions=dict(Counter(s['disposition'] for s in signals)), cost_assumptions=costs.payload(),
        limitations='R sums include priced TIMEOUT; win rate excludes TIMEOUT. Unknown/ambiguous PnL excluded, not zero. No compounded account return.')


def replay(data, strategy, *, start, end, costs=Costs(), horizon=24, context=None, lower=None):
    start, end = utc(start), utc(end)
    if type(horizon) is not int or not 1 <= horizon <= 10000: raise ValueError('Invalid horizon')
    if data.bars[0].timeframe not in {'1H','4H'}: raise ValueError('Unsupported research timeframe')
    if not data.start <= start < end <= data.end: raise ValueError('Split outside qualified data')
    if lower and (lower.start > data.start or lower.end < data.end): raise ValueError('Lower range incomplete')
    if lower and (lower.fixture != data.fixture or lower.bars[0].timeframe != '1H'
                  or data.bars[0].timeframe != '4H' or lower.bars[0].instrument != data.bars[0].instrument
                  or lower.bars[0].provider != data.bars[0].provider):
        raise ValueError('Invalid lower dataset identity')
    config = dict(engine=ENGINE, data=data.identity(), strategy=asdict(strategy), costs=costs.payload(),
                  feature_specification=FEATURE_SPEC, rule_specification=RULE_SPEC.get(strategy.rule,{}),
                  start=start.isoformat(), end=end.isoformat(), horizon=horizon,
                  context=context.identity() if context else None, lower=lower.identity() if lower else None,
                  execution='HARD_DISABLED', precision=40, split_policy='FLAT_START_RIGHT_CENSOR_NO_CROSS_SPLIT_LABELS')
    run_id = digest(config)
    signals, trades, busy_until = [], [], -1
    with localcontext() as ctx:
        ctx.prec = 40
        for i, frame in enumerate(frames(data, context) if context else data.closed_frames):
            if frame.bar.closed < start or frame.bar.closed >= end: continue
            try:
                signal = make_signal(strategy, frame, data)
            except ValueError as exc:
                signals.append(dict(signal_timestamp=frame.bar.closed.isoformat(), disposition='INVALID_SIGNAL', reason=str(exc)))
                continue
            if signal is None: continue
            signal['disposition'] = 'BUSY' if i <= busy_until else 'CANDIDATE'
            signals.append(signal)
            if i <= busy_until: continue
            available = tuple(b for b in data.bars[i+1:] if start <= b.opened and b.closed <= end)
            if not available:
                signal['disposition'] = 'NO_ENTRY_BAR'
                continue
            try:
                outcome, used = reconstruct(signal, available, costs=costs, horizon=horizon, lower=lower)
            except ValueError as exc:
                signal.update(disposition='REJECTED_ADMISSION', reason=str(exc))
                continue
            signal['disposition'] = 'RESEARCH_TRADE'
            trade = dict(outcome, signal=signal.copy(), run_id=run_id, dataset_id=data.dataset_id,
                         context_dataset_id=context.dataset_id if context else None,
                         lower_qualification_id=lower.qualification_id if lower else None)
            trade['research_trade_id'] = digest(dict(run_id=run_id, signal_id=signal['signal_id']))
            trades.append(trade)
            busy_until = i+1+used
        eligible = (strategy.eligibility if data.bars[0].timeframe in strategy.timeframes
                    and data.bars[0].instrument in strategy.instruments else 'INSUFFICIENT_DATA')
        report = dict(run_id=run_id, configuration=config, signals=signals, trades=trades,
                      metrics=metrics(trades,signals,costs), eligibility=eligible)
        report['artifact_id'] = digest(report)
        return json.loads(encode(report))


class ResearchLedger:
    """Additive research-only schema 7; each entire replay commits atomically."""
    def __init__(self, store):
        if type(store) is not MarketStore: raise ValueError('Owned research store required')
        self.store = store
        with store.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS p6_runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS p6_trades(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES p6_runs(id), payload TEXT NOT NULL);
                INSERT OR IGNORE INTO p5_schema VALUES(7);
            ''')
            for table in ('p6_runs','p6_trades'):
                for action in ('UPDATE','DELETE'):
                    c.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Immutable P6 research'); END")

    def save(self, report, *, checkpoint=lambda: None):
        content = {k:v for k,v in report.items() if k != 'artifact_id'}
        if digest(content) != report['artifact_id'] or digest(report['configuration']) != report['run_id']:
            raise ValueError('Artifact identity mismatch')
        if report['configuration']['data']['fixture'] and not fixture_store(self.store):
            raise ValueError('Fixture cannot enter real research ledger')
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT payload FROM p6_runs WHERE id=?',(report['run_id'],)).fetchone()
            payload = encode(report)
            if old:
                if old[0] != payload: raise ValueError('Same run changed result')
                return report['artifact_id']
            c.execute('INSERT INTO p6_runs VALUES(?,?)',(report['run_id'],payload))
            checkpoint()
            for t in report['trades']:
                c.execute('INSERT INTO p6_trades VALUES(?,?,?)',(t['research_trade_id'],report['run_id'],encode(t)))
        return report['artifact_id']

    def read(self, run_id):
        with self.store.connect() as c:
            row = c.execute('SELECT payload FROM p6_runs WHERE id=?',(run_id,)).fetchone()
        if row is None: raise ValueError('Unknown immutable research run')
        report = json.loads(row[0])
        if digest({k:v for k,v in report.items() if k != 'artifact_id'}) != report['artifact_id']:
            raise ValueError('Corrupt result')
        return report
