CREATE TABLE IF NOT EXISTS sensor_readings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL DEFAULT (datetime('now')),
  air_temp REAL,
  air_humidity REAL,
  soil_moisture REAL,
  soil_temp REAL,
  light_lux REAL,
  water_level TEXT,
  ph REAL,
  ec REAL,
  co2 REAL,
  source TEXT NOT NULL DEFAULT 'arduino'
);

CREATE TABLE IF NOT EXISTS actuator_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL DEFAULT (datetime('now')),
  actuator TEXT NOT NULL,
  action TEXT NOT NULL,
  duration_ms INTEGER,
  reason TEXT,
  source TEXT NOT NULL CHECK (source IN ('rule', 'ai', 'manual', 'safety'))
);

CREATE TABLE IF NOT EXISTS ai_predictions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL DEFAULT (datetime('now')),
  model_name TEXT NOT NULL,
  input_summary TEXT NOT NULL,
  prediction TEXT NOT NULL,
  confidence REAL,
  accepted_by_rules INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL DEFAULT (datetime('now')),
  level TEXT NOT NULL CHECK (level IN ('info', 'warning', 'critical')),
  message TEXT NOT NULL,
  resolved INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp ON sensor_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_actuator_events_timestamp ON actuator_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
