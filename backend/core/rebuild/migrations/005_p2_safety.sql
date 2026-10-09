CREATE TABLE p2_policy(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), version TEXT NOT NULL,
 policy_hash TEXT NOT NULL, configuration TEXT NOT NULL
);
CREATE TABLE p2_baselines(
 account_key TEXT PRIMARY KEY REFERENCES account_binding(account_key),
 observed_at TEXT NOT NULL, cash_flow_total TEXT NOT NULL,
 day_start TEXT NOT NULL, week_start TEXT NOT NULL,
 day_equity TEXT NOT NULL, week_equity TEXT NOT NULL, high_water_equity TEXT NOT NULL
);
CREATE TABLE p2_evaluations(
 decision_id TEXT PRIMARY KEY REFERENCES risk_decisions(risk_decision_id),
 intent_id TEXT NOT NULL REFERENCES order_intents(intent_id),
 policy_hash TEXT NOT NULL, inputs_hash TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TRIGGER p2_evaluation_no_update BEFORE UPDATE ON p2_evaluations BEGIN SELECT RAISE(ABORT,'Immutable safety evidence'); END;
CREATE TRIGGER p2_evaluation_no_delete BEFORE DELETE ON p2_evaluations BEGIN SELECT RAISE(ABORT,'Immutable safety evidence'); END;
CREATE TABLE p2_reservations(
 intent_id TEXT PRIMARY KEY REFERENCES order_intents(intent_id),
 decision_id TEXT NOT NULL REFERENCES p2_evaluations(decision_id),
 symbol TEXT NOT NULL, direction TEXT NOT NULL CHECK(direction IN ('BUY','SELL')),
 risk TEXT NOT NULL, notional TEXT NOT NULL, margin TEXT NOT NULL, volume TEXT NOT NULL,
 expires_at TEXT NOT NULL, policy_hash TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RESERVED','SUBMISSION_BEGUN','AMBIGUOUS','PARTIAL','CONVERTED','RELEASED')),
 filled_volume TEXT NOT NULL DEFAULT '0', terminal_evidence_id TEXT
);
CREATE TABLE p2_execution_requests(
 execution_request_id TEXT PRIMARY KEY,
 intent_id TEXT NOT NULL REFERENCES order_intents(intent_id),
 decision_id TEXT NOT NULL UNIQUE REFERENCES p2_evaluations(decision_id),
 account_key TEXT NOT NULL REFERENCES account_binding(account_key),
 policy_hash TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status='ELIGIBLE_NOT_SUBMITTED'),
 created_at TEXT NOT NULL
);
CREATE TABLE p2_reservation_events(
 evidence_id TEXT PRIMARY KEY, intent_id TEXT NOT NULL REFERENCES p2_reservations(intent_id),
 payload TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TRIGGER p2_reservation_event_no_update BEFORE UPDATE ON p2_reservation_events BEGIN SELECT RAISE(ABORT,'Immutable reservation evidence'); END;
CREATE TRIGGER p2_reservation_event_no_delete BEFORE DELETE ON p2_reservation_events BEGIN SELECT RAISE(ABORT,'Immutable reservation evidence'); END;
CREATE TRIGGER p2_request_approval BEFORE INSERT ON p2_execution_requests
 WHEN NOT EXISTS(SELECT 1 FROM risk_decisions d JOIN p2_evaluations e ON e.decision_id=d.risk_decision_id
 JOIN p2_reservations r ON r.intent_id=d.intent_id JOIN p2_policy p ON p.singleton=1
 JOIN order_intents i ON i.intent_id=d.intent_id JOIN signals s ON s.signal_id=i.signal_id
 JOIN account_binding a ON a.account_key=NEW.account_key JOIN halt_state h ON h.singleton=1
 WHERE d.risk_decision_id=NEW.decision_id AND d.intent_id=NEW.intent_id AND d.decision='APPROVED'
 AND d.evidence_scope='P2_NON_EXECUTING' AND r.decision_id=d.risk_decision_id AND r.state='RESERVED'
 AND e.policy_hash=NEW.policy_hash AND p.policy_hash=NEW.policy_hash AND r.policy_hash=NEW.policy_hash
 AND h.state='ACTIVE' AND h.version=d.state_version
 AND julianday(NEW.created_at) < julianday(r.expires_at)
 AND s.source_event_id IS NOT NULL AND s.source_type IN ('MANUAL','WHATSAPP_HUMAN','NEXUSAI_STRATEGY')
 AND NOT EXISTS(SELECT 1 FROM risk_decisions v WHERE v.intent_id=d.intent_id AND v.decision='REJECTED'))
 BEGIN SELECT RAISE(ABORT,'P2 request requires current reserved approval and exact lineage'); END;
CREATE TRIGGER p2_request_no_update BEFORE UPDATE ON p2_execution_requests BEGIN SELECT RAISE(ABORT,'Immutable request'); END;
CREATE TRIGGER p2_request_no_delete BEFORE DELETE ON p2_execution_requests BEGIN SELECT RAISE(ABORT,'Immutable request'); END;
INSERT INTO schema_migrations VALUES(5,CURRENT_TIMESTAMP);
