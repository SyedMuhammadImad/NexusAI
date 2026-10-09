"""P6 closed-bar research rules. No account, outcome, clock or execution inputs."""
from dataclasses import dataclass
from decimal import Decimal as D, localcontext
from types import MappingProxyType
from typing import Mapping

from .market_data import Candle

VERSION = 'p6-rules-v1'
ZERO = D(0)
FEATURE_SPEC = {
    'version':'p6-features-v1', 'precision':40, 'price_side':'BID',
    'ema_periods':[9,12,20,21,26,50,200], 'ema_seed':'first N closes SMA',
    'macd':[12,26,9], 'rsi_periods':[2,14], 'rsi_smoothing':'Wilder; flat=50, loss=0 and gain>0 =>100',
    'atr_period':14, 'atr_smoothing':'Wilder; first TR=high-low',
    'adx_variant':'14-bar rolling directional sums, then 14-DX arithmetic mean; NOT Wilder ADX',
    'stochastic_williams_period':14, 'bollinger':[20,2,'population standard deviation'],
    'cci':[20,'0.015','mean absolute typical-price deviation'], 'supertrend_atr_multiplier':3,
    'prior_range_bars':20, 'hhhl_disjoint_windows':[20,20], 'divergence_endpoint_lag':10,
    'day_week':'previous completely observed UTC date/ISO week; first period excluded',
    'sessions':'fixed UTC v1; London range 06-08, signals 08-11; NY range 11-13, signals 13-16; H1 only',
}
RULE_SPEC = {
    'adx':{'threshold':25,'trigger':'DI difference crosses zero'},
    'rsi':{'reentry':[30,70]}, 'rsi2':{'reentry':[10,90]},
    'stochastic':{'reentry':[20,80]}, 'williams':{'reentry':[-80,-20]}, 'cci':{'reentry':[-100,100]},
    'divergence':{'lag':10,'rsi_buy_below':40,'rsi_sell_above':60,'type':'opposed endpoint changes, not confirmed pivots'},
    'atr_breakout':{'prior_20_bar_width_max_atr':4}, 'fib':{'fraction':'0.618','trend_ema':50},
    'fvg':{'span':3,'type':'current low > high two bars ago or current high < low two bars ago'},
}


def mean(values):
    return sum(values, ZERO) / len(values)


@dataclass(frozen=True)
class Frame:
    bar: Candle
    count: int
    features: Mapping[str, D]
    previous: Mapping[str, D]
    context: Candle | None = None


