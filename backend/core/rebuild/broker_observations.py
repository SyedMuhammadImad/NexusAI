"""Append-only evidence and deterministic projections. Never submits or adopts trades."""
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

from .ledger import canonical, hashed


class BrokerObservation(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    observation_id: str = Field(min_length=1)
    account_key: str = Field(min_length=1)
    broker_entity_type: Literal['ORDER', 'DEAL', 'POSITION', 'ACCOUNT', 'SYMBOL', 'QUOTE', 'INVENTORY']
    broker_entity_id: str = Field(min_length=1)
    observed_version: StrictInt | None = Field(default=None, ge=0)
    supersedes_observation_id: str | None = None
    observed_at: AwareDatetime
    broker_reported_at: AwareDatetime | None = None
    ordering: Literal['SEQUENCE', 'BROKER_UPDATE', 'UNORDERED'] = 'UNORDERED'
    normalized_payload: dict
    raw_native: dict
    raw_reference: str
    normalizer_version: str = Field(min_length=1)
    error: str | None = None

    @model_validator(mode='after')
    def ordering_evidence(self):
        if self.ordering=='SEQUENCE' and self.observed_version is None:
            raise ValueError('Missing authoritative sequence')
        if self.ordering=='BROKER_UPDATE' and self.broker_reported_at is None:
            raise ValueError('Missing broker update timestamp')
        return self


def observation(account, kind, identity, payload, raw, observed_at, *, reported_at=None,
                version=None, supersedes=None, ordering='UNORDERED', error=None,
                normalizer='mt5-native-v1'):
    # Receipt time is deliberately excluded from identity: rereads are not fills.
    body = dict(account_key=account, broker_entity_type=kind, broker_entity_id=identity,
                observed_version=version, supersedes_observation_id=supersedes,
                broker_reported_at=reported_at.isoformat() if reported_at else None,
                ordering=ordering, normalized_payload=payload, raw_native=raw,
                raw_reference=hashed(raw), normalizer_version=normalizer, error=error)
    value = BrokerObservation(observation_id='pending', observed_at=observed_at, **body)
    return value.model_copy(update={'observation_id': hashed(value.model_dump(mode='json', exclude={'observation_id', 'observed_at'}))})


class ObservationJournal:
    def __init__(self, account_key):
        self.account_key = account_key

    def append(self, conn, values):
        touched = set()
        for value in values:
            o = BrokerObservation.model_validate(value)
            if o.account_key != self.account_key or o.raw_reference != hashed(o.raw_native):
                raise ValueError('Observation account/raw identity mismatch')
            expected = o.model_dump(mode='json', exclude={'observation_id', 'observed_at'})
            if hashed(expected) != o.observation_id:
                raise ValueError('Observation content identity mismatch')
            payload = canonical(o.model_dump(mode='json'))
            conn.execute('INSERT INTO p3_native_evidence VALUES(?,?) ON CONFLICT DO NOTHING',
                         (o.raw_reference, canonical(o.raw_native)))
            conn.execute('INSERT INTO p3_observations VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING',
                         (o.observation_id, o.account_key, o.broker_entity_type, o.broker_entity_id,
                          o.observed_version, o.supersedes_observation_id, o.observed_at.isoformat(),
                          o.broker_reported_at.isoformat() if o.broker_reported_at else None,
                          o.normalizer_version, o.raw_reference, payload))
            touched.add((o.broker_entity_type, o.broker_entity_id))
            known = conn.execute('SELECT DISTINCT l.attempt_id FROM p3_observation_links l JOIN p3_observations p ON p.observation_id=l.observation_id WHERE p.account_key=? AND p.broker_entity_type=? AND p.broker_entity_id=?',
                                 (self.account_key,o.broker_entity_type,o.broker_entity_id)).fetchall()
            if len(known)==1:
                conn.execute('INSERT INTO p3_observation_links VALUES(?,?) ON CONFLICT DO NOTHING', (o.observation_id,known[0][0]))
        # Resolve after the whole batch, so parent arrival order cannot matter.
        for kind, identity in sorted(touched):
            self.resolve(conn, kind, identity)

    def resolve(self, conn, kind, identity):
        values = [BrokerObservation.model_validate_json(r[0]) for r in conn.execute(
            'SELECT payload FROM p3_observations WHERE account_key=? AND broker_entity_type=? AND broker_entity_id=?',
            (self.account_key, kind, identity))]
        by_id = {o.observation_id: o for o in values}
        ambiguous = any(o.error for o in values)
        edges = {}
        for o in values:
            parent = o.supersedes_observation_id
            if parent:
                if parent not in by_id or parent == o.observation_id:
                    ambiguous = True
                else:
                    edges[o.observation_id] = parent
        for identity_ in edges:
            seen, node = set(), identity_
            while node in edges:
                if node in seen:
                    ambiguous = True
                    break
                seen.add(node)
                node = edges[node]
        def key(o):
            if o.ordering == 'SEQUENCE' and o.observed_version is not None:
                return ('SEQUENCE', o.observed_version)
            if o.ordering == 'BROKER_UPDATE' and o.broker_reported_at is not None:
                return ('BROKER_UPDATE', o.broker_reported_at.timestamp())
            return None
        # Normalized economic content, not receipt/evidence IDs, determines equality.
        def content(o):
            return canonical(o.normalized_payload)
        for child, parent in edges.items():
            child_key,parent_key = key(by_id[child]),key(by_id[parent])
            if child_key is not None and parent_key is not None and child_key[0]==parent_key[0] and child_key<=parent_key:
                ambiguous = True
        keys = [key(o) for o in values]
        if len({content(o) for o in values}) == 1:
            winner = max(values, key=lambda o: (key(o) or ('',0), o.observation_id))
        elif all(k is not None for k in keys) and len({k[0] for k in keys}) == 1:
            ranks = {}
            for o in values:
                rank = key(o)
                if rank in ranks and content(ranks[rank]) != content(o):
                    ambiguous = True
                ranks[rank] = o
            winner = max(values, key=lambda o: (key(o), o.observation_id))
        else:
            # Explicit supersession can order records without an API revision clock.
            tips = set(by_id) - set(edges.values())
            winner = by_id[next(iter(tips))] if len(tips) == 1 else values[0]
            visited, node = set(), winner.observation_id
            while node not in visited:
                visited.add(node)
                if node not in edges:
                    break
                node = edges[node]
            if visited != set(by_id):
                ambiguous = True
        state = 'AMBIGUOUS' if ambiguous else 'CURRENT'
        conn.execute('INSERT INTO p3_observation_heads VALUES(?,?,?,?,?) ON CONFLICT DO UPDATE SET observation_id=excluded.observation_id,state=excluded.state',
                     (self.account_key, kind, identity, None if ambiguous else winner.observation_id, state))
        return None if ambiguous else winner

    def current(self, conn, kind, identity):
        row = conn.execute('SELECT o.payload FROM p3_observation_heads h LEFT JOIN p3_observations o ON o.observation_id=h.observation_id WHERE h.account_key=? AND h.broker_entity_type=? AND h.broker_entity_id=? AND h.state=?',
                           (self.account_key, kind, identity, 'CURRENT')).fetchone()
        if not row or row[0] is None:
            raise ValueError('Ambiguous broker observation')
        return BrokerObservation.model_validate_json(row[0])

    def link(self, conn, kind, identity, attempt):
        for row in conn.execute('SELECT observation_id FROM p3_observations WHERE account_key=? AND broker_entity_type=? AND broker_entity_id=?',
                                (self.account_key, kind, identity)).fetchall():
            old = conn.execute('SELECT attempt_id FROM p3_observation_links WHERE observation_id=?', (row[0],)).fetchone()
            if old and old[0] != attempt:
                raise ValueError('Observation economic identity changed')
            conn.execute('INSERT INTO p3_observation_links VALUES(?,?) ON CONFLICT DO NOTHING', (row[0], attempt))
