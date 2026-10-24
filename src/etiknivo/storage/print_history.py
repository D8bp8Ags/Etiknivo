"""Print history: which labels were printed, when, and how many.

Every finished print job adds one record to ``print_history.json`` in the
data directory.  Only the newest :data:`MAX_RECORDS` are kept.  A record
points at the label by id, so a reprint uses the label as it is now; the
title is stored too, so deleted labels still show up readably.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from etiknivo.storage.atomic import atomic_write_text

log = logging.getLogger(__name__)

MAX_RECORDS = 1000
FILE_NAME = "print_history.json"


@dataclass(frozen=True)
class PrintRecord:
    time: str  # ISO 8601, local time, seconds
    label_id: str
    title: str
    copies: int
    density: int
    simulated: bool = False

    @classmethod
    def now(cls, label_id: str, title: str, copies: int, density: int,
            simulated: bool = False) -> PrintRecord:
        return cls(datetime.now().isoformat(timespec="seconds"), label_id, title, copies,
                   density, simulated)

    @property
    def when(self) -> datetime:
        return datetime.fromisoformat(self.time)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrintRecord:
        known = {f.name for f in fields(cls)}
        rec = cls(**{k: v for k, v in data.items() if k in known})
        rec.when  # noqa: B018 - validates the time stamp
        return rec


class PrintHistory:
    """The records, oldest first, saved after every change."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.records: list[PrintRecord] = []
        self.load()

    def load(self) -> None:
        self.records = []
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for item in data.get("records", []):
                try:
                    self.records.append(PrintRecord.from_dict(item))
                except (TypeError, ValueError):
                    log.warning("Ongeldige regel in afdrukgeschiedenis overgeslagen: %r", item)
        except (OSError, ValueError, AttributeError):
            log.exception("Afdrukgeschiedenis kon niet worden gelezen: %s", self.path)

    def save(self) -> None:
        doc = {"version": 1, "records": [asdict(r) for r in self.records]}
        try:
            atomic_write_text(self.path, json.dumps(doc, ensure_ascii=False, indent=1))
        except OSError:
            log.exception("Afdrukgeschiedenis kon niet worden opgeslagen: %s", self.path)

    def add(self, record: PrintRecord) -> None:
        self.records.append(record)
        del self.records[:-MAX_RECORDS]
        self.save()

    def clear(self) -> None:
        self.records = []
        self.save()

    def newest_first(self) -> list[PrintRecord]:
        return self.records[::-1]
