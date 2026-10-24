"""Undo/redo for the label library.

The library is small (tens to a few hundred labels), so every step stores a
complete snapshot instead of individual commands.  That keeps undo correct
for every kind of change (editing, new, duplicate, delete, import) without
each action having to know how to reverse itself.

Rapid edits to the same label (typing, spinning a size) are merged into one
step, so Ctrl+Z undoes a word or a setting, not a single character.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from etiknivo.model import Label
from etiknivo.storage.library import labels_from_document, labels_to_document

MERGE_SECONDS = 1.2
MAX_STEPS = 200


@dataclass(frozen=True)
class Snapshot:
    labels_json: str
    selection: tuple[str, ...]
    draft_json: str = ""  # unsaved edits of the open label ("" when there are none)

    @classmethod
    def take(cls, labels: list[Label], selection: list[str],
             draft: Label | None = None) -> Snapshot:
        doc = labels_to_document(labels)
        draft_json = json.dumps(draft.to_dict(), ensure_ascii=False, sort_keys=True) \
            if draft is not None else ""
        return cls(json.dumps(doc, ensure_ascii=False, sort_keys=True), tuple(selection),
                   draft_json)

    def labels(self) -> list[Label]:
        return labels_from_document(json.loads(self.labels_json))

    def draft(self) -> Label | None:
        return Label.from_dict(json.loads(self.draft_json)) if self.draft_json else None

    def same_content(self, other: Snapshot) -> bool:
        return (self.labels_json, self.draft_json) == (other.labels_json, other.draft_json)


class History:
    """Linear undo/redo stack of library snapshots (plus the unsaved draft)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._undo: list[Snapshot] = []
        self._redo: list[Snapshot] = []
        self._current: Snapshot | None = None
        self._merge_key: str | None = None
        self._merge_time = 0.0

    def reset(self, state: Snapshot) -> None:
        """Start over from *state* (e.g. after loading a back-up)."""
        self._undo.clear()
        self._redo.clear()
        self._current = state
        self._merge_key = None

    def record(self, state: Snapshot, merge_key: str | None = None) -> None:
        """Register *state* as the result of a change.

        Consecutive changes with the same *merge_key* within
        :data:`MERGE_SECONDS` form one undo step."""
        if self._current is None:
            self._current = state
            return
        if state.same_content(self._current):
            self._current = state  # selection only: not an undoable change
            return
        now = self._clock()
        merge = (merge_key is not None and merge_key == self._merge_key
                 and now - self._merge_time < MERGE_SECONDS and bool(self._undo))
        if not merge:
            self._undo.append(self._current)
            del self._undo[:-MAX_STEPS]
        self._redo.clear()
        self._current = state
        self._merge_key = merge_key
        self._merge_time = now

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> Snapshot | None:
        if not self._undo or self._current is None:
            return None
        self._redo.append(self._current)
        self._current = self._undo.pop()
        self._merge_key = None
        return self._current

    def redo(self) -> Snapshot | None:
        if not self._redo or self._current is None:
            return None
        self._undo.append(self._current)
        self._current = self._redo.pop()
        self._merge_key = None
        return self._current
