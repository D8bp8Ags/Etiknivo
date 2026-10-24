"""GUI smoke tests (offscreen Qt, simulated printer)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from etiknivo.gui import main_window as mw
from etiknivo.gui.dialogs import PrintPreviewDialog
from etiknivo.model import LayoutPreset
from etiknivo.printing.mock import MockPrinterBackend
from etiknivo.printing.queue import JobStatus
from etiknivo.settings import Settings, data_dir
from etiknivo.storage.library import Library, open_library


@pytest.fixture
def window(qtbot, monkeypatch):  # noqa: ANN001, ANN201
    lib, _ = open_library(data_dir() / "library.json")
    backend = MockPrinterBackend()
    win = mw.MainWindow(lib, Settings(use_mock_printer=True), backend, poll_interval=3600)
    qtbot.addWidget(win)
    win.show()
    monkeypatch.setattr(PrintPreviewDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    yield win
    win.close()


def connect(qtbot, win) -> None:  # noqa: ANN001
    win._connect("")
    qtbot.waitUntil(lambda: win.bridge.state.connection == "connected", timeout=5000)


def test_window_starts_with_seed_library(window) -> None:  # noqa: ANN001
    assert window.windowTitle() == "Etiknivo"
    assert len(window.library_panel.visible_ids()) == 23
    assert window.current is not None
    assert window.raster_view.result.raster.size == (96, 240)


def test_editing_updates_label_preview_and_autosaves(qtbot, window) -> None:  # noqa: ANN001
    lbl = window.current
    editor = window.properties.lines[1]
    editor.text.setText("Nieuwe tekst Ω")
    editor.text.textEdited.emit("Nieuwe tekst Ω")
    assert lbl.main.text == "Nieuwe tekst Ω"
    qtbot.waitUntil(lambda: window.design_view.result.lines[1].text == "Nieuwe tekst Ω",
                    timeout=2000)
    qtbot.waitUntil(lambda: "Nieuwe tekst Ω" in (data_dir() / "library.json").read_text("utf-8"),
                    timeout=3000)
    reloaded = Library(data_dir() / "library.json")
    reloaded.load()
    assert reloaded.get(lbl.id).main.text == "Nieuwe tekst Ω"


def test_layout_switch_in_gui_keeps_text(window) -> None:  # noqa: ANN001
    lbl = window.current
    texts = [ln.text for ln in lbl.lines]
    combo = window.properties.layout_combo
    for preset in (LayoutPreset.SINGLE, LayoutPreset.MAIN_SPEC, LayoutPreset.CATEGORY_MAIN_SPEC):
        combo.setCurrentIndex(combo.findData(preset))
        combo.activated.emit(combo.currentIndex())
        assert lbl.layout == preset
        assert [ln.text for ln in lbl.lines] == texts
    assert len(window.design_view.result.lines) == 3


def test_new_duplicate_delete(window) -> None:  # noqa: ANN001
    n = len(window.library)
    window.new_label()
    assert len(window.library) == n + 1 and window.current.name == "Nieuw label"
    window.duplicate_label()
    assert len(window.library) == n + 2 and window.current.name.endswith("(kopie)")
    window.delete_labels()
    assert len(window.library) == n + 1


def test_search_and_category_filter(window) -> None:  # noqa: ANN001
    lp = window.library_panel
    lp.search.setText("esp32")
    assert len(lp.visible_ids()) == 3
    lp.search.setText("")
    lp.category.setCurrentIndex(lp.category.findText("Dupont"))
    assert len(lp.visible_ids()) == 3
    lp.group.setChecked(False)
    lp.category.setCurrentIndex(0)
    assert len(lp.visible_ids()) == 23


def test_print_current_with_simulated_printer(qtbot, window) -> None:  # noqa: ANN001
    connect(qtbot, window)
    backend = window.bridge.manager.backend
    window.print_current()
    window.print_current()  # accidental double click → ignored
    qtbot.waitUntil(lambda: len(backend.printed) == 1, timeout=5000)
    qtbot.wait(300)
    assert len(backend.printed) == 1
    expected = window.engine.render(window.current).raster_bytes()
    assert backend.printed[0].raster == expected
    qtbot.waitUntil(lambda: window.queue_panel.table.rowCount() == 1, timeout=2000)
    assert window.queue_panel.table.item(0, 3).text() == "Klaar"


def test_print_category_and_error_recovery(qtbot, window, monkeypatch) -> None:  # noqa: ANN001
    connect(qtbot, window)
    backend = window.bridge.manager.backend
    backend.fail_after_labels = 1
    monkeypatch.setattr(mw.QInputDialog, "getItem",
                        staticmethod(lambda *a, **k: ("ESP32-S3", True)))
    window.print_category()
    qtbot.waitUntil(lambda: window.bridge.queue_snapshot().failed == 1, timeout=5000)
    snap = window.bridge.queue_snapshot()
    assert [j.status for j in snap.jobs] == [JobStatus.DONE, JobStatus.FAILED, JobStatus.PENDING]
    assert window.queue_panel.retry_btn.isEnabled()
    backend.fail_after_labels = None
    window.queue_panel.retry_btn.click()
    qtbot.waitUntil(lambda: len(backend.printed) == 3, timeout=5000)


def test_printing_requires_connection(window, monkeypatch) -> None:  # noqa: ANN001
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a)))
    window.print_test_label()
    assert warned


def test_editor_works_without_printer(window) -> None:  # noqa: ANN001
    # no connection at all, everything except printing must work
    window.new_label()
    window.properties.lines[1].text.setText("Zonder printer")
    window.properties.lines[1].text.textEdited.emit("Zonder printer")
    window.update_preview()
    assert window.raster_view.result is not None
