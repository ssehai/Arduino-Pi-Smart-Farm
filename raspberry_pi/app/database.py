from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import BASE_DIR, settings


KST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(KST).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, db_path: Path = settings.db_path) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        schema = (BASE_DIR / "schemas.sql").read_text(encoding="utf-8")
        with self._lock, self.connect() as conn:
            conn.executescript(schema)
            conn.execute("INSERT OR IGNORE INTO app_state(key, value) VALUES('mode', 'auto')")
            conn.execute("INSERT OR IGNORE INTO app_state(key, value) VALUES('pump', 'off')")
            conn.execute("INSERT OR IGNORE INTO app_state(key, value) VALUES('fan', 'off')")
            conn.execute("INSERT OR IGNORE INTO app_state(key, value) VALUES('light', '0')")

    def insert_sensor_reading(self, reading: dict[str, Any]) -> int:
        payload = {
            "timestamp": reading.get("timestamp") or now_iso(),
            "air_temp": reading.get("air_temp"),
            "air_humidity": reading.get("air_humidity"),
            "soil_moisture": reading.get("soil_moisture"),
            "soil_temp": reading.get("soil_temp"),
            "light_lux": reading.get("light_lux"),
            "water_level": reading.get("water_level"),
            "ph": reading.get("ph"),
            "ec": reading.get("ec"),
            "co2": reading.get("co2"),
        }
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO sensor_readings(
                  timestamp, air_temp, air_humidity, soil_moisture, soil_temp,
                  light_lux, water_level, ph, ec, co2
                ) VALUES (
                  :timestamp, :air_temp, :air_humidity, :soil_moisture, :soil_temp,
                  :light_lux, :water_level, :ph, :ec, :co2
                )
                """,
                payload,
            )
            return int(cur.lastrowid)

    def latest_sensor_reading(self) -> dict[str, Any] | None:
        with self._lock, self.connect() as conn:
            row = conn.execute("SELECT * FROM sensor_readings ORDER BY timestamp DESC, id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def sensor_history(self, hours: int = 24, limit: int = 500) -> list[dict[str, Any]]:
        since = (datetime.now(KST) - timedelta(hours=hours)).replace(microsecond=0).isoformat()
        with self._lock, self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sensor_readings
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (since, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def insert_event(
        self,
        actuator: str,
        action: str,
        duration_ms: int | None,
        reason: str,
        source: str,
    ) -> int:
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO actuator_events(timestamp, actuator, action, duration_ms, reason, source)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (now_iso(), actuator, action, duration_ms, reason, source),
            )
            return int(cur.lastrowid)

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM actuator_events ORDER BY timestamp DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def last_watering_event(self) -> dict[str, Any] | None:
        with self._lock, self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM actuator_events
                WHERE actuator = 'pump' AND action = 'on'
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            return dict(row) if row else None

    def daily_pump_usage_ms(self) -> int:
        since = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        with self._lock, self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(duration_ms), 0) AS total
                FROM actuator_events
                WHERE actuator = 'pump' AND action = 'on' AND timestamp >= ?
                """,
                (since,),
            ).fetchone()
            return int(row["total"] or 0)

    def insert_prediction(
        self,
        model_name: str,
        input_summary: dict[str, Any],
        prediction: dict[str, Any],
        confidence: float | None,
        accepted_by_rules: bool,
    ) -> int:
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO ai_predictions(
                  timestamp, model_name, input_summary, prediction, confidence, accepted_by_rules
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    model_name,
                    json.dumps(input_summary, ensure_ascii=False),
                    json.dumps(prediction, ensure_ascii=False),
                    confidence,
                    int(accepted_by_rules),
                ),
            )
            return int(cur.lastrowid)

    def latest_predictions(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock, self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ai_predictions ORDER BY timestamp DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def insert_alert(self, level: str, message: str) -> int:
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO alerts(timestamp, level, message, resolved) VALUES(?, ?, ?, 0)",
                (now_iso(), level, message),
            )
            return int(cur.lastrowid)

    def recent_alerts(self, limit: int = 30, include_resolved: bool = False) -> list[dict[str, Any]]:
        where = "" if include_resolved else "WHERE resolved = 0"
        with self._lock, self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM alerts {where} ORDER BY timestamp DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def set_state(self, key: str, value: str) -> None:
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_state(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_state(self, key: str, default: str | None = None) -> str | None:
        with self._lock, self.connect() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else default

    def all_state(self) -> dict[str, str]:
        with self._lock, self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM app_state").fetchall()
            return {str(row["key"]): str(row["value"]) for row in rows}
