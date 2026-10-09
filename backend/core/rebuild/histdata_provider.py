"""Public HistData ASCII/M1 adapter. No broker or credential dependencies."""
import csv
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from io import BytesIO, StringIO
import zipfile

import httpx

from .market_data import Candle, INTERVALS, MAPPINGS, UTC, resample, series, utc


class DownloadForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'input' and a.get('name') in {'tk', 'date', 'datemonth', 'platform', 'timeframe', 'fxpair'}:
            self.fields[a['name']] = a.get('value', '')


class HistDataProvider:
    name = 'HISTDATA'
    version = 'histdata-ascii-m1-v1'

    def download(self, instrument, year, month):
        if instrument not in MAPPINGS or not 2000 <= year <= datetime.now(UTC).year or not 1 <= month <= 12:
            raise ValueError('Unsupported bounded request')
        symbol = MAPPINGS[instrument]['provider_symbol']
        url = f'https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{symbol.lower()}/{year}/{month}'
        with httpx.Client(timeout=40, trust_env=False, follow_redirects=False) as client:
            response = client.get(url)
            response.raise_for_status()
            form = DownloadForm()
            form.feed(response.text)
            required = dict(date=str(year), datemonth=f'{year}{month:02d}', platform='ASCII', timeframe='M1', fxpair=symbol)
            if not form.fields.get('tk'):
                url = url.rsplit('/', 1)[0]
                response = client.get(url)
                response.raise_for_status()
                form = DownloadForm()
                form.feed(response.text)
                required['datemonth'] = str(year)
            if any(form.fields.get(k) != v for k, v in required.items()) or not form.fields.get('tk'):
                raise ValueError('Provider form identity mismatch')
            with client.stream('POST', 'https://www.histdata.com/get.php', data=form.fields, headers={'Referer': url}) as result:
                result.raise_for_status()
                chunks, size = [], 0
                for chunk in result.iter_bytes():
                    size += len(chunk)
                    if size > 32_000_000: raise ValueError('Oversized provider response')
                    chunks.append(chunk)
                raw = b''.join(chunks)
        return raw, dict(provider=self.name, adapter=self.version, url=url,
                         period=required['datemonth'], price_side='BID', volume='NOT_SUPPLIED',
                         timezone='EST_FIXED_UTC_MINUS_05_NO_DST', fixture=False)

    def normalize(self, raw, instrument, year, month):
        symbol = MAPPINGS[instrument]['provider_symbol']
        annual = f'DAT_ASCII_{symbol}_M1_{year}.csv'
        expected = f'DAT_ASCII_{symbol}_M1_{year}{month:02d}.csv' if month is not None else annual
        candles, issues = [], []
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            if sum(i.file_size for i in entries) > 64_000_000 or len(entries) > 10:
                raise ValueError('Oversized archive')
            files = [e for e in entries if e.filename in {expected, annual}]
            if len(files) != 1 or any(e.filename.lower().endswith('.csv') and e.filename not in {expected, annual} for e in entries):
                raise ValueError('Provider symbol/month archive mismatch')
            content = archive.read(files[0]).decode('ascii')
        for index, row in enumerate(csv.reader(StringIO(content), delimiter=';'), 1):
            try:
                if len(row) != 6: raise ValueError('Malformed fields')
                stamp = datetime.strptime(row[0], '%Y%m%d %H%M%S')
                if stamp.year != year or files[0].filename != annual and stamp.month != month:
                    raise ValueError('Period mismatch')
                if month is not None and stamp.month != month:
                    continue  # Annual source retained intact; this normalization is month-scoped.
                # Provider explicitly omits volume; zero is a placeholder, not measured zero volume.
                if row[5] != '0': raise ValueError('Unexpected volume representation')
                opened = stamp.replace(tzinfo=timezone(timedelta(hours=-5))).astimezone(UTC)
                candles.append(Candle(instrument=instrument, provider_symbol=symbol, timeframe='1M',
                    opened=opened, closed=opened+timedelta(minutes=1), open=row[1], high=row[2], low=row[3], close=row[4],
                    source_time=row[0], timezone_evidence='EST_FIXED_UTC_MINUS_05_NO_DST'))
            except (ValueError, OverflowError):
                issues.append({'kind': 'MALFORMED_NATIVE_ROW', 'row': index})
        return candles, issues


def sync(store, provider, instrument, timeframe, start, end, *, parent=None):
    """Re-fetch bounded months, then atomically publish a complete version or nothing.

    Incremental use extends the explicit start/end range and supplies the prior ID.
    Overlaps are re-read so corrections become a new immutable dataset, not updates.
    """
    start, end = utc(start), utc(end)
    if instrument not in MAPPINGS or timeframe not in INTERVALS or end <= start:
        raise ValueError('Invalid sync range')
    if end > datetime.now(UTC): raise ValueError('Unfinished/future range')
    if (end-start).days > 62: raise ValueError('Sync at most 62 days per dataset')
    if start.timestamp() % INTERVALS[timeframe] or end.timestamp() % INTERVALS[timeframe]:
        raise ValueError('Aligned range required')
    # M1 provider timestamps use fixed EST. Include every native month intersecting UTC range.
    local = start.astimezone(timezone(timedelta(hours=-5)))
    last = (end-timedelta(microseconds=1)).astimezone(timezone(timedelta(hours=-5)))
    year, month = local.year, local.month
    raw_parts, provenance, candles, issues = [], [], [], []
    while (year, month) <= (last.year, last.month):
        raw, p = provider.download(instrument, year, month)
        data, problems = provider.normalize(raw, instrument, year, month)
        raw_parts.append(raw)
        provenance.append(p)
        candles.extend(c for c in data if start <= c.opened < end)
        issues.extend(dict(problem, native_month=f'{year}-{month:02d}') for problem in problems)
        year, month = (year+1, 1) if month == 12 else (year, month+1)
    ordered, checks, gaps = series(candles, start, end, '1M')
    issues.extend(checks)
    if gaps: issues.append({'kind': 'SOURCE_GAPS', 'gaps': gaps})
    if timeframe != '1M':
        ordered, incomplete = resample(ordered, timeframe)
        issues.extend(incomplete)
    # Length framing preserves each exact downloaded byte sequence, without ZIP extraction.
    raw_bundle = b''.join(len(raw).to_bytes(8, 'big')+raw for raw in raw_parts)
    return store.save(instrument, timeframe, start, end, ordered, raw=raw_bundle,
                      provenance={'responses': provenance, 'fixture': any(p.get('fixture', True) for p in provenance)},
                      issues=issues, parent=parent)
