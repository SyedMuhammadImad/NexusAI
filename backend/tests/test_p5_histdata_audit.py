"""Synthetic parser/retention regressions, not qualification market evidence."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
import zipfile

import pytest

from core.rebuild.histdata_audit import inventory
from core.rebuild.histdata_provider import HistDataProvider
from core.rebuild.market_data import resample
from core.rebuild.research_data import ResearchData
from test_p5_market_data import START, bar, store
from test_p5_qualification import source


def archive(lines):
    output=BytesIO()
    with zipfile.ZipFile(output,'w') as z:
        z.writestr('DAT_ASCII_XAUUSD_M1_2021.csv','\n'.join(lines))
    return output.getvalue()


def test_month_inventory_does_not_trust_annual_filename():
    raw=archive([f'2021{m:02d}01 120000;100;102;99;101;0' for m in range(1,13)])
    audit,bars,issues=inventory(raw,'XAUUSD',2021)
    assert len(bars)==audit['raw_rows']==12 and not issues
    assert all(m['raw_rows']==m['accepted_rows']==1 for m in audit['months'].values())
    short,_,_=inventory(archive(['20210101 120000;100;102;99;101;0']),'XAUUSD',2021)
    assert sum(m['raw_rows']==0 for m in short['months'].values())==11
    assert inventory(raw,'XAUUSD',2021)[0]==audit


@pytest.mark.parametrize('date',['20210313','20210314','20210315','20211106','20211107','20211108'])
def test_fixed_est_even_at_dst_transition(date):
    bars,issues=HistDataProvider().normalize(archive([f'{date} 020000;100;102;99;101;0']),'XAUUSD',2021,None)
    assert not issues
    assert bars[0].opened==datetime.strptime(date+' 070000','%Y%m%d %H%M%S').replace(tzinfo=timezone.utc)
    assert bars[0].source_time==date+' 020000'
    assert bars[0].timezone_evidence=='EST_FIXED_UTC_MINUS_05_NO_DST'


def test_rejection_accounting():
    raw=archive(['20210101 120000;100;102;99;101;0',
                 '20210101 120100;NaN;102;99;101;0',
                 '20210101 120200;100;98;99;101;0',
                 '20210101 120301;100;102;99;101;0',
                 '20210101 120400;bad'])
    audit,_,_=inventory(raw,'XAUUSD',2021)
    assert audit['accepted_rows']==1 and audit['rejected_rows']==4
    assert audit['months']['202101']['reasons']==dict(non_finite=1,malformed_OHLC=1,timestamp_issue=1,parse_failure=1)


def test_gap_does_not_remove_valid_neighbor(store):
    bars=[bar(0),bar(2,open='110',high='112',low='109',close='111')]
    identity=store.save('XAUUSD','1M',START,START+timedelta(minutes=3),bars,raw=b'fixture',provenance=source())
    view=ResearchData(store); q=view.qualify(identity)
    result=view.query(q['qualification_id'],allow_segments=True)
    assert result['candles']==[b.payload() for b in bars]
    assert q['excluded_count']==0 and len(result['segments'])==2
    with pytest.raises(ValueError): view.query(q['qualification_id'])


def test_month_boundary_utc_resampling_no_invented_bars():
    start=datetime(2021,1,31,20,tzinfo=timezone.utc)
    bars=[bar(opened=start+timedelta(minutes=i),closed=start+timedelta(minutes=i+1)) for i in range(480)]
    result,issues=resample(bars,'4H')
    assert not issues and len(result)==2
    assert result[1].opened==datetime(2021,2,1,tzinfo=timezone.utc)
    partial,warnings=resample(bars[:-1],'4H')
    assert len(partial)==1 and len(warnings)==1
