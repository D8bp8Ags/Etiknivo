"""Fixes from the code review: braces around a specification name, file
errors shown instead of raised, a restored back-up that brings its own label
roll, and an import that leaves an unrelated draft alone."""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from etiknivo.gui import main_window as mw
from etiknivo.gui.dialogs import PrintPreviewDialog
from etiknivo.model import make_label, spec_name
from etiknivo.printing.mock import MockPrinterBackend
from etiknivo.settings import Settings, data_dir, save_settings
from etiknivo.storage import io as lio
from etiknivo.storage.library import open_library


def test_braces_around_a_specification_name_are_ignored() -> None:
    assert spec_name(" {Spanning} ") == "Spanning"
    lbl = make_label("A1", "", "{Spanning}")
    lbl.specs = {"{Spanning}": "50 V"}
    assert lbl.display_text(lbl.main) == "50 V"
    assert "Spanning" in lbl.field_names() and "{Spanning}" not in lbl.field_names()


@pytest.fixture
def window(qtbot, monkeypatch):  # noqa: ANN001, ANN201
    lib, _ = open_library(data_dir() / "library.json")
    monkeypatch.setattr(mw.MainWindow, "_ask_unsaved", lambda self, lbl: "discard")
    win = mw.MainWindow(lib, Settings(use_mock_printer=True), MockPrinterBackend(),
                        poll_interval=3600)
    qtbot.addWidget(win)
    win.show()
    monkeypatch.setattr(PrintPreviewDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    yield win
    win.close()


def test_file_errors_are_shown_not_raised(window, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda _p, _t, text: shown.append(text)))
    target = str(tmp_path / "missing-folder" / "x" / "out.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (target, "")))

    def fail(*_a: object) -> None:
        raise PermissionError("geen toegang")

    monkeypatch.setattr(lio, "export_csv", fail)
    window.export_csv()
    assert shown and "geen toegang" in shown[0]


def test_restore_uses_the_label_roll_of_the_backup(window, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    save_settings(Settings(label_size_mm=[40.0, 12.0]))
    archive = tmp_path / "backup.zip"
    window.save_library()
    lio.create_backup(data_dir(), archive)
    save_settings(Settings())
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(archive), "")))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    window.restore()
    assert window.profile.label_size == (40.0, 12.0)
    assert window.engine.profile is window.profile