class Features:
    """Decimal streaming indicators; all initializations are part of v1 identity."""
    def __init__(self):
        self.bars = []
        self.values = {}
        self.emas = {}
        self.trs = []
        self.gains = []
        self.losses = []
        self.dx = []
        self.plus = []
        self.minus = []
        self.rsi_history = []

    def push(self, bar, context=None):
        if self.bars and (bar.opened < self.bars[-1].closed or
                (bar.instrument, bar.provider, bar.timeframe) !=
                (self.bars[-1].instrument, self.bars[-1].provider, self.bars[-1].timeframe)):
            raise ValueError('Chronological single-series input required')
        if context is not None and (context.closed > bar.closed or context.timeframe != '4H'
                or bar.timeframe != '1H' or context.instrument != bar.instrument or context.provider != bar.provider):
            raise ValueError('Only same-series CLOSED 4H context is permitted')
        previous = self.values
        with localcontext() as ctx:
            ctx.prec = 40
            v = self._calculate(bar)
        self.values = v
        return Frame(bar, len(self.bars), MappingProxyType(v.copy()),
                     MappingProxyType(previous.copy()), context)

    def _calculate(self, b):
        old = self.bars[-1] if self.bars else None
        prior = self.bars[-20:]
        self.bars.append(b)
        closes = [x.close for x in self.bars]
        v = {'close': b.close, 'high': b.high, 'low': b.low}
        tr = max(b.high-b.low, abs(b.high-old.close), abs(b.low-old.close)) if old else b.high-b.low
        self.trs.append(tr)
        self.gains.append(max(ZERO, b.close-old.close) if old else ZERO)
        self.losses.append(max(ZERO, old.close-b.close) if old else ZERO)
        up, down = (b.high-old.high, old.low-b.low) if old else (ZERO, ZERO)
        self.plus.append(up if up > down and up > 0 else ZERO)
        self.minus.append(down if down > up and down > 0 else ZERO)
        for n in (9, 12, 20, 21, 26, 50, 200):
            if len(closes) == n:
                self.emas[n] = mean(closes)
            elif len(closes) > n:
                self.emas[n] += D(2)/D(n+1)*(b.close-self.emas[n])
            if n in self.emas:
                v['ema'+str(n)] = self.emas[n]
        if 'ema26' in v:
            macd = v['ema12']-v['ema26']
            self.emas.setdefault('macds', []).append(macd)
            history = self.emas['macds']
            if len(history) == 9:
                self.emas['signal'] = mean(history)
            elif len(history) > 9:
                self.emas['signal'] += D('0.2')*(macd-self.emas['signal'])
            if 'signal' in self.emas:
                v.update(macd=macd, macd_signal=self.emas['signal'])
        for n in (2, 14):
            if len(closes) >= n+1:
                key = 'gain'+str(n)
                if key not in self.emas:
                    self.emas[key] = mean(self.gains[-n:])
                    self.emas['loss'+str(n)] = mean(self.losses[-n:])
                else:
                    self.emas[key] = (self.emas[key]*(n-1)+self.gains[-1])/n
                    self.emas['loss'+str(n)] = (self.emas['loss'+str(n)]*(n-1)+self.losses[-1])/n
                gain, loss = self.emas[key], self.emas['loss'+str(n)]
                v['rsi'+str(n)] = D(50) if gain == loss == 0 else (D(100) if loss == 0 else D(100)-100/(1+gain/loss))
        if len(closes) >= 14:
            self.emas['atr'] = mean(self.trs[-14:]) if len(closes) == 14 else (self.emas['atr']*13+tr)/14
            v['atr'] = self.emas['atr']
            den = sum(self.trs[-14:])
            p = sum(self.plus[-14:])/den if den else ZERO
            m = sum(self.minus[-14:])/den if den else ZERO
            self.dx.append(100*abs(p-m)/(p+m) if p+m else ZERO)
            if len(self.dx) >= 14:
                v.update(adx=mean(self.dx[-14:]), di_difference=p-m)
            block = self.bars[-14:]
            hi, lo = max(x.high for x in block), min(x.low for x in block)
            v['stochastic'] = 100*(b.close-lo)/(hi-lo) if hi != lo else D(50)
            v['williams'] = v['stochastic']-100
            middle = (b.high+b.low)/2
            upper, lower = middle+3*v['atr'], middle-3*v['atr']
            if 'st_upper' in self.values:
                upper = upper if upper < self.values['st_upper'] or old.close > self.values['st_upper'] else self.values['st_upper']
                lower = lower if lower > self.values['st_lower'] or old.close < self.values['st_lower'] else self.values['st_lower']
                direction = (D(1) if b.close > upper else D(-1)) if self.values['st_direction'] < 0 else (D(-1) if b.close < lower else D(1))
            else:
                direction = D(1)
            v.update(st_upper=upper, st_lower=lower, st_direction=direction)
        if len(closes) >= 20:
            avg = mean(closes[-20:])
            std = mean([(x-avg)**2 for x in closes[-20:]]).sqrt()
            typical = [(x.high+x.low+x.close)/3 for x in self.bars[-20:]]
            tp = mean(typical)
            deviation = mean([abs(x-tp) for x in typical])
            v.update(bb_lower=avg-2*std, bb_upper=avg+2*std,
                     cci=(typical[-1]-tp)/(D('.015')*deviation) if deviation else ZERO)
        if len(prior) == 20:
            v.update(prior_high=max(x.high for x in prior), prior_low=min(x.low for x in prior),
                     consolidation_width=max(x.high for x in prior)-min(x.low for x in prior))
        if len(self.bars) >= 41:
            recent, earlier = self.bars[-21:-1], self.bars[-41:-21]
            v.update(recent_high=max(x.high for x in recent), recent_low=min(x.low for x in recent),
                     earlier_high=max(x.high for x in earlier), earlier_low=min(x.low for x in earlier))
        # UTC dates/weeks and fixed research windows, never official broker sessions.
        day = b.opened.date()
        week = b.opened.isocalendar()[:2]
        for label, predicate in (
            ('day', lambda x: x.opened.date() < day),
            ('week', lambda x: x.opened.isocalendar()[:2] < week),
        ):
            candidates = [x for x in self.bars[:-1] if predicate(x)]
            if candidates:
                last = candidates[-1]
                group = [x for x in candidates if (x.opened.date() == last.opened.date() if label == 'day'
                          else x.opened.isocalendar()[:2] == last.opened.isocalendar()[:2])]
                # Require a full period after the first observed date/week, not a truncated warm-up day.
                complete = last.opened.date() > self.bars[0].opened.date() if label == 'day' else last.opened.isocalendar()[:2] > self.bars[0].opened.isocalendar()[:2]
                if complete:
                    v[label+'_high'], v[label+'_low'] = max(x.high for x in group), min(x.low for x in group)
        for label, start, end in (('london', 6, 8), ('ny', 11, 13)):
            window = [x for x in self.bars if x.opened.date() == day and start <= x.opened.hour < end]
            if b.timeframe == '1H' and len(window) == end-start and b.opened.hour >= end:
                v[label+'_high'], v[label+'_low'] = max(x.high for x in window), min(x.low for x in window)
        if len(self.bars) >= 3:
            a = self.bars[-3]
            v.update(fvg_buy=b.low-a.high, fvg_sell=a.low-b.high)
        if 'rsi14' in v and len(self.rsi_history) >= 10:
            v.update(div_price=closes[-1]-closes[-11], div_rsi=v['rsi14']-self.rsi_history[-10])
        if 'rsi14' in v:
            self.rsi_history.append(v['rsi14'])
        return v


