CREATE TABLE historical_links(
 import_id TEXT NOT NULL, message_id TEXT NOT NULL,
 archive_hash TEXT, transcript_fingerprint TEXT, historical_message_id TEXT,
 candidate_source_event_id TEXT NOT NULL,
 source_event_id TEXT REFERENCES source_events(source_event_id),
 signal_id TEXT REFERENCES signals(signal_id),
 status TEXT NOT NULL CHECK(status IN ('PENDING','SOURCE_ONLY','VALIDATED','REVIEW_REQUIRED')),
 reason TEXT NOT NULL, review_snapshot TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(import_id,message_id),
 CHECK(status!='VALIDATED' OR (source_event_id IS NOT NULL AND signal_id IS NOT NULL)),
 CHECK(signal_id IS NULL OR source_event_id IS NOT NULL),
 CHECK(source_event_id IS NULL OR source_event_id=candidate_source_event_id)
);
CREATE INDEX historical_links_source ON historical_links(source_event_id);
CREATE TRIGGER historical_link_insert BEFORE INSERT ON historical_links
 WHEN (NEW.source_event_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM source_events WHERE source_event_id=NEW.source_event_id AND source_message_id=NEW.historical_message_id AND source_type IN ('HISTORICAL_WHATSAPP','SCREENSHOT')))
 OR (NEW.signal_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM signals WHERE signal_id=NEW.signal_id AND source_event_id=NEW.source_event_id))
 BEGIN SELECT RAISE(ABORT,'Invalid historical lineage'); END;
CREATE TRIGGER historical_link_update BEFORE UPDATE ON historical_links
 WHEN NEW.import_id!=OLD.import_id OR NEW.message_id!=OLD.message_id
 OR NEW.candidate_source_event_id!=OLD.candidate_source_event_id
 OR NEW.archive_hash IS NOT OLD.archive_hash OR NEW.transcript_fingerprint IS NOT OLD.transcript_fingerprint
 OR NEW.historical_message_id IS NOT OLD.historical_message_id
 OR (OLD.source_event_id IS NOT NULL AND NEW.source_event_id IS NOT OLD.source_event_id)
 OR (OLD.signal_id IS NOT NULL AND NEW.signal_id IS NOT OLD.signal_id)
 OR (NEW.source_event_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM source_events WHERE source_event_id=NEW.source_event_id AND source_message_id=NEW.historical_message_id AND source_type IN ('HISTORICAL_WHATSAPP','SCREENSHOT')))
 OR (NEW.signal_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM signals WHERE signal_id=NEW.signal_id AND source_event_id=NEW.source_event_id))
 BEGIN SELECT RAISE(ABORT,'Invalid or changed historical lineage'); END;
CREATE TRIGGER historical_link_no_delete BEFORE DELETE ON historical_links
 BEGIN SELECT RAISE(ABORT,'Historical provenance must be retained'); END;
CREATE TRIGGER historical_no_intent BEFORE INSERT ON order_intents
 WHEN EXISTS(SELECT 1 FROM signals WHERE signal_id=NEW.signal_id AND source_event_id IS NOT NULL
 AND source_type IN ('HISTORICAL_WHATSAPP','SCREENSHOT'))
 BEGIN SELECT RAISE(ABORT,'Historical sources cannot create intents'); END;
CREATE TRIGGER historical_no_approval BEFORE INSERT ON risk_decisions
 WHEN NEW.decision='APPROVED' AND EXISTS(SELECT 1 FROM order_intents i JOIN signals s ON s.signal_id=i.signal_id
 WHERE i.intent_id=NEW.intent_id AND s.source_event_id IS NOT NULL AND s.source_type IN ('HISTORICAL_WHATSAPP','SCREENSHOT'))
 BEGIN SELECT RAISE(ABORT,'Historical sources cannot receive execution approval'); END;
CREATE TRIGGER historical_no_broker_order BEFORE INSERT ON broker_orders
 WHEN EXISTS(SELECT 1 FROM order_intents i JOIN signals s ON s.signal_id=i.signal_id
 WHERE i.intent_id=NEW.intent_id AND s.source_event_id IS NOT NULL AND s.source_type IN ('HISTORICAL_WHATSAPP','SCREENSHOT'))
 BEGIN SELECT RAISE(ABORT,'Historical sources cannot create broker orders'); END;
CREATE TRIGGER historical_no_position BEFORE INSERT ON positions
 WHEN EXISTS(SELECT 1 FROM order_intents i JOIN signals s ON s.signal_id=i.signal_id
 WHERE i.intent_id=NEW.originating_intent AND s.source_event_id IS NOT NULL AND s.source_type IN ('HISTORICAL_WHATSAPP','SCREENSHOT'))
 BEGIN SELECT RAISE(ABORT,'Historical sources cannot create positions'); END;
INSERT INTO schema_migrations VALUES(4,CURRENT_TIMESTAMP);
