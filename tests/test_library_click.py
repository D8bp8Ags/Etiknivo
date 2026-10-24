"""Clicking a category heading or empty space keeps the open label."""

from __future__ import annotations

from PySide6.QtCore import Qt

from etiknivo.gui.library_panel import HEADER_ROLE
from etiknivo.settings import Settings


def _window(qtbot):  # noqa: ANN001, ANN202
    from etiknivo.gui import main_window as mw
    from etiknivo.settings import data_dir
    from etiknivo.storage.library import open_library

    lib, _ = open_library(data_dir() / "library.json")
    win = mw.MainWindow(lib, Settings(use_mock_printer=True), poll_interval=3600)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


def test_click_on_heading_keeps_label(qtbot) -> None:  # noqa: ANN001
    win = _window(qtbot)
    panel = win.library_panel
    first = panel.visible_ids()[1]
    panel.select_ids([first])
    assert win.current is not None and win.current.id == first
    tree = panel.tree
    head = tree.topLevelItem(0)
    assert head.data(0, HEADER_ROLE)
    rect = tree.visualItemRect(head)
    qtbot.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert panel.selected_ids() == [first]
    assert win.current is not None and win.current.id == first
    assert win.raster_view.result is not None


def test_clearing_selection_by_hand_keeps_label(qtbot) -> None:  # noqa: ANN001
    win = _window(qtbot)
    panel = win.library_panel
    ids = panel.visible_ids()[:2]
    panel.select_ids(ids)
    panel.tree.clearSelection()  # what a click on empty space does
    assert sorted(panel.selected_ids()) == sorted(ids)
    assert win.current is not None


def test_program_can_still_clear(qtbot) -> None:  # noqa: ANN001
    win = _window(qtbot)
    panel = win.library_panel
    panel.select_ids([panel.visible_ids()[0]])
    panel.select_ids([])
    assert panel.selected_ids() == []
