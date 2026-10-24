"""Application and print logging to local files."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from etiknivo.settings import log_dir


def setup_logging(level: int = logging.INFO) -> Path:
    """Configure ``app.log`` (everything) and ``print.log`` (print results only).
    Returns the log directory."""
    directory = log_dir()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(h, "_etiknivo", False) for h in root.handlers):
        app = RotatingFileHandler(directory / "app.log", maxBytes=1_000_000, backupCount=3,
                                  encoding="utf-8")
        app.setFormatter(fmt)
        app._etiknivo = True  # type: ignore[attr-defined]
        root.addHandler(app)
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console.setLevel(logging.WARNING)
        console._etiknivo = True  # type: ignore[attr-defined]
        root.addHandler(console)

        plog = logging.getLogger("etiknivo.printlog")
        ph = RotatingFileHandler(directory / "print.log", maxBytes=1_000_000, backupCount=5,
                                 encoding="utf-8")
        ph.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
        plog.addHandler(ph)
        plog.setLevel(logging.INFO)
    return directory
