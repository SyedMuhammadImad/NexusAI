"""Provider-independent, version-pinned P5 research access. Never chooses latest."""
import json

from .export_research import ExportResearch
from .feed_calendar import FeedResearch


class ResearchDatasetReader:
    def __init__(self,store):
        self.store=store

    def query(self,qualification_id,*,start,end):
        with self.store.connect() as c:
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, reader in (('p5_export_qualification',ExportResearch),
                                  ('p5_feed_qualification',FeedResearch)):
                if table not in tables: continue
                row=c.execute(f'SELECT payload FROM {table} WHERE id=?',(qualification_id,)).fetchone()
                if row:
                    result=reader(self.store).query(qualification_id,start=start,end=end)
                    result['qualification']=json.loads(row[0])
                    return result
        raise ValueError('Unknown version-pinned research qualification')
