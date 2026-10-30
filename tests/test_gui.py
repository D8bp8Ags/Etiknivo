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
    monkeypatch.setattr(mw.MainWindow, "_ask_unsaved", lambda self, lbl: "discard")
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
    assert window.windowTitle() == "Etiknivo[*]" and not window.isWindowModified()
    assert len(window.library_panel.visible_ids()) == 23
    assert window.current is not None
    assert window.raster_view.result.raster.size == (96, 240)


def edit_main(window, text: str) -> None:  # noqa: ANN001
    editor = window.properties.lines[1]
    editor.text.setText(text)
    editor.text.textEdited.emit(text)


def test_edits_are_a_draft_until_saved(qtbot, window) -> None:  # noqa: ANN001
    lbl = window.current
    path = data_dir() / "library.json"
    edit_main(window, "Nieuwe tekst Ω")
    assert lbl.main.text == "Nieuwe tekst Ω"
    qtbot.waitUntil(lambda: window.design_view.result.lines[1].text == "Nieuwe tekst Ω",
                    timeout=2000)
    assert window.is_dirty() and window.isWindowModified() and window.save_btn.isEnabled()
    assert window.library.get(lbl.id).main.text != "Nieuwe tekst Ω"  # list/library untouched
    qtbot.wait(800)  # longer than the old autosave delay
    assert "Nieuwe tekst Ω" not in path.read_text("utf-8")
    window.save_current()
    assert not window.is_dirty() and not window.save_btn.isEnabled()
    reloaded = Library(path)
    reloaded.load()
    assert reloaded.get(lbl.id).main.text == "Nieuwe tekst Ω"


def test_revert_restores_saved_label(window) -> None:  # noqa: ANN001
    before = window.current.main.text
    edit_main(window, "Weg ermee")
    window.revert_current()
    assert window.current.main.text == before and not window.is_dirty()
    assert window.properties.lines[1].text.text() == before


def test_switching_with_unsaved_changes_asks(window, monkeypatch) -> None:  # noqa: ANN001
    lp = window.library_panel
    first, second = lp.visible_ids()[:2]
    edit_main(window, "Concept")
    monkeypatch.setattr(mw.MainWindow, "_ask_unsaved", lambda self, lbl: "cancel")
    lp.select_ids([second])
    assert window.current.id == first and window.current.main.text == "Concept"
    assert lp.selected_ids() == [first]
    monkeypatch.setattr(mw.MainWindow, "_ask_unsaved", lambda self, lbl: "discard")
    lp.select_ids([second])
    assert window.current.id == second
    assert window.library.get(first).main.text != "Concept"
    edit_main(window, "Bewaard")
    monkeypatch.setattr(mw.MainWindow, "_ask_unsaved", lambda self, lbl: "save")
    lp.select_ids([first])
    assert window.current.id == first and window.library.get(second).main.text == "Bewaard"


def test_print_uses_the_draft(window) -> None:  # noqa: ANN001
    edit_main(window, "Ongesaved")
    sel = window._selected_in_view_order()
    assert sel[0] is window.current and sel[0].main.text == "Ongesaved"


def test_line_count_buttons_keep_text_and_style(window) -> None:  # noqa: ANN001
    lbl = window.current
    lbl.main.font_size_pt, lbl.main.italic = 11.0, True
    texts = [ln.text for ln in lbl.lines]
    buttons = window.properties.count_buttons
    for count, preset in ((1, LayoutPreset.SINGLE), (2, LayoutPreset.MAIN_SPEC),
                          (3, LayoutPreset.CATEGORY_MAIN_SPEC)):
        buttons[count - 1].click()
        assert lbl.layout == preset and lbl.line_count() == count
        assert [b.isChecked() for b in buttons] == [n == count for n in (1, 2, 3)]
        assert [ln.text for ln in lbl.lines] == texts
        assert lbl.main.font_size_pt == 11.0 and lbl.main.italic  # the look stays
    assert len(window.design_view.result.lines) == 3
    window.properties.lines[0].setChecked(False)  # a line turned off by hand
    assert [b.isChecked() for b in buttons] == [False, True, False]


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
    qtbot.waitUntil(window.queue_panel.retry_btn.isEnabled, timeout=2000)
    backend.fail_after_labels = None
    window.queue_panel.retry_btn.click()
    qtbot.waitUntil(lambda: len(backend.printed) == 3, timeout=5000)


def test_printing_requires_connection(qtbot, window, monkeypatch) -> None:  # noqa: ANN001
    qtbot.waitUntil(lambda: window.bridge.state.connection == "connected", timeout=5000)
    window._disconnect()
    qtbot.waitUntil(lambda: window.bridge.state.connection == "disconnected", timeout=5000)
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


