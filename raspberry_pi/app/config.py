from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("SMARTFARM_DATA_DIR", BASE_DIR.parent / "data"))


@dataclass(frozen=True)
class Settings:
    app_name: str = "Cherry Tomato AI Smart Farm"
    db_path: Path = DATA_DIR / "smartfarm.sqlite3"
    serial_port: str | None = os.getenv("SERIAL_PORT")
    serial_baudrate: int = int(os.getenv("SERIAL_BAUDRATE", "115200"))
    control_interval_seconds: int = int(os.getenv("CONTROL_INTERVAL_SECONDS", "30"))
    simulator_interval_seconds: int = int(os.getenv("SIMULATOR_INTERVAL_SECONDS", "5"))


settings = Settings()
