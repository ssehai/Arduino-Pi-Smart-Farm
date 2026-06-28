from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from ..ai.anomaly_detector import AnomalyDetector
from ..ai.irrigation_model import IrrigationModel
from ..database import Database
from .safety_rules import validate_command, validate_sensor_reading


class CommandTransport(Protocol):
    async def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        ...


class NoopTransport:
    async def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "command_ack",
            "command_id": command["command_id"],
            "status": "accepted",
            "message": "simulated transport accepted command",
        }


class ControlEngine:
    def __init__(self, db: Database, transport: CommandTransport | None = None) -> None:
        self.db = db
        self.transport = transport or NoopTransport()
        self.irrigation_model = IrrigationModel()
        self.anomaly_detector = AnomalyDetector()

    def last_watering_hours(self) -> float | None:
        event = self.db.last_watering_event()
        if not event:
            return None
        try:
            ts = datetime.fromisoformat(event["timestamp"])
        except ValueError:
            return None
        return (datetime.now(ts.tzinfo) - ts).total_seconds() / 3600

    async def run_once(self) -> list[dict[str, Any]]:
        latest = self.db.latest_sensor_reading()
        if latest is None:
            return []

        actions: list[dict[str, Any]] = []
        for alert in validate_sensor_reading(latest):
            self.db.insert_alert("warning", alert)

        recent = self.db.sensor_history(hours=2, limit=80)
        anomaly = self.anomaly_detector.detect(recent)
        if anomaly.is_anomaly:
            self.db.insert_alert(anomaly.level, "; ".join(anomaly.reasons))

        mode = self.db.get_state("mode", "auto")
        if mode != "auto":
            return actions

        actions.extend(await self._rule_based_actions(latest))
        actions.extend(await self._ai_irrigation_action(latest))
        return actions

    async def _rule_based_actions(self, latest: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        soil = latest.get("soil_moisture")
        water_level = latest.get("water_level")
        air_temp = latest.get("air_temp")
        humidity = latest.get("air_humidity")
        lux = latest.get("light_lux")
        last_hours = self.last_watering_hours()

        if soil is not None and float(soil) < 35 and water_level == "ok" and (last_hours is None or last_hours > 6):
            result = await self.apply_command("pump", "on", 5000, None, "rule", "soil moisture below 35")
            actions.append(result)

        fan_should_on = (air_temp is not None and float(air_temp) > 30) or (humidity is not None and float(humidity) > 85)
        fan_should_off = (air_temp is not None and float(air_temp) < 27) and (humidity is not None and float(humidity) < 78)
        if fan_should_on and self.db.get_state("fan") != "on":
            actions.append(await self.apply_command("fan", "on", None, None, "rule", "temperature or humidity high"))
        elif fan_should_off and self.db.get_state("fan") != "off":
            actions.append(await self.apply_command("fan", "off", None, None, "rule", "temperature and humidity normalized"))

        hour = datetime.now().hour
        if 6 <= hour <= 20 and lux is not None and float(lux) < 9000 and self.db.get_state("light") == "0":
            actions.append(await self.apply_command("light", "on", None, 180, "rule", "daytime light below target"))
        elif (hour > 20 or hour < 6) and self.db.get_state("light") != "0":
            actions.append(await self.apply_command("light", "off", None, 0, "rule", "night light schedule"))

        if water_level == "low":
            if self.db.get_state("pump") == "on":
                actions.append(await self.apply_command("pump", "off", None, None, "safety", "water level low"))
            self.db.insert_alert("critical", "Water tank level low: pump lockout active")

        return actions

    async def _ai_irrigation_action(self, latest: dict[str, Any]) -> list[dict[str, Any]]:
        recommendation = self.irrigation_model.predict(latest, self.last_watering_hours(), datetime.now())
        command_would_pass = validate_command(
            latest=latest,
            actuator="pump",
            action="on",
            duration_ms=recommendation.duration_ms,
            source="ai",
            daily_pump_usage_ms=self.db.daily_pump_usage_ms(),
            last_watering_hours=self.last_watering_hours(),
        )
        accepted = recommendation.needs_water and command_would_pass.accepted
        self.db.insert_prediction(
            model_name=self.irrigation_model.model_name,
            input_summary={
                "soil_moisture": latest.get("soil_moisture"),
                "air_temp": latest.get("air_temp"),
                "air_humidity": latest.get("air_humidity"),
                "light_lux": latest.get("light_lux"),
                "last_watering_hours": self.last_watering_hours(),
            },
            prediction=recommendation.to_dict() | {"safety_reason": command_would_pass.reason},
            confidence=recommendation.probability,
            accepted_by_rules=accepted,
        )

        if not accepted:
            return []

        result = await self.apply_command(
            "pump",
            "on",
            recommendation.duration_ms,
            None,
            "ai",
            "ai irrigation recommendation passed safety rules",
        )
        return [result]

    async def apply_command(
        self,
        actuator: str,
        action: str,
        duration_ms: int | None,
        value: int | None,
        source: str,
        reason: str,
    ) -> dict[str, Any]:
        latest = self.db.latest_sensor_reading()
        last_hours = self.last_watering_hours()
        decision = validate_command(
            latest=latest,
            actuator=actuator,
            action=action,
            duration_ms=duration_ms,
            source=source,
            daily_pump_usage_ms=self.db.daily_pump_usage_ms(),
            last_watering_hours=last_hours,
        )
        if not decision.accepted:
            self.db.insert_alert("warning", f"{actuator} {action} blocked: {decision.reason}")
            return {"accepted": False, "reason": decision.reason}

        command = {
            "type": "command",
            "command_id": f"cmd_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}",
            "actuator": actuator,
            "action": action,
            "duration_ms": duration_ms or 0,
            "value": value if value is not None else 0,
            "reason": reason.replace(" ", "_"),
        }
        ack = await self.transport.send_command(command)
        accepted_by_arduino = ack.get("status") == "accepted"
        if accepted_by_arduino:
            self.db.insert_event(actuator, action, duration_ms, reason, source)
            self._update_actuator_state(actuator, action, value)
        else:
            self.db.insert_alert("warning", f"Arduino rejected {actuator} {action}: {ack.get('message')}")

        return {
            "accepted": accepted_by_arduino,
            "safety": decision.reason,
            "command": command,
            "ack": ack,
        }

    def _update_actuator_state(self, actuator: str, action: str, value: int | None) -> None:
        if actuator == "light":
            self.db.set_state("light", str(value or 0 if action == "on" else 0))
        else:
            self.db.set_state(actuator, action)

    @staticmethod
    def pretty_json(data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, indent=2)