def cross(v, p, a, b):
    if any(k not in q for q in (v, p) for k in (a, b)):
        return None
    return 'BUY' if p[a] <= p[b] and v[a] > v[b] else ('SELL' if p[a] >= p[b] and v[a] < v[b] else None)


def extremes(v, p, key, low, high):
    if key not in v or key not in p:
        return None
    return 'BUY' if p[key] < low <= v[key] else ('SELL' if p[key] > high >= v[key] else None)


def breakout(v, p, upper, lower):
    if any(k not in v for k in (upper, lower)) or 'close' not in p:
        return None
    return 'BUY' if p['close'] <= v[upper] < v['close'] else ('SELL' if p['close'] >= v[lower] > v['close'] else None)


@dataclass(frozen=True)
class BaseStrategy:
    strategy_id: str
    name: str
    family: str
    rule: str
    warmup: int
    eligibility: str = 'TOURNAMENT_READY'
    timeframes: tuple = ('1H', '4H')
    version: str = VERSION
    instruments: tuple = ('XAUUSD', 'XAGUSD', 'USOIL')
    parameters: tuple = (('atr_period', '14'), ('stop_atr', '2'), ('reward_r', '2'))

    def __post_init__(self):
        p = dict(self.parameters)
        if len(p) != len(self.parameters) or set(p) != {'atr_period','stop_atr','reward_r'} or p['atr_period'] != '14':
            raise ValueError('Unsupported parameter; fixed indicator changes require a new implementation version')
        for key in ('stop_atr','reward_r'):
            value = D(p[key])
            if not value.is_finite() or value <= 0 or key == 'reward_r' and value < D('1.5'):
                raise ValueError('Invalid intentional stop/reward parameter')
        if not self.strategy_id or not self.version: raise ValueError('Strategy identity required')

    def direction(self, frame):
        if frame.count < self.warmup or frame.bar.timeframe not in self.timeframes or frame.bar.instrument not in self.instruments:
            return None
        if self.eligibility not in {'TOURNAMENT_READY', 'EXPERIMENTAL'}:
            return None
        return self.evaluate(frame.features, frame.previous, frame.bar.opened.hour)

    def evaluate(self, v, p, hour):
        r = self.rule
        if r.startswith('ema_cross_'):
            a, b = r.removeprefix('ema_cross_').split('_')
            return cross(v, p, 'ema'+a, 'ema'+b)
        if r == 'macd': return cross(v, p, 'macd', 'macd_signal')
        if r == 'supertrend': return extremes(v, p, 'st_direction', 0, 0)
        if r == 'adx':
            if v.get('adx', ZERO) < 25: return None
            return extremes(v, p, 'di_difference', 0, 0)
        if r == 'donchian': return breakout(v, p, 'prior_high', 'prior_low')
        if r == 'ema_pullback': return cross(v, p, 'close', 'ema200')
        if r == 'rsi': return extremes(v, p, 'rsi14', 30, 70)
        if r == 'rsi2': return extremes(v, p, 'rsi2', 10, 90)
        if r == 'stochastic': return extremes(v, p, 'stochastic', 20, 80)
        if r == 'williams': return extremes(v, p, 'williams', -80, -20)
        if r == 'cci': return extremes(v, p, 'cci', -100, 100)
        if r == 'divergence':
            if not {'div_price', 'div_rsi', 'rsi14'} <= v.keys(): return None
            return 'BUY' if v['div_price'] < 0 < v['div_rsi'] and v['rsi14'] < 40 else ('SELL' if v['div_price'] > 0 > v['div_rsi'] and v['rsi14'] > 60 else None)
        if r in {'bb_reentry', 'bb_touch'}:
            if not {'bb_lower','bb_upper'} <= v.keys(): return None
            if r == 'bb_touch':
                buy, sell = v['low'] <= v['bb_lower'], v['high'] >= v['bb_upper']
            else:
                if not {'bb_lower','bb_upper'} <= p.keys(): return None
                buy = p['close'] < p['bb_lower'] and v['close'] >= v['bb_lower']
                sell = p['close'] > p['bb_upper'] and v['close'] <= v['bb_upper']
            return None if buy == sell else ('BUY' if buy else 'SELL')
        if r in {'day', 'week', 'london', 'ny'}:
            if r in {'london','ny'} and not ((8 <= hour < 11) if r == 'london' else (13 <= hour < 16)): return None
            return breakout(v, p, r+'_high', r+'_low')
        if r == 'atr_breakout':
            if v.get('consolidation_width', D('Infinity')) > 4*v.get('atr', ZERO): return None
            return breakout(v, p, 'prior_high', 'prior_low')
        if r == 'flip':
            if not {'prior_high','prior_low'} <= p.keys(): return None
            return 'BUY' if p['close'] > p['prior_high'] and v['low'] <= p['prior_high'] < v['close'] else ('SELL' if p['close'] < p['prior_low'] and v['high'] >= p['prior_low'] > v['close'] else None)
        if r == 'hhhl':
            if not {'recent_high','recent_low','earlier_high','earlier_low'} <= v.keys(): return None
            side = breakout(v, p, 'recent_high', 'recent_low')
            return side if (side == 'BUY' and v['recent_low'] > v['earlier_low'] and v['recent_high'] > v['earlier_high']) or (side == 'SELL' and v['recent_high'] < v['earlier_high'] and v['recent_low'] < v['earlier_low']) else None
        if r == 'sweep':
            if not {'prior_high','prior_low'} <= v.keys(): return None
            buy, sell = v['low'] < v['prior_low'] < v['close'], v['high'] > v['prior_high'] > v['close']
            return None if buy == sell else ('BUY' if buy else 'SELL')
        if r == 'fvg':
            return 'BUY' if v.get('fvg_buy', ZERO) > 0 else ('SELL' if v.get('fvg_sell', ZERO) > 0 else None)
        if r == 'fib':
            if not {'prior_high','prior_low','ema50'} <= v.keys(): return None
            width = v['prior_high']-v['prior_low']
            buy = v['prior_high']-D('.618')*width
            sell = v['prior_low']+D('.618')*width
            return 'BUY' if v['low'] <= buy < v['close'] and v['close'] > v['ema50'] else ('SELL' if v['high'] >= sell > v['close'] and v['close'] < v['ema50'] else None)
        return None


