"""P5 immutable research data. No lifecycle, broker or strategy dependencies."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Annotated, Literal

UTC = timezone.utc
VERSION = 'p5-data-v1'
VALIDATOR = 'strict-shape-completeness-discontinuity-v3'
INTERVALS = {'1M': 60, '1H': 3600, '4H': 14400}
MAPPINGS = {
    'XAUUSD': {'provider_symbol': 'XAUUSD', 'broker_symbol': 'XAUUSDm', 'basis': 'HistData bid gold/USD; broker equivalence unproven'},
    'XAGUSD': {'provider_symbol': 'XAGUSD', 'broker_symbol': 'XAGUSDm', 'basis': 'HistData bid silver/USD; broker equivalence unproven'},
    'USOIL': {'provider_symbol': 'WTIUSD', 'broker_symbol': 'USOILm', 'basis': 'HistData WTI/USD; contract/roll and broker basis unverified'},
}
EVTL_MAPPINGS = {
    symbol: {'provider_symbol': native, 'broker_symbol': broker,
             'basis': basis, 'upstream': 'Dukascopy, as reported by EV Trading Labs'}
    for symbol, native, broker, basis in (
        ('XAUUSD', 'XAUUSD', 'XAUUSDm', 'Gold/USD research proxy; broker equivalence unproven'),
        ('XAGUSD', 'XAGUSD', 'XAGUSDm', 'Silver/USD research proxy; broker equivalence unproven'),
        ('USOIL', 'WTI', 'USOILm', 'Provider WTI research proxy; exact upstream contract/roll construction unverified'),
    )
}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Explicit timezone required')
    return value.astimezone(UTC)


class Candle(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    instrument: Literal['XAUUSD', 'XAGUSD', 'USOIL']
    provider: Literal['HISTDATA', 'EV_TRADING_LABS'] = 'HISTDATA'
    provider_symbol: str
    timeframe: Literal['1M', '1H', '4H']
    opened: datetime
    closed: datetime
    open: Decimal = Field(gt=0, max_digits=30, decimal_places=12)
    high: Decimal = Field(gt=0, max_digits=30, decimal_places=12)
    low: Decimal = Field(gt=0, max_digits=30, decimal_places=12)
    close: Decimal = Field(gt=0, max_digits=30, decimal_places=12)
    volume: Decimal | None = Field(default=None, ge=0)
    volume_kind: Literal['NONE', 'TICK', 'REAL', 'UNKNOWN'] = 'NONE'
    spread: Decimal | None = Field(default=None, ge=0)
    timezone_evidence: str = Field(min_length=1)
    source_time: str = Field(min_length=1)
    price_basis: Literal['BID'] | None = None
    ask_ohlc: dict[str, Annotated[Decimal, Field(gt=0, max_digits=30, decimal_places=12)]] | None = None

    @model_validator(mode='after')
    def valid(self):
        a, b = utc(self.opened), utc(self.closed)
        seconds = INTERVALS[self.timeframe]
        if b-a != timedelta(seconds=seconds) or a.timestamp() % seconds:
            raise ValueError('Timeframe/alignment mismatch')
        mapping = MAPPINGS if self.provider == 'HISTDATA' else EVTL_MAPPINGS
        if self.provider_symbol != mapping[self.instrument]['provider_symbol']:
            raise ValueError('Provider symbol mismatch')
        if self.provider == 'HISTDATA':
            if self.price_basis is not None or self.ask_ohlc is not None:
                raise ValueError('Legacy HistData basis cannot be relabelled')
        else:
            if self.price_basis != 'BID' or self.ask_ohlc is None or set(self.ask_ohlc) != {'open','high','low','close'}:
                raise ValueError('Explicit bid and ask evidence required')
            ask = self.ask_ohlc
            if any(not v.is_finite() or v <= 0 for v in ask.values()):
                raise ValueError('Invalid ask price')
            if not ask['low'] <= min(ask['open'],ask['close']) <= max(ask['open'],ask['close']) <= ask['high']:
                raise ValueError('Ask OHLC geometry')
            if any(ask[k] < getattr(self,k) for k in ask):
                raise ValueError('Contradictory bid/ask evidence')
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError('OHLC geometry')
        if (self.volume is None) != (self.volume_kind == 'NONE'):
            raise ValueError('Volume semantics mismatch')
        object.__setattr__(self, 'opened', a)
        object.__setattr__(self, 'closed', b)
        return self

    def payload(self):
        result = self.model_dump(mode='json')
        if self.provider == 'HISTDATA':
            result.pop('price_basis')
            result.pop('ask_ohlc')
        elif self.ask_ohlc:
            result['ask_ohlc'] = {k: format(v, 'f').rstrip('0').rstrip('.') if '.' in format(v,'f') else format(v,'f')
                                  for k,v in self.ask_ohlc.items()}
        for key in ('open', 'high', 'low', 'close', 'volume', 'spread'):
            value = getattr(self, key)
            if value is not None:
                text = format(value, 'f')
                result[key] = text.rstrip('0').rstrip('.') if '.' in text else text
        return result


def series(candles, start, end, timeframe):
    """Classify evidence; never fabricate bars or guess market sessions."""
    start, end = utc(start), utc(end)
    step = INTERVALS[timeframe]
    if end <= start or start.timestamp() % step or end.timestamp() % step:
        raise ValueError('Aligned half-open range required')
    if (end-start).total_seconds()/step > 600000:
        raise ValueError('Bounded dataset required')
    issues, by_time, conflict = [], {}, set()
    previous = None
    identity = None
    for item in candles:
        c = Candle.model_validate(item.model_dump())
        key = (c.instrument, c.provider, c.provider_symbol, c.timeframe)
        if c.timeframe != timeframe or identity is not None and identity != key:
            raise ValueError('Mixed instrument/provider/timeframe')
        identity = key
        if not start <= c.opened < end:
            raise ValueError('Observation outside declared range')
        if previous is not None and c.opened < previous:
            issues.append({'kind': 'OUT_OF_ORDER', 'at': c.opened.isoformat()})
        previous = c.opened
        if c.opened in by_time:
            kind = 'IDENTICAL_DUPLICATE' if by_time[c.opened].payload() == c.payload() else 'CONFLICTING_DUPLICATE'
            issues.append({'kind': kind, 'at': c.opened.isoformat()})
            if kind == 'CONFLICTING_DUPLICATE': conflict.add(c.opened)
        else: by_time[c.opened] = c
    ordered = [by_time[t] for t in sorted(by_time) if t not in conflict]
    # Exact discontinuities are evidence, not an invented percentage cutoff or a repair.
    for left, right in zip(ordered, ordered[1:]):
        if right.opened == left.closed and (right.low > left.high or right.high < left.low):
            issues.append({'kind': 'DISJOINT_ADJACENT_PRICE_RANGES', 'at': right.opened.isoformat()})
    present = {c.opened for c in ordered}
    gaps = []
    stamp = start
    while stamp < end:
        if stamp not in present:
            first = stamp
            while stamp < end and stamp not in present: stamp += timedelta(seconds=step)
            gaps.append({'start': first.isoformat(), 'end': stamp.isoformat(),
                         'missing_count': int((stamp-first).total_seconds()/step),
                         'classification': 'UNKNOWN_SESSION_OR_MISSING', 'expected_seconds': step})
        else: stamp += timedelta(seconds=step)
    return ordered, issues, gaps


def resample(candles, timeframe):
    if timeframe not in {'1H', '4H'}: raise ValueError('Unsupported target')
    if not candles: return [], []
    source = candles[0].timeframe
    step, target = INTERVALS[source], INTERVALS[timeframe]
    if target <= step or target % step: raise ValueError('Invalid resampling')
    groups = {}
    for c in candles:
        if c.provider != 'HISTDATA':
            raise ValueError('Provider-specific bid/ask aggregation required')
        if c.timeframe != source or (c.instrument, c.provider_symbol) != (candles[0].instrument, candles[0].provider_symbol):
            raise ValueError('Mixed resampling series')
        anchor = int(c.opened.timestamp()) // target * target
        groups.setdefault(anchor, []).append(c)
    output, issues = [], []
    for anchor, group in sorted(groups.items()):
        group.sort(key=lambda c: c.opened)
        if [int(c.opened.timestamp()) for c in group] != list(range(anchor, anchor+target, step)):
            issues.append({'kind': 'INCOMPLETE_RESAMPLE', 'at': datetime.fromtimestamp(anchor, UTC).isoformat()})
            continue
        first = group[0]
        values = first.model_dump()
        with localcontext() as context:
            context.prec = 60
            total_volume = sum((c.volume for c in group), Decimal(0)) if all(c.volume is not None for c in group) else None
        values.update(timeframe=timeframe, opened=datetime.fromtimestamp(anchor, UTC),
                      closed=datetime.fromtimestamp(anchor+target, UTC),
                      high=max(c.high for c in group), low=min(c.low for c in group), close=group[-1].close,
                      volume=total_volume,
                      volume_kind=first.volume_kind if all(c.volume_kind == first.volume_kind for c in group) else 'NONE',
                      spread=None, source_time=f'{source}:UTC-epoch-left-closed:{VERSION}')
        output.append(Candle(**values))
    return output, issues


class MarketStore:
    """Dedicated root only. Fixture roots must live under OS temporary storage."""
    def __init__(self, root=None, *, fixture=False):
        default = Path(__file__).resolve().parents[3] / 'research/p5-market-data'
        self.root = Path(root or default).absolute()
        resolved = self.root.resolve()
        permitted = Path(tempfile.gettempdir()).resolve() if fixture else default.resolve()
        if (not fixture and resolved != permitted or fixture and (resolved == permitted or not resolved.is_relative_to(permitted))
                or any(p.lower() in {'private', '.env', '.p3-verification'} for p in self.root.parts)):
            raise ValueError('Research storage boundary')
        if any(p.exists() and (p.is_symlink() or p.is_junction()) for p in [self.root, *self.root.parents]):
            raise ValueError('Linked research root forbidden')
        self.path = self.root / 'market-data.sqlite3'
        self.root.mkdir(parents=True, exist_ok=True)
        marker = self.root / '.p5-research'
        if not marker.exists():
            if list(self.root.iterdir()): raise ValueError('Unowned research directory')
            marker.write_text(VERSION, encoding='ascii')
        if marker.read_text(encoding='ascii') != VERSION: raise ValueError('Research marker mismatch')
        if self.path.exists() and (self.path.is_symlink() or self.path.stat().st_nlink != 1):
            raise ValueError('Linked database forbidden')
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS p5_schema(version INTEGER PRIMARY KEY);
            INSERT OR IGNORE INTO p5_schema VALUES(1);
            CREATE TABLE IF NOT EXISTS raw(id TEXT PRIMARY KEY, body BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bars(dataset TEXT NOT NULL, opened TEXT NOT NULL, payload TEXT NOT NULL,
              PRIMARY KEY(dataset,opened), FOREIGN KEY(dataset) REFERENCES datasets(id));
            CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY, dataset TEXT, raw_id TEXT,
              ingested_at TEXT NOT NULL, provenance TEXT NOT NULL);
            ''')
            for table in ('raw', 'datasets', 'bars', 'receipts'):
                for action in ('UPDATE', 'DELETE'):
                    c.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Immutable P5 evidence'); END")

    def connect(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c

    def save(self, instrument, timeframe, start, end, candles, *, raw, provenance, issues=(), parent=None, derivation=None, provider='HISTDATA'):
        if instrument not in MAPPINGS: raise ValueError('Unknown mapping')
        if provider not in {'HISTDATA','EV_TRADING_LABS'}: raise ValueError('Unknown provider')
        candles = list(candles)
        if any(c.instrument != instrument or c.provider != provider for c in candles):
            raise ValueError('Instrument/provider mismatch')
        ordered, checks, gaps = series(candles, start, end, timeframe)
        if any(c.instrument != instrument or c.provider != provider for c in ordered): raise ValueError('Instrument/provider mismatch')
        raw_id = hashlib.sha256(raw).hexdigest()
        quality = [json.loads(item) for item in sorted({encode(item) for item in list(issues)+checks})]
        manifest = dict(version=VERSION, mapping_version='histdata-v1', instrument=instrument,
                        mapping=MAPPINGS[instrument], provider='HISTDATA', timeframe=timeframe,
                        start=utc(start).isoformat(), end=utc(end).isoformat(),
                        normalization=VERSION, resampling='UTC-epoch-left-closed-complete-only-v1',
                        validation=VALIDATOR, source_timeframe='1M',
                        content_hash=digest([c.payload() for c in ordered]),
                        gaps=gaps, issues=quality, real_data=not provenance.get('fixture', False),
                        bar_count=len(ordered), status='REVIEW_REQUIRED' if gaps or quality or not ordered else 'VALIDATED')
        if derivation is not None:
            manifest['derivation'] = json.loads(encode(derivation))
            manifest['resampling'] = derivation['resampling_rule']
        if provider == 'EV_TRADING_LABS':
            manifest.update(provider=provider, mapping=EVTL_MAPPINGS[instrument], mapping_version='evtl-v1',
                            normalization='evtl-json-v1', source_timeframe=timeframe,
                            resampling='provider-precomputed-M1-resample', price_basis='BID_WITH_SEPARATE_ASK_OHLC',
                            volume_semantics='Provider v; units and meaning unverified',
                            attribution='EV Trading Labs; upstream Dukascopy as reported by provider')
        identity = digest(manifest)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if parent:
                prior = c.execute('SELECT manifest FROM datasets WHERE id=?', (parent,)).fetchone()
                if not prior: raise ValueError('Unknown parent dataset')
                prior = json.loads(prior[0])
                if (prior['instrument'], prior['timeframe'], prior['provider']) != (instrument, timeframe, provider):
                    raise ValueError('Incompatible dataset parent')
            c.execute('INSERT OR IGNORE INTO raw VALUES(?,?)', (raw_id, raw))
            c.execute('INSERT OR IGNORE INTO datasets VALUES(?,?)', (identity, encode(manifest)))
            c.executemany('INSERT OR IGNORE INTO bars VALUES(?,?,?)', [(identity, x.opened.isoformat(), encode(x.payload())) for x in ordered])
            p = dict(provenance, parent_dataset=parent, raw_id=raw_id)
            if not c.execute('SELECT 1 FROM receipts WHERE dataset=? AND raw_id=? AND provenance=?', (identity, raw_id, encode(p))).fetchone():
                c.execute('INSERT INTO receipts(dataset,raw_id,ingested_at,provenance) VALUES(?,?,?,?)',
                          (identity, raw_id, datetime.now(UTC).isoformat(), encode(p)))
        return identity

    def query(self, dataset, *, start=None, end=None, research=True):
        with self.connect() as c:
            row = c.execute('SELECT manifest FROM datasets WHERE id=?', (dataset,)).fetchone()
            if not row: raise ValueError('Unknown dataset')
            m = json.loads(row[0])
            a = utc(start).isoformat() if start else m['start']
            b = utc(end).isoformat() if end else m['end']
            if not m['start'] <= a < b <= m['end']: raise ValueError('Range outside dataset')
            if datetime.fromisoformat(a).timestamp() % INTERVALS[m['timeframe']] or datetime.fromisoformat(b).timestamp() % INTERVALS[m['timeframe']]:
                raise ValueError('Query must use complete candle boundaries')
            if research and (m['status'] != 'VALIDATED' or not m['real_data'] or m['validation'] != VALIDATOR):
                raise ValueError('Dataset not qualified for research consumption')
            bars = [json.loads(x[0]) for x in c.execute('SELECT payload FROM bars WHERE dataset=? AND opened>=? AND opened<? ORDER BY opened', (dataset, a, b))]
            provenance = [dict(x) for x in c.execute('SELECT raw_id,ingested_at,provenance FROM receipts WHERE dataset=? ORDER BY id', (dataset,))]
        return dict(dataset_id=dataset, manifest=m, candles=bars, provenance=provenance)
