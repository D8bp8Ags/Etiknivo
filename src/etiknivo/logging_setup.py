"""Application and print logging: local files plus an in-memory copy for the
log window in the app."""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from etiknivo.settings import log_dir

PRINT_LOGGER = "etiknivo.printlog"


@dataclass(frozen=True)
class LogEntry:
    time: datetime
    level: int
    name: str
    message: str

    @property
    def is_print(self) -> bool:
        return self.name == PRINT_LOGGER

    def format(self) -> str:
        return (f"{self.time:%H:%M:%S}  {logging.getLevelName(self.level):<7}  "
                f"{self.name.removeprefix('etiknivo.')}: {self.message}")


class MemoryLog(logging.Handler):
    """Keeps the most recent log records for the log window.  Listeners are
    called from the thread that logged (the GUI hops to its own thread)."""

    def __init__(self, capacity: int = 2000) -> None:
        super().__init__(logging.DEBUG)
        self.entries: deque[LogEntry] = deque(maxlen=capacity)
        self.listeners: list[Callable[[LogEntry], None]] = []
        self._guard = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if record.exc_info and record.exc_info[0] is not None:
                msg += "\n" + logging.Formatter().formatException(record.exc_info)
        except Exception:  # noqa: BLE001 - a broken log call must not crash the app
            msg = str(record.msg)
        entry = LogEntry(datetime.fromtimestamp(record.created), record.levelno, record.name, msg)
        with self._guard:
            self.entries.append(entry)
            listeners = list(self.listeners)
        for fn in listeners:
            try:
                fn(entry)
            except Exception:  # noqa: BLE001, S110
                pass

    def snapshot(self) -> list[LogEntry]:
        with self._guard:
            return list(self.entries)

    def clear(self) -> None:
        with self._guard:
            self.entries.clear()


_memory: MemoryLog | None = None


def memory_log() -> MemoryLog:
    """The in-memory log, attached to the root logger on first use."""
    global _memory
    if _memory is None:
        _memory = MemoryLog()
        logging.getLogger().addHandler(_memory)
    return _memory


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

        plog = logging.getLogger(PRINT_LOGGER)
        ph = RotatingFileHandler(directory / "print.log", maxBytes=1_000_000, backupCount=5,
                                 encoding="utf-8")
        ph.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
        plog.addHandler(ph)
        plog.setLevel(logging.INFO)
    memory_log()
    return directory