def test_theme_switch_and_icons(window) -> None:  # noqa: ANN001
    from importlib import resources

    from etiknivo.gui import theme

    window.set_theme("dark")
    assert theme.tokens().dark and window.settings.theme == "dark"
    window.set_theme("light")
    assert not theme.tokens().dark
    names = [p.name[:-4] for p in resources.files("etiknivo.gui.icons").iterdir()
             if p.name.endswith(".svg")]
    assert names and all(not theme.icon(n).isNull() for n in names)


def test_new_label_follows_category_change_without_losing_focus(window) -> None:  # noqa: ANN001
    lp = window.library_panel
    lp.category.setCurrentIndex(lp.category.findText("Dupont"))
    window.new_label()
    lbl = window.current
    assert lbl.category == "Dupont" and lbl.id in lp.visible_ids()
    combo = window.properties.category
    combo.setEditText("Aud")  # half typed: nothing happens yet
    assert lbl.category == "Dupont" and lp.category.currentText() == "Dupont"
    combo.setEditText("Audio")
    combo.lineEdit().editingFinished.emit()
    assert lbl.category == "Audio"
    assert lp.category.currentText() == "Dupont"  # still a draft: list unchanged
    window.save_current()
    assert lp.category.currentText() == "Audio"  # the filter followed the label
    assert window.current is lbl and lp.selected_ids() == [lbl.id]
    assert window.properties.isEnabled()


def test_edited_label_stays_visible_during_search(window) -> None:  # noqa: ANN001
    lp = window.library_panel
    lp.search.setText("esp32")
    window.new_label()  # "Nieuw label" does not match the search
    lbl = window.current
    assert lbl.id in lp.visible_ids()
    lp.search.setText("esp3")  # refresh while still editing
    assert lbl.id in lp.visible_ids() and window.current is lbl
    lp.select_ids([lp.visible_ids()[0] if lp.visible_ids()[0] != lbl.id else lp.visible_ids()[1]])
    lp.search.setText("esp32")
    assert lbl.id not in lp.visible_ids()  # unpinned once another label is chosen


def test_undo_redo_edits_and_delete(qtbot, window) -> None:  # noqa: ANN001
    lbl_id = window.current.id
    before = window.current.main.text
    editor = window.properties.lines[1]
    editor.text.setText("Gewijzigd")
    editor.text.textEdited.emit("Gewijzigd")
    assert window.act_undo.isEnabled()
    window.undo()
    assert window.current.id == lbl_id and window.current.main.text == before
    assert window.properties.lines[1].text.text() == before
    window.redo()
    assert window.current.main.text == "Gewijzigd"
    n = len(window.library)
    window.delete_labels()
    assert len(window.library) == n - 1
    window.undo()
    assert len(window.library) == n and window.current.id == lbl_id


