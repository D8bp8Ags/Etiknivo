"""Label library persistence (local JSON file).

The library file is a small, human-editable JSON document::

    {"app": "Etiknivo", "schema": 1, "labels": [ {...}, ... ]}

Writes are atomic and the previous version is kept as ``library.json.bak``.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Iterable, Iterator
from importlib import resources
from pathlib import Path
from typing import Any

from etiknivo.i18n import tr
from etiknivo.model import SCHEMA_VERSION, Label
from etiknivo.storage.atomic import atomic_write_text

log = logging.getLogger(__name__)


class LibraryError(Exception):
    """Raised when a library file cannot be read or is invalid."""


def labels_to_document(labels: Iterable[Label]) -> dict[str, Any]:
    return {"app": "Etiknivo", "schema": SCHEMA_VERSION, "labels": [lbl.to_dict() for lbl in labels]}


def labels_from_document(doc: Any) -> list[Label]:
    """Parse a library document.  Accepts the full document or a bare list."""
    if isinstance(doc, dict):
        items = doc.get("labels")
    else:
        items = doc
    if not isinstance(items, list):
        raise LibraryError(tr("Ongeldig bibliotheekbestand: lijst 'labels' ontbreekt"))
    labels: list[Label] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise LibraryError(tr("Ongeldig label op positie {n}", n=i))
        try:
            labels.append(Label.from_dict(item))
        except (ValueError, TypeError, KeyError) as exc:
            raise LibraryError(tr("Ongeldig label op positie {n}: {error}", n=i, error=exc)) from exc
    return labels


class Library:
    """In-memory label collection backed by a JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._labels: list[Label] = []

    # -- collection API --------------------------------------------------------

    def __iter__(self) -> Iterator[Label]:
        return iter(self._labels)

    def __len__(self) -> int:
        return len(self._labels)

    @property
    def labels(self) -> list[Label]:
        return list(self._labels)

    def get(self, label_id: str) -> Label | None:
        return next((lbl for lbl in self._labels if lbl.id == label_id), None)

    def add(self, label: Label) -> Label:
        if self.get(label.id) is not None:
            label = label.clone()
        self._labels.append(label)
        return label

    def update(self, label: Label) -> bool:
        """Replace the stored label with the same id.  Returns False if absent."""
        for i, lbl in enumerate(self._labels):
            if lbl.id == label.id:
                self._labels[i] = label
                return True
        return False

    def remove(self, label_ids: Iterable[str]) -> int:
        ids = set(label_ids)
        before = len(self._labels)
        self._labels = [lbl for lbl in self._labels if lbl.id not in ids]
        return before - len(self._labels)

    def duplicate(self, label_id: str) -> Label | None:
        src = self.get(label_id)
        if src is None:
            return None
        dup = src.clone()
        dup.name = tr("{name} (kopie)", name=src.name)
        idx = self._labels.index(src)
        self._labels.insert(idx + 1, dup)
        return dup

    def replace_all(self, labels: Iterable[Label]) -> None:
        self._labels = list(labels)

    def merge(self, labels: Iterable[Label]) -> tuple[int, int]:
        """Merge imported labels: same id → update, otherwise add.
        Returns (added, updated)."""
        added = updated = 0
        for new in labels:
            existing = self.get(new.id)
            if existing is None:
                self._labels.append(new)
                added += 1
            else:
                self._labels[self._labels.index(existing)] = new
                updated += 1
        return added, updated

    def categories(self) -> list[str]:
        return sorted({lbl.category for lbl in self._labels if lbl.category}, key=str.casefold)

    def by_category(self, category: str) -> list[Label]:
        return [lbl for lbl in self._labels if lbl.category == category]

    # -- persistence -----------------------------------------------------------

    def load(self) -> None:
        try:
            doc = json.loads(self.path.read_text("utf-8"))
        except FileNotFoundError:
            self._labels = []
            return
        except (OSError, ValueError) as exc:
            raise LibraryError(tr("Bibliotheek kon niet worden gelezen: {error}", error=exc)) from exc
        self._labels = labels_from_document(doc)

    def save(self) -> None:
        if self.path.exists():
            try:
                shutil.copy2(self.path, self.path.with_suffix(self.path.suffix + ".bak"))
            except OSError as exc:  # a failed backup copy must not block saving
                log.warning("Back-up van bibliotheek mislukt: %s", exc)
        text = json.dumps(labels_to_document(self._labels), indent=2, ensure_ascii=False)
        atomic_write_text(self.path, text)


def seed_labels() -> list[Label]:
    """The bundled Raaco electronics sample library (23 labels)."""
    from etiknivo.storage.io import parse_csv_labels

    text = resources.files("etiknivo.data").joinpath("raaco_seed.csv").read_text("utf-8")
    labels, errors = parse_csv_labels(text)
    if errors:  # pragma: no cover - bundled data is validated by tests
        raise LibraryError("; ".join(errors))
    return labels


def open_library(path: Path) -> tuple[Library, bool]:
    """Load the library at *path*, seeding it with the sample labels on first
    start.  Returns ``(library, seeded)``."""
    lib = Library(path)
    if path.exists():
        lib.load()
        return lib, False
    lib.replace_all(seed_labels())
    lib.save()
    return lib, True
