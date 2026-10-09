"""Historical human behavior audit; no invented UTC, no invented negative events."""
from collections import Counter
import hashlib
import io
import re
from datetime import datetime
from statistics import median
import zipfile

from services.signal_parser import SignalParser
from .market_data import digest

HEADER=re.compile(r'^\[?(\d{1,2}[/.]\d{1,2}[/.]\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\]?\s*(?:-\s*)?(.*)$',re.I)


def records(text):
    result=[]; orphan=0
    for line in text.splitlines():
        line=line.replace('\u200e','').replace('\u200f','').replace('\u202f',' ').replace('\xa0',' ')
        m=HEADER.match(line)
        if m:
            date,clock,rest=m.groups(); sender,sep,body=rest.partition(': ')
            result.append(dict(local_date=date,local_clock=clock,sender=sender if sep else 'SYSTEM',
                               body=body if sep else rest))
        elif result: result[-1]['body']+='\n'+line
        elif line.strip(): orphan+=1
    if not result: raise ValueError('No supported transcript records')
    return result,orphan


def summary(values):
    return dict(count=len(values),median=median(values) if values else None,
                minimum=min(values) if values else None,maximum=max(values) if values else None)


def local_clock(value):
    for fmt in ('%I:%M:%S %p','%I:%M %p','%H:%M:%S','%H:%M'):
        try: return datetime.strptime(value.strip().upper(),fmt).time()
        except ValueError: pass
    return None


def timestamp_audit(items):
    alternatives={'DMY':[],'MDY':[]}; two_digit_years=0; both=0
    for item in items:
        a,b,y=map(int,re.split('[/.]',item['local_date'])); clock=local_clock(item['local_clock'])
        two_digit_years+=int(y<100); y=y+2000 if y<100 else y; valid=[]
        for order,day,month in [('DMY',a,b),('MDY',b,a)]:
            try:
                if clock is None: continue
                value=datetime(y,month,day,clock.hour,clock.minute,clock.second)
                alternatives[order].append(value.isoformat()); valid.append(order)
            except ValueError: pass
        both+=int(len(valid)==2)
    return dict(orders={k:dict(valid_records=len(v),local_start=min(v) if v else None,
                               local_end=max(v) if v else None) for k,v in alternatives.items()},
        both_orders_valid_records=both,two_digit_year_records=two_digit_years,
        timezone='UNATTESTED; local time is NOT UTC',
        year_interpretation='2000+ for two digits is an audit convention, not an attested source mapping')


