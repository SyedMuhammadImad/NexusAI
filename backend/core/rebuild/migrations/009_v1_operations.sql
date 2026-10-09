CREATE TABLE v1_control_events (
 revision INTEGER PRIMARY KEY,
 command_id TEXT NOT NULL UNIQUE,
 observed_at TEXT NOT NULL,
 payload TEXT NOT NULL,
 payload_hash TEXT NOT NULL
);
CREATE TRIGGER v1_control_no_update BEFORE UPDATE ON v1_control_events BEGIN SELECT RAISE(ABORT,'Immutable control audit'); END;
CREATE TRIGGER v1_control_no_delete BEFORE DELETE ON v1_control_events BEGIN SELECT RAISE(ABORT,'Immutable control audit'); END;
CREATE TABLE v1_deployments (
 deployment_id TEXT PRIMARY KEY,
 strategy_id TEXT NOT NULL,
 strategy_version TEXT NOT NULL,
 instrument TEXT NOT NULL,
 timeframe TEXT NOT NULL CHECK(timeframe IN ('1H','4H')),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 mode TEXT NOT NULL CHECK(mode='DEMO_ONLY'),
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(strategy_id,strategy_version,instrument,timeframe)
);
CREATE TABLE v1_deployment_events (
 event_id TEXT PRIMARY KEY,
 deployment_id TEXT NOT NULL REFERENCES v1_deployments(deployment_id),
 observed_at TEXT NOT NULL,
 payload TEXT NOT NULL
);
CREATE TRIGGER v1_deployment_event_no_update BEFORE UPDATE ON v1_deployment_events BEGIN SELECT RAISE(ABORT,'Immutable deployment audit'); END;
CREATE TRIGGER v1_deployment_event_no_delete BEFORE DELETE ON v1_deployment_events BEGIN SELECT RAISE(ABORT,'Immutable deployment audit'); END;
CREATE TABLE v1_ingress (
 ingress_id TEXT PRIMARY KEY,
 input_hash TEXT NOT NULL,
 source_type TEXT NOT NULL,
 source_id TEXT NOT NULL,
 received_at TEXT NOT NULL,
 status TEXT NOT NULL,
 payload TEXT NOT NULL
);
CREATE TABLE v1_monitor_samples (
 sample_id TEXT PRIMARY KEY,
 component TEXT NOT NULL,
 observed_at TEXT NOT NULL,
 valid_until TEXT NOT NULL,
 state TEXT NOT NULL,
 payload TEXT NOT NULL,
 payload_hash TEXT NOT NULL
);
CREATE INDEX v1_monitor_time ON v1_monitor_samples(component,observed_at);
CREATE TRIGGER v1_sample_no_update BEFORE UPDATE ON v1_monitor_samples BEGIN SELECT RAISE(ABORT,'Immutable monitoring evidence'); END;
CREATE TRIGGER v1_sample_no_delete BEFORE DELETE ON v1_monitor_samples BEGIN SELECT RAISE(ABORT,'Immutable monitoring evidence'); END;
CREATE TABLE v1_alerts (
 alert_id TEXT PRIMARY KEY,
 kind TEXT NOT NULL,
 severity TEXT NOT NULL CHECK(severity IN ('INFO','WARNING','CRITICAL')),
 source TEXT NOT NULL,
 related_id TEXT,
 observed_at TEXT NOT NULL,
 resolved_at TEXT
);
CREATE TABLE v1_alert_ack (
 command_id TEXT PRIMARY KEY,
 alert_id TEXT NOT NULL REFERENCES v1_alerts(alert_id),
 observed_at TEXT NOT NULL
);
CREATE TRIGGER v1_ack_no_update BEFORE UPDATE ON v1_alert_ack BEGIN SELECT RAISE(ABORT,'Immutable acknowledgment'); END;
CREATE TRIGGER v1_ack_no_delete BEFORE DELETE ON v1_alert_ack BEGIN SELECT RAISE(ABORT,'Immutable acknowledgment'); END;
INSERT INTO schema_migrations VALUES(9,CURRENT_TIMESTAMP);
