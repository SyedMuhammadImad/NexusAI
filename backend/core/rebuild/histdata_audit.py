"""Raw acquisition accounting, separate from canonical continuity qualification."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import csv
import hashlib
import zipfile

from .histdata_provider import HistDataProvider
from .market_data import MAPPINGS


def inventory(raw, instrument, year):
    candles, issues = HistDataProvider().normalize(raw, instrument, year, None)
    rejected = {i['row'] for i in issues}
    name = f'DAT_ASCII_{MAPPINGS[instrument]["provider_symbol"]}_M1_{year}.csv'
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        info = archive.getinfo(name)
        content = archive.read(info)
    months = {f'{year}{m:02d}': dict(raw_rows=0, accepted_rows=0, rejected_rows=0,
              row_bytes=0, first_source=None, last_source=None, reasons={}) for m in range(1,13)}
    unknown = 0
    for index, line in enumerate(content.splitlines(keepends=True), 1):
        row = next(csv.reader([line.decode('ascii').rstrip('\r\n')], delimiter=';'))
        key = row[0][:6] if row else ''
        if key not in months:
            unknown += 1
            continue
        item = months[key]; item['raw_rows'] += 1; item['row_bytes'] += len(line)
        reason = None
        if index in rejected:
            reason = 'other'
            try:
                if len(row)!=6:
                    reason='parse_failure'
                else:
                    stamp=datetime.strptime(row[0], '%Y%m%d %H%M%S')
                    if stamp.year!=year or stamp.second:
                        reason='timestamp_issue'
                    else:
                        values=[Decimal(v) for v in row[1:5]]
                        reason='non_finite' if not all(v.is_finite() for v in values) else 'malformed_OHLC'
                        if row[5]!='0': reason='other'
            except (ValueError, OverflowError):
                reason='timestamp_issue'
            except InvalidOperation:
                reason='parse_failure'
            item['rejected_rows'] += 1
            item['reasons'][reason]=item['reasons'].get(reason,0)+1
        else:
            item['accepted_rows'] += 1
            item['first_source']=min(item['first_source'] or row[0],row[0])
            item['last_source']=max(item['last_source'] or row[0],row[0])
    return dict(archive_sha256=hashlib.sha256(raw).hexdigest(),archive_bytes=len(raw),
                csv_name=name,csv_bytes=len(content),csv_compressed_bytes=info.compress_size,
                months=months,unassigned_month_rows=unknown,raw_rows=sum(x['raw_rows'] for x in months.values())+unknown,
                accepted_rows=len(candles),rejected_rows=len(issues)), candles, issues