def audit_archive(body):
    if len(body)>100*1024*1024: raise ValueError('Oversized historical archive')
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        members=z.infolist()
        if any(m.flag_bits&1 for m in members): raise ValueError('Encrypted archive not supported')
        texts=[m for m in members if m.filename.lower().endswith('.txt')]
        if len(texts)!=1 or texts[0].file_size>5*1024*1024 or len(members)>20000:
            raise ValueError('Bounded single transcript required')
        with z.open(texts[0]) as f: raw=f.read(5*1024*1024+1)
        if len(raw)>5*1024*1024: raise ValueError('Oversized transcript')
        items,orphan=records(raw.decode('utf-8-sig'))
        media=sum(not m.is_dir() and not m.filename.lower().endswith('.txt') for m in members)
    seen=set(); signal_ids=set(); duplicates=0; duplicate_signals=0; candidates=0; usable=[]; ambiguous=0; reasons=Counter()
    fields=Counter(); reported=0; excluded_update=0
    for item in items:
        identity=digest(item)
        if identity in seen:
            duplicates+=1; duplicate_signals+=int(identity in signal_ids); continue
        seen.add(identity); text=item['body'].replace('*','')
        text=re.sub(r'<attached:[^>]+>','',text,flags=re.I)
        text=re.sub(r'(?<=\d),(?=\d{3}\b)','',text)
        for pattern,replacement in [(r'\bshortsell\b','SELL'),(r'\bcrude\s+oil\b','USOIL'),
                                    (r'\bcurrent\s+price\b','current rate')]:
            text=re.sub(pattern,replacement,text,flags=re.I)
        text=re.sub(r'\b(?:(?:on|at)\s+)?current\s+rate\b(?!\s*[:=@]?\s*[+-]?\d)',
                    'MARKET',text,flags=re.I)
        if re.search(r'\b(hit|booked|achieved|profitable)\b',text,re.I): reported+=1
        if re.search(r'\b(cancel|ignore|close|exit|update|move|trail)\b',text,re.I):
            excluded_update+=1; continue
        # Synthetic positive timestamps are exclusively parser shape-validation inputs.
        # They are never retained as market timestamps or used to train a model.
        parsed=SignalParser().parse(message_id=identity,group_id='historical-research',sender_id='redacted',
            text=text,message_timestamp=1.,received_timestamp=1.,p2=True)
        if parsed.instrument and parsed.direction in {'BUY','SELL'}:
            signal_ids.add(identity)
            candidates+=1
            fields.update(k for k,v in [('entry',parsed.entry_price),('sl',parsed.stop_loss),
                ('tp',parsed.primary_take_profit)] if v is not None)
            if any('AMBIGUOUS' in x or 'DUPLICATE' in x for x in parsed.rejection_reasons): ambiguous+=1
            reasons.update(parsed.rejection_reasons)
            if parsed.rejection_reasons: continue
            signal=dict(id=identity,instrument=parsed.instrument,direction=parsed.direction,
                entry=parsed.entry_price,stop=parsed.stop_loss,target=parsed.primary_take_profit,
                entry_type=parsed.entry_type,local_clock=item['local_clock'])
            if parsed.entry_price is not None:
                sl=abs(parsed.entry_price-parsed.stop_loss); tp=abs(parsed.primary_take_profit-parsed.entry_price)
                signal.update(stop_fraction=sl/parsed.entry_price,target_fraction=tp/parsed.entry_price,reward_r=tp/sl)
            usable.append(signal)
    return dict(track='HUMAN_IMITATION',status='INSUFFICIENT_DATA',result='HUMAN_IMITATION_PARTIAL',
        raw_messages=len(items),archive_sha256=hashlib.sha256(body).hexdigest(),
        transcript_sha256=hashlib.sha256(raw).hexdigest(),archive_media_count=media,orphan_lines=orphan,
        duplicate_messages=duplicates,signal_candidates=candidates,usable_signal_shapes=len(usable),
        duplicate_signal_events=duplicate_signals,timestamps=timestamp_audit(items),
        ambiguous_signals=ambiguous,excluded_updates=excluded_update,reported_result_messages=reported,
        rejection_reasons=dict(reasons),available_fields=dict(fields),
        instrument_counts=dict(Counter(s['instrument'] for s in usable)),
        direction_counts=dict(Counter(s['direction'] for s in usable)),
        local_hour_counts=dict(Counter(str(local_clock(s['local_clock']).hour) for s in usable if local_clock(s['local_clock']))),
        numeric_behavior={k:summary([s[k] for s in usable if k in s]) for k in ('stop_fraction','target_fraction','reward_r')},
        tasks=['conditional instrument/direction frequency','explicit stop/target fraction and R:R descriptive statistics'],
        model='DESCRIPTIVE_CONDITIONAL_BEHAVIOR; no supervised fit on this unqualified archive',
        timestamp_evidence='local date/clock retained in source; date order/UTC offset not attested',
        utc_qualified_signals=0,reconstructed_market_context=0,verified_outcomes=0,
        validation='Chronological predictive evaluation NOT_APPLICABLE without qualified UTC/context',
        negatives=0,no_signal_classifier=False,execution_eligible=False,
        blockers=['Unattested export timezone/date semantics; no qualified market-context join or verified economic outcomes'],
        limitations=['Images not OCR-reinterpreted','Text reports are not broker outcomes',
                      'Stop/target geometry is observed behavior, not a direction predictor',
                      'Usable means syntactic/geometry evidence only, not execution eligibility'])
