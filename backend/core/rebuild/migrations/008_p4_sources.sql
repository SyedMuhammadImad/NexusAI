CREATE TABLE p4_source_configuration (
 revision INTEGER PRIMARY KEY CHECK(revision > 0),
 payload TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TRIGGER p4_configuration_immutable_update BEFORE UPDATE ON p4_source_configuration
BEGIN SELECT RAISE(ABORT, 'Immutable source configuration'); END;
CREATE TRIGGER p4_configuration_immutable_delete BEFORE DELETE ON p4_source_configuration
BEGIN SELECT RAISE(ABORT, 'Persistent P4 broker block'); END;
CREATE TRIGGER p4_no_broker_attempt BEFORE INSERT ON p3_attempts
WHEN EXISTS(SELECT 1 FROM p4_source_configuration)
BEGIN SELECT RAISE(ABORT, 'P4_BROKER_HARD_DISABLED'); END;
INSERT INTO schema_migrations VALUES(8,CURRENT_TIMESTAMP);
