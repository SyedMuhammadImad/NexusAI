CREATE TABLE p3_attempts(
 attempt_id TEXT PRIMARY KEY,
 execution_request_id TEXT NOT NULL UNIQUE REFERENCES p2_execution_requests(execution_request_id),
 intent_id TEXT NOT NULL UNIQUE REFERENCES order_intents(intent_id),
 correlation TEXT NOT NULL UNIQUE, magic INTEGER NOT NULL UNIQUE,
 state TEXT NOT NULL CHECK(state IN ('NOT_SUBMITTED','SUBMISSION_STARTED','SUBMISSION_CONFIRMED','SUBMISSION_AMBIGUOUS','REJECTED_BY_BROKER','PARTIALLY_FILLED','FILLED','CANCELLED')),
 created_at TEXT NOT NULL, started_at TEXT, updated_at TEXT NOT NULL,
 command TEXT, failure TEXT
);
CREATE TRIGGER p3_attempt_lineage BEFORE INSERT ON p3_attempts
 WHEN NOT EXISTS(SELECT 1 FROM p2_execution_requests r JOIN p2_evaluations e ON e.decision_id=r.decision_id
 JOIN risk_decisions d ON d.risk_decision_id=e.decision_id
 WHERE r.execution_request_id=NEW.execution_request_id AND r.intent_id=NEW.intent_id
 AND e.intent_id=NEW.intent_id AND d.decision='APPROVED' AND d.evidence_scope='P2_NON_EXECUTING')
 BEGIN SELECT RAISE(ABORT,'Exact P2 approval required'); END;
CREATE TRIGGER p3_attempt_identity BEFORE UPDATE OF attempt_id,execution_request_id,intent_id,correlation,magic,created_at ON p3_attempts
 BEGIN SELECT RAISE(ABORT,'Immutable execution identity'); END;
CREATE TRIGGER p3_attempt_no_delete BEFORE DELETE ON p3_attempts BEGIN SELECT RAISE(ABORT,'Durable attempt'); END;
CREATE TRIGGER p3_no_resubmit BEFORE UPDATE OF state ON p3_attempts
 WHEN (NEW.state='SUBMISSION_STARTED' AND (OLD.state!='NOT_SUBMITTED' OR OLD.started_at IS NOT NULL))
 OR (NEW.state='NOT_SUBMITTED' AND OLD.started_at IS NOT NULL)
 BEGIN SELECT RAISE(ABORT,'Submission cannot restart'); END;
CREATE TABLE p3_events(
 event_id TEXT PRIMARY KEY, attempt_id TEXT REFERENCES p3_attempts(attempt_id),
 kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER p3_event_no_update BEFORE UPDATE ON p3_events BEGIN SELECT RAISE(ABORT,'Immutable execution evidence'); END;
CREATE TRIGGER p3_event_no_delete BEFORE DELETE ON p3_events BEGIN SELECT RAISE(ABORT,'Immutable execution evidence'); END;
CREATE TABLE p3_orders(
 broker_order_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE REFERENCES p3_attempts(attempt_id),
 payload TEXT NOT NULL, observed_at TEXT NOT NULL
);
CREATE TABLE p3_deals(
 broker_deal_id TEXT PRIMARY KEY, broker_order_id TEXT NOT NULL REFERENCES p3_orders(broker_order_id),
 broker_position_id TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TRIGGER p3_deal_no_update BEFORE UPDATE ON p3_deals BEGIN SELECT RAISE(ABORT,'Immutable broker deal'); END;
CREATE TRIGGER p3_deal_no_delete BEFORE DELETE ON p3_deals BEGIN SELECT RAISE(ABORT,'Immutable broker deal'); END;
CREATE TABLE p3_positions(
 broker_position_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE REFERENCES p3_attempts(attempt_id),
 payload TEXT NOT NULL, observed_at TEXT NOT NULL,
 lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('OPEN','CLOSED','RECOVERY_REQUIRED'))
);
CREATE TABLE p3_exit_orders(
 broker_order_id TEXT PRIMARY KEY, broker_position_id TEXT NOT NULL REFERENCES p3_positions(broker_position_id),
 payload TEXT NOT NULL
);
CREATE TABLE p3_exit_deals(
 broker_deal_id TEXT PRIMARY KEY, broker_order_id TEXT NOT NULL REFERENCES p3_exit_orders(broker_order_id),
 broker_position_id TEXT NOT NULL REFERENCES p3_positions(broker_position_id), payload TEXT NOT NULL
);
CREATE TRIGGER p3_exit_order_no_update BEFORE UPDATE ON p3_exit_orders BEGIN SELECT RAISE(ABORT,'Immutable protective exit'); END;
CREATE TRIGGER p3_exit_order_no_delete BEFORE DELETE ON p3_exit_orders BEGIN SELECT RAISE(ABORT,'Immutable protective exit'); END;
CREATE TRIGGER p3_exit_deal_no_update BEFORE UPDATE ON p3_exit_deals BEGIN SELECT RAISE(ABORT,'Immutable protective deal'); END;
CREATE TRIGGER p3_exit_deal_no_delete BEFORE DELETE ON p3_exit_deals BEGIN SELECT RAISE(ABORT,'Immutable protective deal'); END;
CREATE TRIGGER p3_order_identity BEFORE UPDATE OF broker_order_id,attempt_id ON p3_orders BEGIN SELECT RAISE(ABORT,'Immutable broker order identity'); END;
CREATE TRIGGER p3_position_identity BEFORE UPDATE OF broker_position_id,attempt_id ON p3_positions BEGIN SELECT RAISE(ABORT,'Immutable broker position identity'); END;
CREATE TRIGGER p3_order_no_delete BEFORE DELETE ON p3_orders BEGIN SELECT RAISE(ABORT,'Durable broker order'); END;
CREATE TRIGGER p3_position_no_delete BEFORE DELETE ON p3_positions BEGIN SELECT RAISE(ABORT,'Durable broker position'); END;
INSERT INTO schema_migrations VALUES(6,CURRENT_TIMESTAMP);
