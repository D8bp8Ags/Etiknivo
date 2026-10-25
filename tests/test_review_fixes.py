"""Fixes from the code review: braces around a specification name, file
errors shown instead of raised, a restored back-up that brings its own label
roll, and an import that leaves an unrelated draft alone."""

from __future__ import annotations

import json

import pytest
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
