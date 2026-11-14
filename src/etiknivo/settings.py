"""Application settings and local file locations.

Everything is stored locally (no accounts, no cloud).  The data directory can
be overridden with the ``ETIKNIVO_DATA_DIR`` environment variable, which the
test-suite uses to stay isolated from the user's real library.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import platformdirs

from etiknivo.i18n import tr
from etiknivo.model import as_bool, as_dict, as_float, as_str
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
    def from_dict(cls, data: Any) -> Calibration:
        """Calibration from settings.json; wrong or out-of-range values get the
        default (the ranges are those of the calibration dialog)."""
        data, d = as_dict(data), cls()
        return cls(
            offset_feed_px=int(as_float(data.get("offset_feed_px"), d.offset_feed_px, -40, 40)),
            offset_head_px=int(as_float(data.get("offset_head_px"), d.offset_head_px, -16, 16)),
            threshold=int(as_float(data.get("threshold"), d.threshold, 1, 255)),
            rotate_clockwise=as_bool(data.get("rotate_clockwise"), d.rotate_clockwise),
            supersample=int(as_float(data.get("supersample"), d.supersample, 1, 8)),
        )


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
    theme: str = "system"  # system, light, dark, paper, night or contrast
    accent: str = "default"  # default (the theme's own), blue, green, orange or purple
    language: str = "system"  # system, nl or en (applied at start-up)
    check_updates: bool = False  # look for a new version on GitHub at start-up
    last_update_check: str = ""  # ISO date; the automatic check runs once a day
    calibration: Calibration = field(default_factory=Calibration)

    @classmethod
    def from_dict(cls, data: Any) -> Settings:
        """Settings from settings.json.  Every field is checked on its own: a
        value of the wrong type falls back to the default, so one bad value
        never costs the other settings (or the start of the app)."""
        data, d = as_dict(data), cls()
        size = data.get("label_size_mm")
        if not (isinstance(size, list) and len(size) == 2
                and all(as_float(v, -1.0) > 0 for v in size)):
            size = []
        s = cls(
            printer_model=as_str(data.get("printer_model"), d.printer_model) or d.printer_model,
            printer_address=as_str(data.get("printer_address"), d.printer_address),
            label_size_mm=[as_float(v, 0.0) for v in size],
            density=int(as_float(data.get("density"), d.density, 0, 2)),
            default_copies=int(as_float(data.get("default_copies"), d.default_copies, 1, 99)),
            use_mock_printer=as_bool(data.get("use_mock_printer"), d.use_mock_printer),
            zoom=as_float(data.get("zoom"), d.zoom, 6, 40),
            show_printable_area=as_bool(data.get("show_printable_area"), d.show_printable_area),
            show_native_raster=as_bool(data.get("show_native_raster"), d.show_native_raster),
            group_by_category=as_bool(data.get("group_by_category"), d.group_by_category),
            sort_key=as_str(data.get("sort_key"), d.sort_key) or d.sort_key,
            theme=as_str(data.get("theme"), d.theme) or d.theme,
            accent=as_str(data.get("accent"), d.accent) or d.accent,
            language=as_str(data.get("language"), d.language) or d.language,
            check_updates=as_bool(data.get("check_updates"), d.check_updates),
            last_update_check=as_str(data.get("last_update_check"), d.last_update_check),
        )
        s.calibration = Calibration.from_dict(data.get("calibration"))
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
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        log.warning(tr("Instellingen konden niet worden gelezen (%s); standaardwaarden gebruikt"), exc)
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    atomic_write_text(path or settings_path(), json.dumps(settings.to_dict(), indent=2, ensure_ascii=False))
