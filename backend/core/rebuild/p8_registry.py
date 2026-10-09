"""Append-only research registry in its own root. Never deserializes executable models."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from .market_data import digest, encode

ROOT=Path(__file__).resolve().parents[3]/'research/p8-intelligence'
STATUSES={'EXPERIMENTAL','INSUFFICIENT_DATA','RESEARCH_QUALIFIED','REJECTED','DISABLED','KRONOS_RUNTIME_BLOCKED'}


class Registry:
    def __init__(self,root=None,*,fixture=False):
        self.root=Path(root or ROOT).absolute()
        resolved=self.root.resolve(); temporary=Path(tempfile.gettempdir()).resolve()
        if (not fixture and resolved!=ROOT.resolve() or fixture and
            (resolved==temporary or not resolved.is_relative_to(temporary)) or
            any(p.lower() in {'private','.env','data','.p3-verification'} for p in self.root.parts)):
            raise ValueError('P8 research root boundary')
        if any(p.exists() and (p.is_symlink() or p.is_junction()) for p in [self.root,*self.root.parents]):
            raise ValueError('Linked research storage forbidden')
        self.root.mkdir(parents=True,exist_ok=True)
        marker=self.root/'.p8-research'
        if not marker.exists():
            if list(self.root.iterdir()): raise ValueError('Unowned research directory')
            marker.write_text('p8-registry-v1',encoding='ascii')
        if marker.is_symlink() or marker.read_text(encoding='ascii')!='p8-registry-v1':
            raise ValueError('Ownership marker mismatch')
        self.path=self.root/'registry.sqlite3'
        self._safe(self.path)
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY,payload TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS immutable_p8_update BEFORE UPDATE ON models BEGIN SELECT RAISE(ABORT,'Immutable research registry'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_p8_delete BEFORE DELETE ON models BEGIN SELECT RAISE(ABORT,'Immutable research registry'); END;''')

    def _safe(self,path):
        if path.exists() and (path.is_symlink() or path.is_junction() or path.stat().st_nlink!=1):
            raise ValueError('Linked research file forbidden')

    @contextmanager
    def connect(self):
        self._safe(self.path)
        c=sqlite3.connect(self.path,timeout=20)
        try:
            with c: yield c
        finally: c.close()

    def register(self,entry,artifact,*,checkpoint=lambda:None):
        if entry.get('status') not in STATUSES or entry.get('execution_eligible') is not False:
            raise ValueError('Research-only registry status required')
        required={'track','task','model_type','dataset_ids','schema_id','label_policy','train_range',
                  'validation_ranges','test_ranges','hyperparameters','seed','metrics'}
        if not required<=entry.keys(): raise ValueError('Incomplete model registry entry')
        body=encode(artifact).encode(); sha=hashlib.sha256(body).hexdigest()
        path=self.root/(sha+'.json')
        record=dict(entry,artifact_path=path.name,artifact_sha256=sha)
        identity=digest(record); text=encode(record)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            # Serialize publication across threads/processes before touching the artifact.
            self._safe(path)
            if path.exists():
                if path.read_bytes()!=body: raise ValueError('Artifact tampering')
            else:
                fd,temp=tempfile.mkstemp(prefix='.p8-artifact-',dir=self.root)
                temporary=Path(temp)
                try:
                    with os.fdopen(fd,'wb') as f:
                        f.write(body); f.flush(); os.fsync(f.fileno())
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
            old=c.execute('SELECT payload FROM models WHERE id=?',(identity,)).fetchone()
            if old and old[0]!=text: raise ValueError('Registry identity collision')
            checkpoint()
            c.execute('INSERT OR IGNORE INTO models VALUES(?,?,?)',
                      (identity,text,datetime.now(timezone.utc).isoformat()))
        return identity

    def read(self,identity):
        with self.connect() as c:
            row=c.execute('SELECT payload,created_at FROM models WHERE id=?',(identity,)).fetchone()
        if not row: raise ValueError('Unknown research model')
        value=json.loads(row[0])
        if digest(value)!=identity: raise ValueError('Registry identity mismatch')
        name=value['artifact_path']
        if not re.fullmatch('[a-f0-9]{64}\\.json',name): raise ValueError('Artifact path escape')
        path=self.root/name; self._safe(path); body=path.read_bytes()
        if hashlib.sha256(body).hexdigest()!=value['artifact_sha256']: raise ValueError('Artifact hash mismatch')
        return dict(model_id=identity,created_at=row[1],**value),json.loads(body)
