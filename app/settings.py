"""Settings that survive restarts: printer credentials, bed size and pen calibration."""

import json
import os
from pathlib import Path

from pydantic import BaseModel

CONFIG_PATH = Path(os.environ.get("BAMBU_PLOTTER_CONFIG", "~/.config/bambu-plotter/settings.json")).expanduser()

BED_PRESETS = {
    "a1mini": ("A1 mini", 180.0, 180.0),
    "a1": ("A1", 256.0, 256.0),
    "p1": ("P1P / P1S / X1", 256.0, 256.0),
}


class Point(BaseModel):
    x: float
    y: float


class Settings(BaseModel):
    ip: str = ""
    serial: str = ""
    access_code: str = ""

    model: str = "a1mini"

    # Pen calibration. The paper corners are in machine coordinates, recorded
    # with the pen tip over them, so the pen's offset from the nozzle never
    # matters.
    paper_top_left: Point | None = None
    paper_bottom_right: Point | None = None

    # Height above the paper the pen travels at, in mm.
    pen_up: float = 3.0
    # How far below the touch point the pen goes when drawing. A little
    # pressure keeps the line continuous on paper that isn't perfectly flat.
    pen_pressure: float = 0.3

    draw_speed: float = 3000.0  # mm/min
    travel_speed: float = 6000.0  # mm/min

    @property
    def bed_size(self) -> tuple[float, float]:
        _, w, h = BED_PRESETS.get(self.model, BED_PRESETS["a1mini"])
        return w, h

    @property
    def has_credentials(self) -> bool:
        return bool(self.ip and self.serial and self.access_code)


def _import_bambucuts() -> Settings:
    """Start from bambucuts' config if it exists, so nobody types the access code twice."""
    path = Path("~/.bambucuts.conf").expanduser()
    try:
        data = json.loads(path.read_text())
    except OSError, ValueError:
        return Settings()
    return Settings(
        ip=data.get("ip", ""),
        serial=data.get("serial", ""),
        access_code=data.get("access_code", ""),
    )


def load() -> Settings:
    try:
        return Settings.model_validate_json(CONFIG_PATH.read_text())
    except OSError, ValueError:
        return _import_bambucuts()


def save(settings: Settings) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(settings.model_dump_json(indent=2))
