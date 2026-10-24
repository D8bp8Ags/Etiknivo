"""Application settings and local file locations.

Everything is stored locally (no accounts, no cloud).  The data directory can
be overridden with the ``ETIKNIVO_DATA_DIR`` environment variable, which the
test-suite uses to stay isolated from the user's real library.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import platformdirs

from etiknivo.storage.atomic import atomic_write_text

log = logging.getLogger(__name__)

APP_DIR_NAME = "Etiknivo"


def data_dir() -> Path:
    """Directory holding the library, settings and backups."""
    override = os.environ.get("ETIKNIVO_DATA_DIR")
    path = Path(override) if override else Path(platformdirs.user_data_dir(APP_DIR_NAME, False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    """Directory holding the application and print logs."""
    override = os.environ.get("ETIKNIVO_DATA_DIR")
    path = Path(override) / "logs" if override else Path(platformdirs.user_log_dir(APP_DIR_NAME, False))
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Calibration:
    """Printer-specific corrections applied by the render engine.

    ``offset_feed_px``  shifts the image along the roll (label length);
    ``offset_head_px``  shifts it across the 96-pixel printhead.
    Positive values move content right/down in the design orientation.
    """

    offset_feed_px: int = 0
    offset_head_px: int = 0
    threshold: int = 140  # 0-255; grey values below become black dots
    rotate_clockwise: bool = False  # flip print orientation if labels come out upside down
    supersample: int = 4

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Calibration:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Settings:
    printer_model: str = "fichero_5836"
    printer_address: str = ""
    #: Label roll in the printer as [length, height] in mm; empty = the model's default.
    label_size_mm: list[float] = field(default_factory=list)
    density: int = 1  # 0=licht, 1=normaal, 2=donker
    default_copies: int = 1
    use_mock_printer: bool = False
    zoom: float = 14.0  # screen pixels per millimetre
    show_printable_area: bool = True
    show_native_raster: bool = False
    group_by_category: bool = True
    sort_key: str = "tray_id"
    theme: str = "system"  # system, light or dark
    language: str = "system"  # system, nl or en (applied at start-up)
    calibration: Calibration = field(default_factory=Calibration)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known and k != "calibration"}
        s = cls(**kwargs)
        s.calibration = Calibration.from_dict(data.get("calibration", {}))
        return s

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def settings_path() -> Path:
    return data_dir() / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or settings_path()
    if not path.exists():
        return Settings()
    try:
        return Settings.from_dict(json.loads(path.read_text("utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        log.warning("Instellingen konden niet worden gelezen (%s); standaardwaarden gebruikt", exc)
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    atomic_write_text(path or settings_path(), json.dumps(settings.to_dict(), indent=2, ensure_ascii=False))
