PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS signals(
 signal_id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
 source_message_id TEXT NOT NULL, payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(source_type,source_id,source_message_id)
);
CREATE TABLE IF NOT EXISTS halt_state(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 state TEXT NOT NULL CHECK(state IN ('ACTIVE','HALTED','RECOVERY_REQUIRED')),
 version INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL, updated_at TEXT NOT NULL
);
INSERT INTO halt_state VALUES(1,'RECOVERY_REQUIRED',0,'Initial reconciliation has not run',CURRENT_TIMESTAMP)
 ON CONFLICT(singleton) DO NOTHING;
CREATE TABLE IF NOT EXISTS order_intents(
 intent_id TEXT PRIMARY KEY, signal_id TEXT NOT NULL REFERENCES signals(signal_id),
 client_order_id TEXT NOT NULL UNIQUE, request_hash TEXT NOT NULL, request TEXT NOT NULL,
 action TEXT NOT NULL CHECK(action IN ('OPEN','MODIFY','PARTIAL_CLOSE','CLOSE','EMERGENCY_CLOSE','ADOPT')),
 symbol TEXT NOT NULL, target_position_id TEXT,
 state TEXT NOT NULL CHECK(state IN ('CREATED','APPROVED','SUBMITTING','SUBMITTED','PLACED','PARTIALLY_FILLED','FILLED','REJECTED','CANCELLED','UNKNOWN','RECOVERY_REQUIRED')),
 created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_logical_intent ON order_intents(signal_id,action,coalesce(target_position_id,''));
CREATE TABLE IF NOT EXISTS risk_decisions(
 risk_decision_id TEXT PRIMARY KEY, intent_id TEXT NOT NULL REFERENCES order_intents(intent_id),
 decision TEXT NOT NULL CHECK(decision IN ('APPROVED','REJECTED')),
 reason_codes TEXT NOT NULL, risk_budget REAL NOT NULL CHECK(risk_budget>=0),
 approved_volume REAL NOT NULL CHECK(approved_volume>=0), state_version INTEGER NOT NULL,
 timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reservations(
 intent_id TEXT PRIMARY KEY REFERENCES order_intents(intent_id),
 risk_amount REAL NOT NULL CHECK(risk_amount>=0), notional REAL NOT NULL CHECK(notional>=0),
 margin REAL NOT NULL CHECK(margin>=0), volume REAL NOT NULL CHECK(volume>=0),
 state TEXT NOT NULL CHECK(state IN ('RESERVED','CONVERTED','RELEASED'))
);
CREATE TABLE IF NOT EXISTS broker_orders(
 broker_order_id TEXT PRIMARY KEY, intent_id TEXT NOT NULL REFERENCES order_intents(intent_id),
 client_order_id TEXT NOT NULL UNIQUE REFERENCES order_intents(client_order_id),
 retcode INTEGER NOT NULL, requested_volume REAL NOT NULL CHECK(requested_volume>0),
 filled_volume REAL NOT NULL CHECK(filled_volume>=0 AND filled_volume<=requested_volume),
 status TEXT NOT NULL, timestamp REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS positions(
 broker_position_id TEXT PRIMARY KEY, originating_intent TEXT NOT NULL REFERENCES order_intents(intent_id),
 symbol TEXT NOT NULL, direction TEXT NOT NULL CHECK(direction IN ('BUY','SELL')),
 open_volume REAL NOT NULL CHECK(open_volume>=0),
 lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('OPEN','CLOSED','RECOVERY_REQUIRED'))
);
CREATE TABLE IF NOT EXISTS broker_deals(
 broker_deal_id TEXT PRIMARY KEY, broker_order_id TEXT NOT NULL REFERENCES broker_orders(broker_order_id),
 broker_position_id TEXT NOT NULL, deal_type TEXT NOT NULL CHECK(deal_type IN ('IN','OUT')),
 volume REAL NOT NULL CHECK(volume>0), price REAL NOT NULL CHECK(price>0),
 profit REAL NOT NULL, commission REAL NOT NULL, swap REAL NOT NULL, fee REAL NOT NULL,
 timestamp REAL NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trade_outcomes(
 outcome_id TEXT PRIMARY KEY, position_id TEXT NOT NULL UNIQUE REFERENCES positions(broker_position_id),
 confirmed_close_timestamp REAL NOT NULL, realized_pnl REAL NOT NULL,
 commission REAL NOT NULL, swap REAL NOT NULL, fees REAL NOT NULL, pnl_in_r REAL,
 source TEXT NOT NULL CHECK(source='BROKER_CONFIRMED'), evidence_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
 event_type TEXT NOT NULL, intent_id TEXT REFERENCES order_intents(intent_id),
 payload TEXT NOT NULL, timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quarantine(
 evidence_id TEXT PRIMARY KEY, reason TEXT NOT NULL, payload TEXT NOT NULL, timestamp TEXT NOT NULL
);
INSERT INTO schema_migrations VALUES(1,CURRENT_TIMESTAMP) ON CONFLICT(version) DO NOTHING;
CREATE TRIGGER IF NOT EXISTS signals_no_update BEFORE UPDATE ON signals BEGIN SELECT RAISE(ABORT,'Immutable signal'); END;
CREATE TRIGGER IF NOT EXISTS signals_no_delete BEFORE DELETE ON signals BEGIN SELECT RAISE(ABORT,'Immutable signal'); END;
CREATE TRIGGER IF NOT EXISTS deals_no_update BEFORE UPDATE ON broker_deals BEGIN SELECT RAISE(ABORT,'Immutable broker deal'); END;
CREATE TRIGGER IF NOT EXISTS deals_no_delete BEFORE DELETE ON broker_deals BEGIN SELECT RAISE(ABORT,'Immutable broker deal'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT,'Append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT,'Append-only audit'); END;
COMMIT;
