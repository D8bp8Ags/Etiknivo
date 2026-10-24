"""A new label takes the style of the last edited label in its category."""

from __future__ import annotations

import pytest

from etiknivo.model import HAlign, PictureKind
from etiknivo.settings import Settings


@pytest.fixture(autouse=True)
def _no_questions(monkeypatch):  # noqa: ANN001, ANN202
    from etiknivo.gui import main_window as mw

    monkeypatch.setattr(mw.MainWindow, "_ask_unsaved", lambda self, lbl: "discard")


def _window(qtbot):  # noqa: ANN001, ANN202
    from etiknivo.gui import main_window as mw
    from etiknivo.settings import data_dir
    from etiknivo.storage.library import open_library

    lib, _ = open_library(data_dir() / "library.json")
    win = mw.MainWindow(lib, Settings(use_mock_printer=True), poll_interval=3600)
    qtbot.addWidget(win)
    return win


def _style_category(win, category: str):  # noqa: ANN001, ANN202
    model = next(lbl for lbl in win.library.labels if lbl.category == category)
    model.main.align = HAlign.LEFT
    model.style.border = True
    model.picture.kind = PictureKind.SYMBOL
    model.picture.symbol = "diode"
    model.modified = "2999-01-01T00:00:00+00:00"  # most recently edited
    return model


def test_new_label_in_filtered_category(qtbot) -> None:  # noqa: ANN001
    win = _window(qtbot)
    model = _style_category(win, "Dupont")
    win.library_panel.category.setCurrentText("Dupont")
    win.new_label()
    new = win.current
    assert new.category == "Dupont" and new.id != model.id
    assert new.main.align == HAlign.LEFT and new.style.border
    assert new.picture.symbol == "diode"
    assert new.main.text == "Nieuw label"  # text is not copied


def test_new_label_gets_style_when_category_is_chosen(qtbot) -> None:  # noqa: ANN001
    win = _window(qtbot)
    _style_category(win, "Audio")
    win.new_label()
    assert win.current.category == "" and not win.current.style.border
    win.properties.category.setCurrentText("Audio")
    win.properties._commit_category()
    assert win.current.category == "Audio"
    assert win.current.style.border and win.current.main.align == HAlign.LEFT


def test_hand_styled_new_label_is_left_alone(qtbot) -> None:  # noqa: ANN001
    win = _window(qtbot)
    _style_category(win, "Audio")
    win.new_label()
    win.properties.invert.setChecked(True)  # the user styles it first
    win.properties.category.setCurrentText("Audio")
    win.properties._commit_category()
    assert win.current.style.invert and not win.current.style.border


def test_empty_category_keeps_default(qtbot) -> None:  # noqa: ANN001
    win = _window(qtbot)
    assert win.category_template("") is None
    assert win.category_template("bestaat-niet") is None