def test_import_keeps_an_unrelated_draft(window, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    window.current.main.text = "Nog niet opgeslagen"
    assert window.is_dirty()
    other = make_label("Z9", "", "Nieuw van buiten")
    path = tmp_path / "import.json"
    path.write_text(json.dumps({"labels": [other.to_dict()]}), "utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(path), "")))

    def merge(box: QMessageBox) -> int:
        box.clickedButton = lambda: box.buttons()[0]  # "Samenvoegen"
        return 0

    monkeypatch.setattr(QMessageBox, "exec", merge)
    window.import_json()
    assert window.library.get(other.id) is not None
    assert window.current.main.text == "Nog niet opgeslagen"


def test_specs_table_edits_the_label(window) -> None:  # noqa: ANN001
    specs = window.properties.specs
    specs.add_row()
    row = specs.table.rowCount() - 1
    specs.table.item(row, 0).setText("{Spanning}")  # braces typed by habit
    specs.table.item(row, 1).setText("50 V")
    assert window.current.specs["Spanning"] == "50 V"
    assert specs.warning.isHidden()
    specs.table.item(row, 1).setText("{Lade}")
    assert not specs.warning.isHidden()  # a field in a value is not filled in


def test_specs_button_puts_the_field_in_a_line(window) -> None:  # noqa: ANN001
    props = window.properties
    props.specs.set_specs({"Spanning": "12 V"})
    props.specs.changed.emit()
    props.lines[2].text.setText("")
    targets = dict(props._field_targets())
    targets[props.lines[2].title().lower()]("Spanning")
    assert window.current.bottom.text == "{Spanning}"
    assert window.current.display_text(window.current.bottom) == "12 V"


def test_field_in_notes_shows_a_hint(window) -> None:  # noqa: ANN001
    props = window.properties
    props.notes.setPlainText("{Spanning}")
    assert not props.notes_hint.isHidden()
    props.notes.setPlainText("besteld bij de groothandel")
    assert props.notes_hint.isHidden()


def test_inspector_fits_a_narrow_window(window) -> None:  # noqa: ANN001
    props = window.properties
    body = props.widget()
    assert props.horizontalScrollBarPolicy() == props.horizontalScrollBarPolicy().ScrollBarAlwaysOff
    assert props.minimumSizeHint().width() >= body.minimumSizeHint().width()
    assert body.minimumSizeHint().width() < 340
    assert window.minimumSizeHint().width() < 1150


def test_style_section_folds_and_remembers(window) -> None:  # noqa: ANN001
    from etiknivo.gui.properties_panel import CollapsibleSection

    section = window.properties.style_section
    section.set_open(False)
    assert section.body.isHidden()
    again = CollapsibleSection("Opmaak", "style_open")
    assert not again.is_open()  # remembered
    section.set_open(True)
    assert not section.body.isHidden()


def test_compact_lines_and_section_summaries(window) -> None:  # noqa: ANN001
    props = window.properties
    line = props.lines[1]
    assert line.details.isHidden()  # font, size, style, alignment folded away
    line.more.click()
    assert not line.details.isHidden()
    line.more.click()
    order = [props.widget().layout().indexOf(w) for w in (
        props.label_section, props.text_section, props.code_group, props.pic_group,
        props.meta_section, props.style_section)]
    assert order == sorted(order)
    props.code_group.set_open(False)
    assert props.code_group.toggle.text().startswith(props.code_group._title + "  ·  ")
    props.code_group.set_open(True)
    assert props.code_group.toggle.text() == props.code_group._title


def test_pictograms_dialog_suggests_and_applies(window, monkeypatch) -> None:  # noqa: ANN001
    from etiknivo.gui.dialogs import PictogramsDialog
    from etiknivo.model import PictureKind
    from etiknivo.rendering.symbols import suggest_symbol

    assert suggest_symbol("Weerstanden", "") == "resistor"
    assert suggest_symbol("Ringkern", "") is None  # a short word must be whole
    for lbl in window.library.labels:
        lbl.picture.kind = PictureKind.NONE
    window.open_label(next(lbl.id for lbl in window.library.labels
                           if lbl.category == "Weerstanden"))
    window.current.picture.kind = PictureKind.NONE
    assert not window.is_dirty()
    dupont = [lbl.id for lbl in window.library.labels if lbl.category == "Dupont"]

    def accept(dlg: PictogramsDialog) -> int:
        dlg.set_category_symbol("Antennes", "")
        # two Dupont labels get their own symbol, a third is skipped
        dlg.tree.clearSelection()
        for lid in dupont[:2]:
            dlg._items[lid].setSelected(True)
        dlg._set_own("cable")
        dlg.tree.clearSelection()
        dlg._items[dupont[2]].setSelected(True)
        dlg._check(False)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PictogramsDialog, "exec", accept)
    window.choose_pictograms()
    labels = {lbl.id: lbl for lbl in window.library.labels}
    by_cat = {lbl.category: lbl for lbl in labels.values()}
    assert by_cat["Weerstanden"].picture.symbol == "resistor"
    assert by_cat["Weerstanden"].picture.kind == PictureKind.SYMBOL
    assert by_cat["Antennes"].picture.kind == PictureKind.NONE
    assert [labels[i].picture.symbol for i in dupont[:2]] == ["cable", "cable"]
    assert labels[dupont[2]].picture.kind == PictureKind.NONE  # skipped
    # remembered per category, and used for a new label in that category
    assert window.library.category_symbols["Antennes"] == ""
    assert window.library.category_symbols["Dupont"] == "connector"
    new = make_label("", "Dupont", "nieuw")
    window._apply_category_style(new)
    assert new.picture.kind == PictureKind.SYMBOL and new.picture.symbol == "connector"
    # the open label: saved, shown in the editor, and not left as an unsaved draft
    assert window.current.picture.symbol == "resistor" and not window.is_dirty()
    assert window.design_view.result.picture_box is not None


def test_bulk_edit_spreads_over_the_selection(window, monkeypatch) -> None:  # noqa: ANN001
    from etiknivo.gui.bulk_edit import CATEGORY_COLUMN, BulkEditDialog

    first = window.library.labels[0]
    window.open_label(first.id)
    dupont = [lbl.id for lbl in window.library.labels if lbl.category == "Dupont"]

    def accept(dlg: BulkEditDialog) -> int:
        rows = [r for r in range(dlg.table.rowCount())
                if dlg.table.item(r, 0).data(Qt.ItemDataRole.UserRole) in dupont]
        dlg.table.clearSelection()
        for r in rows:
            dlg.table.item(r, CATEGORY_COLUMN).setSelected(True)
        dlg.set_cell(rows[0], CATEGORY_COLUMN, "Kabels")
        assert all(dlg.table.item(r, CATEGORY_COLUMN).text() == "Kabels" for r in rows)
        dlg.table.clearSelection()
        dlg.set_cell(0, 1, "Z99")  # the open label, on its own
        assert len(dlg.changes()) == len(dupont) + 1
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(BulkEditDialog, "exec", accept)
    window.edit_labels()
    assert {window.library.get(i).category for i in dupont} == {"Kabels"}
    assert window.library.get(first.id).tray_id == "Z99"
    assert window.current.tray_id == "Z99" and not window.is_dirty()
    window.undo()
    assert {window.library.get(i).category for i in dupont} == {"Dupont"}


def test_field_menu_explains_each_field(qtbot) -> None:  # noqa: ANN001
    from PySide6.QtWidgets import QLineEdit

    from etiknivo.gui.widgets import FieldButton

    edit = QLineEdit()
    btn = FieldButton(edit, lambda: ["Spanning", "Naam", "Nr"])
    qtbot.addWidget(btn)
    btn._fill()
    texts = [a.text() for a in btn._menu.actions()]
    assert "{Spanning}" in texts
    assert any(t.startswith("{Nr}") and "volgnummer" in t for t in texts)
    next(a for a in btn._menu.actions() if a.text().startswith("{Nr}")).trigger()
    assert edit.text() == "{Nr}"


def test_notes_grow_and_open_links(window, qtbot, monkeypatch) -> None:  # noqa: ANN001
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QDesktopServices, QMouseEvent

    from etiknivo.gui.notes_edit import find_links, link_url

    text = ("Passieve buzzer — TinyTronics\nhttps://www.tinytronics.nl/nl/audio/speakers/x.\n"
            "mail info@example.com of www.example.org")
    assert find_links(text) == ["https://www.tinytronics.nl/nl/audio/speakers/x",
                                "info@example.com", "www.example.org"]
    assert link_url("www.example.org").toString() == "https://www.example.org"
    assert link_url("info@example.com").toString() == "mailto:info@example.com"

    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    props = window.properties
    notes = props.notes
    short = notes.sizeHint().height()
    notes.setPlainText(text + "\n" * 6)
    assert notes.sizeHint().height() > short  # grows with its text
    assert props.notes_links.isVisible() or not props.isVisible()
    assert "tinytronics.nl/nl/audio/speakers/x" in props.notes_links.text()

    notes.setPlainText(text)
    cursor = notes.textCursor()
    cursor.setPosition(text.index("tinytronics") + 3)
    pos = QPointF(notes.cursorRect(cursor).center())
    for mods in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ControlModifier):
        notes.mousePressEvent(QMouseEvent(QMouseEvent.Type.MouseButtonPress, pos, pos,
                                          Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                          mods))
    assert opened == ["https://www.tinytronics.nl/nl/audio/speakers/x"]  # only with Cmd


def test_bulk_edit_category_shows_every_category(qtbot) -> None:  # noqa: ANN001
    from PySide6.QtWidgets import QComboBox

    from etiknivo.gui.bulk_edit import CATEGORY_COLUMN, BulkEditDialog
    from etiknivo.storage.library import seed_labels

    labels = seed_labels()
    cats = sorted({lbl.category for lbl in labels}, key=str.casefold)
    dlg = BulkEditDialog(labels, cats)
    qtbot.addWidget(dlg)
    dlg.show()
    item = dlg.table.item(0, CATEGORY_COLUMN)
    dlg.table.setCurrentItem(item)
    dlg.table.editItem(item)
    editor = dlg.table.findChild(QComboBox)
    assert editor is not None and editor.isEditable()
    assert [editor.itemText(i) for i in range(editor.count())] == cats  # all, not filtered
    assert editor.currentText() == labels[0].category
    editor.setCurrentText("Nieuwe categorie")
    dlg.table.commitData(editor)
    assert dlg.changes()[labels[0].id].category == "Nieuwe categorie"