def test_ctrl_z_in_text_field_uses_app_undo(qtbot, window) -> None:  # noqa: ANN001
    from PySide6.QtCore import Qt

    window.activateWindow()
    field = window.properties.lines[1].text
    before = window.current.main.text
    field.setFocus()
    qtbot.waitUntil(field.hasFocus, timeout=2000)
    qtbot.keyClicks(field, "XYZ")
    assert window.current.main.text.endswith("XYZ")
    qtbot.keyClick(field, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.current.main.text == before and field.text() == before


def test_simulated_printer_connects_by_itself(qtbot, window) -> None:  # noqa: ANN001
    qtbot.waitUntil(lambda: window.bridge.state.connection == "connected", timeout=5000)
    window._disconnect()
    qtbot.waitUntil(lambda: window.bridge.state.connection == "disconnected", timeout=5000)
    window.set_mock(True)  # switching simulation on connects without an extra click
    qtbot.waitUntil(lambda: window.bridge.state.connection == "connected", timeout=5000)


def test_insert_field_from_specifications(qtbot, window) -> None:  # noqa: ANN001
    props = window.properties
    props.specs.set_specs({"Spanning": "12 V"})
    props.specs.changed.emit()
    le = props.lines[2]
    le.text.setText("")
    le.insert_field("Spanning")
    assert window.current.bottom.text == "{Spanning}"
    qtbot.waitUntil(lambda: any(lb.text == "12 V" for lb in window.design_view.result.lines),
                    timeout=2000)
    assert "Spanning" in le.fields()


def test_app_icon_and_about(window) -> None:  # noqa: ANN001
    from etiknivo.gui import theme
    from etiknivo.gui.dialogs import AboutDialog
    from etiknivo.settings import log_dir

    assert not theme.app_icon().isNull()
    dlg = AboutDialog(window.profile, data_dir(), log_dir(), window)
    info = dlg.system_info()
    assert "Etiknivo" in info and "Python" in info and window.profile.key in info
    dlg.close()


def test_log_window_shows_live_log_with_filters(qtbot, window) -> None:  # noqa: ANN001
    import logging

    from etiknivo.logging_setup import PRINT_LOGGER

    window.show_log()
    lw = window._log_window
    assert lw is not None and lw.isVisible()
    logging.getLogger("etiknivo.test").warning("Iets is mis %d", 42)
    logging.getLogger(PRINT_LOGGER).warning("OK      A01 ×1")
    qtbot.waitUntil(lambda: "Iets is mis 42" in lw.view.toPlainText(), timeout=2000)
    lw.filter.setCurrentIndex(lw.filter.findData("print"))
    assert "A01" in lw.visible_text() and "Iets is mis" not in lw.visible_text()
    lw.filter.setCurrentIndex(lw.filter.findData("all"))
    lw.search.setText("mis 42")
    assert lw.visible_text().count("\n") == 0 and "Iets is mis 42" in lw.visible_text()
    lw.close()


def test_menus_have_no_duplicates_and_mac_roles(window) -> None:  # noqa: ANN001
    from PySide6.QtGui import QAction

    def items(menu):  # noqa: ANN001, ANN202
        for a in menu.actions():
            if a.menu():
                yield from items(a.menu())
            elif not a.isSeparator():
                yield a

    def paths(menu, prefix=""):  # noqa: ANN001, ANN202
        for a in menu.actions():
            if a.menu():
                yield from paths(a.menu(), prefix + a.text() + "/")
            elif not a.isSeparator() and not a.actionGroup():
                yield prefix + a.text()

    menus = {a.text().replace("&", ""): list(items(a.menu()))
             for a in window.menuBar().actions()}
    texts = [p for a in window.menuBar().actions() for p in paths(a.menu())]
    leaves = [t.rsplit("/", 1)[-1] for t in texts if "/" not in t]
    assert len(leaves) == len(set(leaves)), "elk menu-item maar één keer"
    assert "Importeren/Bibliotheek (JSON)…" in texts and "Exporteren/Bibliotheek (JSON)…" in texts
    assert "Testlabel afdrukken" in [a.text() for a in menus["Printer"]]
    assert "Testlabel afdrukken" not in [a.text() for a in menus["Afdrukken"]]
    roles = {a.text(): a.menuRole() for acts in menus.values() for a in acts}
    assert roles["Afsluiten"] == QAction.MenuRole.QuitRole
    assert roles["Over Etiknivo"] == QAction.MenuRole.AboutRole
    assert roles["Kalibratie-instellingen…"] == QAction.MenuRole.NoRole


def test_panel_widths_and_window_sizes_are_remembered(qtbot, window) -> None:  # noqa: ANN001
    from etiknivo.gui.bulk_edit import BulkEditDialog

    window.splitter.setSizes([260, 700, 440])
    wanted = window.splitter.sizes()
    window._save_panels()  # what dragging a panel edge does after a short pause
    lib, _ = open_library(data_dir() / "library.json")
    again = mw.MainWindow(lib, Settings(use_mock_printer=True), MockPrinterBackend(),
                          poll_interval=3600)
    qtbot.addWidget(again)
    again.resize(window.size())
    again.show()
    qtbot.wait(50)
    assert again.splitter.sizes()[0] == wanted[0] and again.splitter.sizes()[2] == wanted[2]

    dlg = BulkEditDialog(lib.labels, lib.categories())
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.resize(701, 455)
    dlg.table.setColumnWidth(0, 321)
    dlg.reject()
    dlg2 = BulkEditDialog(lib.labels, lib.categories())
    qtbot.addWidget(dlg2)
    assert dlg2.width() == 701 and dlg2.table.columnWidth(0) == 321


def test_qr_size_buttons(window) -> None:  # noqa: ANN001
    from etiknivo.model import CodeKind, CodeSize

    p = window.properties
    p.code_kind.setCurrentIndex(p._code_index(CodeKind.QR))
    assert p._code_size_box.isVisibleTo(p)
    p.code_sizes[0].click()
    assert window.current.code.size == CodeSize.SMALL
    p.code_kind.setCurrentIndex(0)
    assert not p._code_size_box.isVisibleTo(p)
