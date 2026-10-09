CREATE TABLE p3_observations (
 observation_id TEXT PRIMARY KEY,
 account_key TEXT NOT NULL,
 broker_entity_type TEXT NOT NULL,
 broker_entity_id TEXT NOT NULL,
 observed_version INTEGER,
 supersedes_observation_id TEXT,
 observed_at TEXT NOT NULL,
 broker_reported_at TEXT,
 normalizer_version TEXT NOT NULL,
 raw_reference TEXT NOT NULL,
 payload TEXT NOT NULL
);
CREATE INDEX p3_observation_entity ON p3_observations(account_key,broker_entity_type,broker_entity_id);
CREATE TRIGGER p3_observation_no_update BEFORE UPDATE ON p3_observations BEGIN SELECT RAISE(ABORT,'Immutable broker observation'); END;
CREATE TRIGGER p3_observation_no_delete BEFORE DELETE ON p3_observations BEGIN SELECT RAISE(ABORT,'Immutable broker observation'); END;
CREATE TABLE p3_native_evidence (
 evidence_id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TRIGGER p3_native_no_update BEFORE UPDATE ON p3_native_evidence BEGIN SELECT RAISE(ABORT,'Immutable native evidence'); END;
CREATE TRIGGER p3_native_no_delete BEFORE DELETE ON p3_native_evidence BEGIN SELECT RAISE(ABORT,'Immutable native evidence'); END;
CREATE TABLE p3_observation_heads (
 account_key TEXT NOT NULL, broker_entity_type TEXT NOT NULL, broker_entity_id TEXT NOT NULL,
 observation_id TEXT REFERENCES p3_observations(observation_id), state TEXT NOT NULL,
 PRIMARY KEY(account_key,broker_entity_type,broker_entity_id)
);
CREATE TABLE p3_observation_links (
 observation_id TEXT PRIMARY KEY REFERENCES p3_observations(observation_id),
 attempt_id TEXT NOT NULL REFERENCES p3_attempts(attempt_id)
);
CREATE TRIGGER p3_link_no_update BEFORE UPDATE ON p3_observation_links BEGIN SELECT RAISE(ABORT,'Immutable observation lineage'); END;
CREATE TRIGGER p3_link_no_delete BEFORE DELETE ON p3_observation_links BEGIN SELECT RAISE(ABORT,'Immutable observation lineage'); END;
INSERT INTO schema_migrations VALUES(7,CURRENT_TIMESTAMP);