def catalogue():
    groups = (
        ('TREND', [('EMA 9/21','ema_cross_9_21',22),('EMA 20/50','ema_cross_20_50',51),
                   ('EMA 50/200','ema_cross_50_200',201),('MACD crossover','macd',35),
                   ('Supertrend','supertrend',15),('Rolling-ADX trend research variant','adx',28),
                   ('Donchian breakout','donchian',22),('EMA 200 pullback','ema_pullback',201)]),
        ('MEAN_REVERSION', [('RSI 30/70','rsi',16),('RSI divergence','divergence',26),
                            ('Bollinger re-entry','bb_reentry',21),('Stochastic extremes','stochastic',15),
                            ('Williams %R','williams',15),('RSI(2)','rsi2',15),
                            ('Bollinger outer touch','bb_touch',20),('CCI re-entry','cci',21)]),
        ('BREAKOUT', [('Previous-day breakout','day',49),('ATR consolidation','atr_breakout',22),
                     ('London UTC research breakout','london',24),('NY UTC research breakout','ny',24),
                     ('Previous-week breakout','week',241),('Support/resistance flip','flip',22),
                     ('Volume-spike breakout','volume',20)]),
        ('STRUCTURE', [('HH/HL continuation','hhhl',41),('Liquidity sweep','sweep',21),
                      ('Three-candle FVG','fvg',15),('Order block','undefined',1),
                      ('Rolling-range Fibonacci','fib',50),('Double top/bottom','undefined',1),
                      ('Head-and-shoulders','undefined',1)]),
    )
    out = []
    for family, rows in groups:
        for name, rule, warmup in rows:
            state = 'INSUFFICIENT_DEFINITION' if rule == 'undefined' else ('DISABLED_VOLUME_SEMANTICS' if rule == 'volume' else
                    ('EXPERIMENTAL' if rule in {'divergence','flip','hhhl','sweep','fvg','fib'} else 'TOURNAMENT_READY'))
            out.append(BaseStrategy(f'p6-{len(out)+1:02}', name, family, rule, warmup, state,
                                    ('1H',) if rule in {'london','ny'} else ('1H','4H')))
    return tuple(out)
