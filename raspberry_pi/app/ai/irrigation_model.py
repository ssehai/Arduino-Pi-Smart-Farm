from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class IrrigationRecommendation:
    needs_water: bool
    probability: float
    duration_ms: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IrrigationModel:
    model_name = "irrigation_rule_fallback_v1"

    def predict(
        self,
        latest: dict[str, Any],
        last_watering_hours: float | None,
        current_time: datetime,
    ) -> IrrigationRecommendation:
        soil = float(latest.get("soil_moisture") or 0)
        air_temp = float(latest.get("air_temp") or 24)
        humidity = float(latest.get("air_humidity") or 60)
        lux = float(latest.get("light_lux") or 0)

        score = 0.0
        reasons: list[str] = []

        if soil < 28:
            score += 0.55
            reasons.append("soil moisture is very low")
        elif soil < 35:
            score += 0.35
            reasons.append("soil moisture is below target")

        if air_temp > 29:
            score += 0.15
            reasons.append("air temperature is high")
        if humidity < 45:
            score += 0.10
            reasons.append("air is dry")
        if lux > 25000:
            score += 0.05
            reasons.append("strong light increases transpiration")
        if last_watering_hours is None or last_watering_hours > 6:
            score += 0.15
            reasons.append("enough time passed since watering")

        probability = min(0.98, max(0.02, score))
        needs_water = probability >= 0.60
        duration = 5000 if soil >= 25 else 8000

        return IrrigationRecommendation(
            needs_water=needs_water,
            probability=round(probability, 3),
            duration_ms=duration if needs_water else 0,
            reason=", ".join(reasons) or "conditions are inside the target range",
        )
