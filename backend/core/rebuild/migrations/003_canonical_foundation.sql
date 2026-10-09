CREATE TABLE source_events(
 source_event_id TEXT PRIMARY KEY,
 source_type TEXT NOT NULL CHECK(source_type IN ('WHATSAPP_HUMAN','MANUAL','NEXUSAI_STRATEGY','HISTORICAL_WHATSAPP','SCREENSHOT')),
 source_id TEXT NOT NULL, source_message_id TEXT NOT NULL,
 raw_source_hash TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('RECEIVED','TIME_UNRESOLVED')), created_at TEXT NOT NULL,
 UNIQUE(source_type,source_id,source_message_id)
);
CREATE TRIGGER source_no_update BEFORE UPDATE ON source_events BEGIN SELECT RAISE(ABORT,'Immutable source event'); END;
CREATE TRIGGER source_no_delete BEFORE DELETE ON source_events BEGIN SELECT RAISE(ABORT,'Immutable source event'); END;
ALTER TABLE signals ADD COLUMN source_event_id TEXT REFERENCES source_events(source_event_id);
CREATE UNIQUE INDEX signal_source_event ON signals(source_event_id) WHERE source_event_id IS NOT NULL;
CREATE TRIGGER signal_source_lineage BEFORE INSERT ON signals
 WHEN json_extract(NEW.payload,'$.contract_version')='signal.v2' AND NOT EXISTS(
 SELECT 1 FROM source_events e WHERE e.source_event_id=NEW.source_event_id
 AND e.source_event_id=json_extract(NEW.payload,'$.source_event_id')
 AND e.source_type=NEW.source_type AND e.source_id=NEW.source_id
 AND e.source_message_id=NEW.source_message_id
 AND e.raw_source_hash=json_extract(NEW.payload,'$.raw_source_hash'))
 BEGIN SELECT RAISE(ABORT,'Invalid source event lineage'); END;
ALTER TABLE risk_decisions ADD COLUMN explanation TEXT;
ALTER TABLE risk_decisions ADD COLUMN policy_id TEXT;
ALTER TABLE risk_decisions ADD COLUMN policy_version TEXT;
ALTER TABLE risk_decisions ADD COLUMN evidence_scope TEXT;
ALTER TABLE risk_decisions ADD COLUMN payload TEXT;
ALTER TABLE risk_decisions ADD COLUMN payload_hash TEXT;
CREATE TRIGGER risk_no_delete BEFORE DELETE ON risk_decisions BEGIN SELECT RAISE(ABORT,'Immutable risk decision'); END;
CREATE TABLE execution_requests(
 execution_request_id TEXT PRIMARY KEY,
 intent_id TEXT NOT NULL UNIQUE REFERENCES order_intents(intent_id),
 safety_decision_id TEXT NOT NULL REFERENCES risk_decisions(risk_decision_id),
 client_order_id TEXT NOT NULL UNIQUE REFERENCES order_intents(client_order_id),
 account_key TEXT NOT NULL REFERENCES account_binding(account_key),
 status TEXT NOT NULL CHECK(status='RECORDED_NOT_SUBMITTED'),
 evidence_scope TEXT NOT NULL CHECK(evidence_scope='FIXTURE'),
 payload_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER execution_approved_lineage BEFORE INSERT ON execution_requests
 WHEN NOT EXISTS(SELECT 1 FROM risk_decisions d JOIN order_intents i ON i.intent_id=d.intent_id
 JOIN signals s ON s.signal_id=i.signal_id JOIN account_binding a ON a.account_key=NEW.account_key
 WHERE d.risk_decision_id=NEW.safety_decision_id AND d.intent_id=NEW.intent_id
 AND i.client_order_id=NEW.client_order_id AND d.decision='APPROVED'
 AND d.evidence_scope='FIXTURE' AND d.policy_id='p1-fixture' AND d.policy_version='1'
 AND d.approved_volume=i.requested_volume
 AND json_extract(i.request,'$.contract_version')='intent.v2'
 AND NOT EXISTS(SELECT 1 FROM risk_decisions veto WHERE veto.intent_id=i.intent_id AND veto.decision='REJECTED')
 AND json_extract(a.payload,'$.evidence_source')='FIXTURE'
 AND json_extract(a.payload,'$.mode')='DEMO'
 AND s.source_type IN ('MANUAL','WHATSAPP_HUMAN') AND s.source_event_id IS NOT NULL)
 BEGIN SELECT RAISE(ABORT,'Execution request requires exact approved fixture lineage'); END;
CREATE TRIGGER execution_no_update BEFORE UPDATE ON execution_requests BEGIN SELECT RAISE(ABORT,'Immutable execution request'); END;
CREATE TRIGGER execution_no_delete BEFORE DELETE ON execution_requests BEGIN SELECT RAISE(ABORT,'Immutable execution request'); END;
INSERT INTO schema_migrations VALUES(3,CURRENT_TIMESTAMP);
