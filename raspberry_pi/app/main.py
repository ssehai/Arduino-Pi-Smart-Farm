from __future__ import annotations

import asyncio
import json
import math
import random
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .ai.disease_model import DiseaseModel
from .config import BASE_DIR, settings
from .control.engine import ControlEngine, NoopTransport
from .control.safety_rules import validate_sensor_reading
from .database import Database, now_iso
from .serial_comm.serial_client import SerialClient


class ModeRequest(BaseModel):
    mode: str = Field(pattern="^(auto|manual)$")


class ControlRequest(BaseModel):
    action: str = Field(pattern="^(on|off)$")
    duration_ms: Optional[int] = Field(default=None, ge=0, le=10000)
    value: Optional[int] = Field(default=None, ge=0, le=255)
    reason: str = "manual dashboard control"


class EventBroker:
    def __init__(self) -> None:
        self.clients: set[asyncio.Queue[str]] = set()

    async def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
        self.clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self.clients.discard(queue)

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for queue in list(self.clients):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await queue.put(payload)


db = Database()
broker = EventBroker()
disease_model = DiseaseModel()
serial_client: SerialClient | None = None
engine = ControlEngine(db, NoopTransport())


async def handle_sensor_message(message: dict[str, Any]) -> None:
    reading = dict(message)
    reading.pop("type", None)
    reading["timestamp"] = now_iso()
    db.insert_sensor_reading(reading)
    for alert in validate_sensor_reading(reading):
        db.insert_alert("warning", alert)
    await broker.publish("status", build_status())


async def handle_serial_message(message: dict[str, Any]) -> None:
    if message.get("type") == "safety_event":
        db.insert_alert(str(message.get("level") or "warning"), str(message.get("message") or "Arduino safety event"))
    await broker.publish("serial", message)


async def simulator_loop() -> None:
    tick = 0
    while True:
        tick += 1
        soil = max(18, min(78, 48 - tick * 0.08 + random.uniform(-1.2, 1.2)))
        if tick % 180 == 0:
            soil += 18
        reading = {
            "type": "sensor_reading",
            "timestamp": now_iso(),
            "air_temp": round(24 + 5 * math.sin(tick / 40) + random.uniform(-0.3, 0.3), 1),
            "air_humidity": round(62 + 15 * math.sin(tick / 53) + random.uniform(-1.5, 1.5), 1),
            "soil_moisture": round(soil, 1),
            "soil_temp": round(22 + 2 * math.sin(tick / 60), 1),
            "light_lux": round(max(0, 12000 + 9000 * math.sin(tick / 35)), 0),
            "water_level": "low" if tick % 240 > 220 else "ok",
            "ph": 6.2,
            "ec": 2.1,
            "co2": 550,
        }
        await handle_sensor_message(reading)
        await asyncio.sleep(settings.simulator_interval_seconds)


async def control_loop() -> None:
    while True:
        actions = await engine.run_once()
        if actions:
            await broker.publish("status", build_status())
        await asyncio.sleep(settings.control_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global serial_client, engine
    tasks: list[asyncio.Task[Any]] = []

    if settings.serial_port:
        serial_client = SerialClient(
            port=settings.serial_port,
            baudrate=settings.serial_baudrate,
            on_sensor=handle_sensor_message,
            on_message=handle_serial_message,
        )
        engine = ControlEngine(db, serial_client)
        tasks.append(asyncio.create_task(serial_client.start()))
    else:
        engine = ControlEngine(db, NoopTransport())
        tasks.append(asyncio.create_task(simulator_loop()))

    tasks.append(asyncio.create_task(control_loop()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request, "app_name": settings.app_name})


@app.get("/api/status")
async def api_status() -> dict[str, Any]:
    return build_status()


@app.get("/api/history")
async def api_history(hours: int = 24) -> dict[str, Any]:
    return {"items": db.sensor_history(hours=max(1, min(hours, 168)))}


@app.get("/api/events")
async def api_events(limit: int = 50) -> dict[str, Any]:
    return {"items": db.recent_events(limit=max(1, min(limit, 200)))}


@app.get("/api/alerts")
async def api_alerts() -> dict[str, Any]:
    return {"items": db.recent_alerts()}


@app.get("/api/stream")
async def api_stream() -> StreamingResponse:
    queue = await broker.subscribe()

    async def generator():
        try:
            yield f"event: status\ndata: {json.dumps(build_status(), ensure_ascii=False)}\n\n"
            while True:
                yield await queue.get()
        finally:
            broker.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.post("/api/mode")
async def api_mode(payload: ModeRequest) -> dict[str, Any]:
    db.set_state("mode", payload.mode)
    await broker.publish("status", build_status())
    return {"mode": payload.mode}


@app.post("/api/control/pump")
async def api_control_pump(payload: ControlRequest) -> dict[str, Any]:
    duration = payload.duration_ms if payload.action == "on" else None
    result = await engine.apply_command("pump", payload.action, duration, None, "manual", payload.reason)
    await broker.publish("status", build_status())
    return result


@app.post("/api/control/fan")
async def api_control_fan(payload: ControlRequest) -> dict[str, Any]:
    result = await engine.apply_command("fan", payload.action, None, None, "manual", payload.reason)
    await broker.publish("status", build_status())
    return result


@app.post("/api/control/light")
async def api_control_light(payload: ControlRequest) -> dict[str, Any]:
    value = payload.value if payload.action == "on" else 0
    result = await engine.apply_command("light", payload.action, None, value, "manual", payload.reason)
    await broker.publish("status", build_status())
    return result


@app.post("/api/camera/analyze")
async def api_camera_analyze(image: UploadFile = File(...)) -> dict[str, Any]:
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="empty image")
    prediction = disease_model.predict(image_bytes)
    db.insert_prediction(
        model_name=disease_model.model_name,
        input_summary={"filename": image.filename, "bytes": len(image_bytes)},
        prediction=prediction.to_dict(),
        confidence=prediction.confidence,
        accepted_by_rules=False,
    )
    await broker.publish("status", build_status())
    return prediction.to_dict()


def build_status() -> dict[str, Any]:
    return {
        "latest": db.latest_sensor_reading(),
        "state": db.all_state(),
        "events": db.recent_events(10),
        "alerts": db.recent_alerts(10),
        "predictions": db.latest_predictions(5),
        "serial_connected": settings.serial_port is not None,
        "timestamp": now_iso(),
    }
