CREATE TABLE account_binding(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), account_key TEXT NOT NULL UNIQUE,
 payload TEXT NOT NULL, bound_at TEXT NOT NULL
);
CREATE TRIGGER account_no_update BEFORE UPDATE ON account_binding BEGIN SELECT RAISE(ABORT,'Immutable account binding'); END;
CREATE TRIGGER account_no_delete BEFORE DELETE ON account_binding BEGIN SELECT RAISE(ABORT,'Immutable account binding'); END;
DROP TRIGGER signals_no_update;
ALTER TABLE signals ADD COLUMN source_timestamp REAL;
ALTER TABLE signals ADD COLUMN received_timestamp REAL;
ALTER TABLE signals ADD COLUMN parser_version TEXT;
ALTER TABLE signals ADD COLUMN status TEXT;
UPDATE signals SET source_timestamp=json_extract(payload,'$.source_timestamp'),
 received_timestamp=json_extract(payload,'$.received_timestamp'), parser_version=json_extract(payload,'$.parser_version'),
 status=json_extract(payload,'$.validation_status');
CREATE TRIGGER signals_no_update BEFORE UPDATE ON signals BEGIN SELECT RAISE(ABORT,'Immutable signal'); END;
ALTER TABLE order_intents ADD COLUMN requested_volume REAL;
ALTER TABLE order_intents ADD COLUMN requested_entry REAL;
ALTER TABLE order_intents ADD COLUMN stop_loss REAL;
ALTER TABLE order_intents ADD COLUMN take_profit REAL;
UPDATE order_intents SET requested_volume=json_extract(request,'$.volume'), requested_entry=json_extract(request,'$.entry'),
 stop_loss=json_extract(request,'$.stop_loss'), take_profit=json_extract(request,'$.take_profit');
CREATE TRIGGER intent_identity_no_update BEFORE UPDATE OF intent_id,signal_id,client_order_id,request_hash,request,action,symbol,target_position_id,requested_volume,requested_entry,stop_loss,take_profit ON order_intents
 BEGIN SELECT RAISE(ABORT,'Immutable intent identity'); END;
CREATE TRIGGER intent_no_delete BEFORE DELETE ON order_intents BEGIN SELECT RAISE(ABORT,'Immutable intent identity'); END;
CREATE TRIGGER order_identity_no_update BEFORE UPDATE OF broker_order_id,intent_id,client_order_id,requested_volume ON broker_orders
 BEGIN SELECT RAISE(ABORT,'Immutable broker order identity'); END;
CREATE TRIGGER order_no_delete BEFORE DELETE ON broker_orders BEGIN SELECT RAISE(ABORT,'Immutable broker order identity'); END;
CREATE TRIGGER deal_requires_position BEFORE INSERT ON broker_deals WHEN NOT EXISTS(
 SELECT 1 FROM positions WHERE broker_position_id=NEW.broker_position_id)
 BEGIN SELECT RAISE(ABORT,'Deal requires exact position identity'); END;
CREATE TRIGGER position_identity_no_update BEFORE UPDATE OF broker_position_id,originating_intent,symbol,direction ON positions
 BEGIN SELECT RAISE(ABORT,'Immutable position identity'); END;
CREATE TABLE position_observations(
 observation_id TEXT PRIMARY KEY, broker_position_id TEXT NOT NULL REFERENCES positions(broker_position_id),
 open_volume REAL NOT NULL CHECK(open_volume>=0), source_timestamp REAL NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE order_observations(
 observation_hash TEXT PRIMARY KEY, broker_order_id TEXT NOT NULL REFERENCES broker_orders(broker_order_id),
 payload TEXT NOT NULL
);
CREATE INDEX deals_by_position ON broker_deals(broker_position_id,timestamp);
CREATE INDEX positions_by_intent ON positions(originating_intent);
CREATE TRIGGER risks_no_update BEFORE UPDATE ON risk_decisions BEGIN SELECT RAISE(ABORT,'Immutable risk decision'); END;
CREATE TRIGGER outcomes_no_update BEFORE UPDATE ON trade_outcomes BEGIN SELECT RAISE(ABORT,'Immutable outcome'); END;
INSERT INTO schema_migrations VALUES(2,CURRENT_TIMESTAMP);
