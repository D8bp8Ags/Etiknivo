"""Print history: records of finished jobs and printing them again."""

from __future__ import annotations

import json

from etiknivo.gui.history_window import HistoryWindow
from etiknivo.settings import data_dir
from etiknivo.storage import print_history as ph
from etiknivo.storage.print_history import PrintHistory, PrintRecord
from tests.test_gui import connect, window  # noqa: F401 - fixture


def test_history_is_saved_and_trimmed(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(ph, "MAX_RECORDS", 3)
    h = PrintHistory(tmp_path / "h.json")
    for n in range(5):
        h.add(PrintRecord.now(f"id{n}", f"A{n} Label", 2, 1))
    again = PrintHistory(tmp_path / "h.json")
    assert [r.label_id for r in again.newest_first()] == ["id4", "id3", "id2"]
    assert again.records[0].copies == 2


def test_broken_history_file_is_skipped(tmp_path) -> None:  # noqa: ANN001
    p = tmp_path / "h.json"
    good = PrintRecord.now("x", "X", 1, 0)
    p.write_text(json.dumps({"records": [{"time": "nonsense"}, good.__dict__]}))
    assert PrintHistory(p).records == [good]
    p.write_text("{not json")
    assert PrintHistory(p).records == []


def test_printing_adds_history_and_reprint(qtbot, window, monkeypatch) -> None:  # noqa: ANN001, F811
    connect(qtbot, window)
    backend = window.bridge.manager.backend
    lbl = window.current
    window.print_current()
    qtbot.waitUntil(lambda: len(window.print_history.records) == 1, timeout=5000)
    rec = window.print_history.records[0]
    assert rec.label_id == lbl.id and rec.simulated and rec.copies == 1
    assert PrintHistory(data_dir() / ph.FILE_NAME).records == [rec]

    # test labels are not part of the history
    window._last_print = 0
    window.print_test_label()
    qtbot.waitUntil(lambda: len(backend.printed) == 2, timeout=5000)
    qtbot.wait(200)
    assert len(window.print_history.records) == 1

    window.show_print_history()
    w = window._history_window
    assert isinstance(w, HistoryWindow) and w.tree.topLevelItemCount() == 1
    assert not w.reprint_btn.isEnabled()
    w.tree.topLevelItem(0).setSelected(True)
    assert w.reprint_btn.isEnabled()
    seen = {}
    monkeypatch.setattr(type(window), "print_labels",
                        lambda self, labels, copies=None, density=None:
                        seen.update(ids=[x.id for x in labels], copies=copies, density=density))
    w.reprint()
    assert seen == {"ids": [lbl.id], "copies": [1], "density": rec.density}

    w.search.setText("zzz-geen-treffer")
    assert w.tree.topLevelItemCount() == 0
    w.search.clear()
    w.hide_sim.setChecked(True)
    assert w.tree.topLevelItemCount() == 0


def test_deleted_label_cannot_be_reprinted(qtbot, window) -> None:  # noqa: ANN001, F811
    window.print_history.add(PrintRecord.now("weg", "Z9 Verdwenen", 1, 0))
    window.show_print_history()
    w = window._history_window
    item = w.tree.topLevelItem(0)
    assert "verwijderd" in item.text(1)
    item.setSelected(True)
    assert w.selected() == [] and not w.reprint_btn.isEnabled()
    w.ask_clear()  # QMessageBox.question is answered Yes by the fixture
    assert window.print_history.records == [] and w.tree.topLevelItemCount() == 0
