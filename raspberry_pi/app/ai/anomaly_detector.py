from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AnomalyResult:
    is_anomaly: bool
    level: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnomalyDetector:
    model_name = "anomaly_rule_fallback_v1"

    def detect(self, readings: list[dict[str, Any]]) -> AnomalyResult:
        if not readings:
            return AnomalyResult(False, "info", [])

        latest = readings[-1]
        reasons: list[str] = []
        level = "info"

        checks = [
            ("air_temp", latest.get("air_temp"), -5, 50),
            ("air_humidity", latest.get("air_humidity"), 0, 100),
            ("soil_moisture", latest.get("soil_moisture"), 0, 100),
            ("soil_temp", latest.get("soil_temp"), -5, 45),
            ("light_lux", latest.get("light_lux"), 0, 120000),
        ]

        for name, value, low, high in checks:
            if value is None:
                reasons.append(f"{name} missing")
            else:
                value_f = float(value)
                if value_f < low or value_f > high:
                    reasons.append(f"{name} out of range: {value_f}")

        if latest.get("water_level") == "low":
            reasons.append("water tank level is low")
            level = "critical"

        if len(readings) >= 4:
            soil_values = [float(r["soil_moisture"]) for r in readings[-4:] if r.get("soil_moisture") is not None]
            if len(soil_values) >= 4 and max(soil_values) - min(soil_values) > 35:
                reasons.append("soil moisture changed too quickly")

        if reasons and level != "critical":
            level = "warning"

        return AnomalyResult(bool(reasons), level, reasons)
