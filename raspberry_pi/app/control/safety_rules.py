from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


MAX_PUMP_DURATION_MS = 10000
DAILY_MAX_PUMP_MS = 60000
MIN_WATERING_INTERVAL_HOURS = 6


@dataclass(frozen=True)
class SafetyDecision:
    accepted: bool
    reason: str


def validate_sensor_reading(reading: dict[str, Any]) -> list[str]:
    alerts: list[str] = []
    ranges = {
        "air_temp": (-5, 50),
        "air_humidity": (0, 100),
        "soil_moisture": (0, 100),
        "soil_temp": (-5, 45),
        "light_lux": (0, 120000),
        "ph": (3, 10),
        "ec": (0, 8),
        "co2": (250, 5000),
    }
    for key, (low, high) in ranges.items():
        value = reading.get(key)
        if value is None:
            continue
        try:
            value_f = float(value)
        except (TypeError, ValueError):
            alerts.append(f"{key} is not numeric")
            continue
        if value_f < low or value_f > high:
            alerts.append(f"{key} out of safe range: {value_f}")
    if reading.get("water_level") not in (None, "ok", "low"):
        alerts.append(f"unknown water_level: {reading.get('water_level')}")
    return alerts


def validate_command(
    latest: dict[str, Any] | None,
    actuator: str,
    action: str,
    duration_ms: int | None,
    source: str,
    daily_pump_usage_ms: int,
    last_watering_hours: float | None,
) -> SafetyDecision:
    if latest is None:
        return SafetyDecision(False, "no sensor reading available")

    sensor_alerts = validate_sensor_reading(latest)
    if sensor_alerts and actuator in {"pump", "light"} and action != "off":
        return SafetyDecision(False, "sensor invalid: " + "; ".join(sensor_alerts[:2]))

    if actuator == "pump" and action == "on":
        if latest.get("water_level") != "ok":
            return SafetyDecision(False, "water level low")
        if duration_ms is None or duration_ms <= 0:
            return SafetyDecision(False, "pump duration required")
        if duration_ms > MAX_PUMP_DURATION_MS:
            return SafetyDecision(False, "pump duration exceeds single-run limit")
        if daily_pump_usage_ms + duration_ms > DAILY_MAX_PUMP_MS:
            return SafetyDecision(False, "daily pump limit reached")
        if source != "manual" and last_watering_hours is not None and last_watering_hours < MIN_WATERING_INTERVAL_HOURS:
            return SafetyDecision(False, "minimum watering interval not reached")

    if actuator == "fan" and action == "on":
        air_temp = latest.get("air_temp")
        humidity = latest.get("air_humidity")
        if air_temp is None and humidity is None:
            return SafetyDecision(False, "fan requires temperature or humidity reading")

    if actuator == "light" and action == "on":
        hour = datetime.now().hour
        if hour < 5 or hour > 22:
            return SafetyDecision(False, "light schedule lockout")

    return SafetyDecision(True, "passed safety rules")
