from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import serial
from serial import SerialException


SensorCallback = Callable[[dict[str, Any]], Awaitable[None]]
AckCallback = Callable[[dict[str, Any]], Awaitable[None]]


class SerialClient:
    def __init__(
        self,
        port: str,
        baudrate: int,
        on_sensor: SensorCallback,
        on_message: AckCallback | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.on_sensor = on_sensor
        self.on_message = on_message
        self._serial: serial.Serial | None = None
        self._write_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self.is_connected = False
        self.last_message_at: str | None = None
        self.last_error: str | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        while True:
            try:
                self._serial = serial.Serial(self.port, self.baudrate, timeout=1)
            except (OSError, SerialException) as exc:
                self._serial = None
                self.is_connected = False
                self.last_error = str(exc)
                await asyncio.sleep(3)
                continue

            self.is_connected = True
            self.last_error = None
            await asyncio.to_thread(self._read_loop)
            await asyncio.sleep(3)

    def _read_loop(self) -> None:
        assert self._serial is not None
        while True:
            try:
                raw = self._serial.readline()
            except (OSError, SerialException) as exc:
                self.is_connected = False
                self.last_error = str(exc)
                try:
                    self._serial.close()
                except (OSError, SerialException, AttributeError):
                    pass
                self._serial = None
                return
            if not raw:
                continue
            try:
                message = json.loads(raw.decode("utf-8").strip())
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            self.last_message_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            if self._loop is not None:
                asyncio.run_coroutine_threadsafe(self._dispatch(message), self._loop)

    async def _dispatch(self, message: dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type == "sensor_reading":
            await self.on_sensor(message)
        elif msg_type == "command_ack":
            command_id = str(message.get("command_id"))
            pending = self._pending.pop(command_id, None)
            if pending and not pending.done():
                pending.set_result(message)
        if self.on_message:
            await self.on_message(message)

    async def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        if self._serial is None or not self.is_connected:
            return {
                "type": "command_ack",
                "command_id": command["command_id"],
                "status": "rejected",
                "message": "serial not connected",
            }

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[command["command_id"]] = future

        payload = (json.dumps(command, separators=(",", ":")) + "\n").encode("utf-8")
        async with self._write_lock:
            await asyncio.to_thread(self._serial.write, payload)
            await asyncio.to_thread(self._serial.flush)

        try:
            return await asyncio.wait_for(future, timeout=3)
        except asyncio.TimeoutError:
            self._pending.pop(command["command_id"], None)
            return {
                "type": "command_ack",
                "command_id": command["command_id"],
                "status": "rejected",
                "message": "ack timeout",
            }

    def status(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "device_present": Path(self.port).exists(),
            "serial_open": self.is_connected,
            "last_message_at": self.last_message_at,
            "last_error": self.last_error,
        }
