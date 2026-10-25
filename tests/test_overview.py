"""Label overview: grouping, the A4 sheet and the window."""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QFileDialog

from etiknivo.gui import main_window as mw
from etiknivo.model import make_label
from etiknivo.printing.mock import MockPrinterBackend
from etiknivo.rendering import overview
from etiknivo.settings import Settings, data_dir
from etiknivo.storage.library import open_library, seed_labels


def test_groups_by_category_with_uncategorised_last() -> None:
    labels = [make_label("B2", "Weerstand", "1k"), make_label("", "", "Los"),
              make_label("A1", "Audio", "Jack"), make_label("B1", "Weerstand", "10k")]
    groups = overview.overview_order(labels)
    assert [cat for cat, _ in groups] == ["Audio", "Weerstand", ""]
    assert [lbl.tray_id for lbl in groups[1][1]] == ["B1", "B2"]


def test_small_categories_share_a_row(engine) -> None:  # noqa: ANN001
    layout = overview.OverviewLayout(engine, overview.A4_MM[0], overview.A4_MM[1])
    page = layout.pages(overview.overview_order(seed_labels()))[0]
    headings = [item for item in page if item[0] == "heading"]
    assert {h[1] for h in headings[:3]} == {headings[0][1]}  # side by side, same height
    labels = [item for item in page if item[0] == "label"]
    assert len(labels) == 23 and all(item[3] < layout.cols for item in labels)


def test_pdf_has_a4_pages_with_labels_at_real_size(engine, tmp_path) -> None:  # noqa: ANN001
    pages = overview.overview_pages(engine, seed_labels(), today=date(2026, 10, 25))
    ppm = engine.profile.dots_per_mm * 2
    assert pages[0].size == (round(210 * ppm), round(297 * ppm))
    many = [make_label(f"X{n}", f"Cat {n % 7}", f"Label {n}") for n in range(120)]
    assert len(overview.overview_pages(engine, many)) > 1
    path = tmp_path / "overzicht.pdf"
    assert overview.export_overview_pdf(engine, many, path) > 1
    assert path.read_bytes().startswith(b"%PDF")
    png = tmp_path / "overzicht.png"
    overview.export_overview_png(engine, seed_labels(), png)
    assert png.stat().st_size > 1000


@pytest.fixture
def window(qtbot, monkeypatch):  # noqa: ANN001, ANN201
    lib, _ = open_library(data_dir() / "library.json")
    monkeypatch.setattr(mw.MainWindow, "_ask_unsaved", lambda self, lbl: "discard")
    win = mw.MainWindow(lib, Settings(use_mock_printer=True), MockPrinterBackend(),
                        poll_interval=3600)
    qtbot.addWidget(win)
    win.show()
    yield win
    win.close()


def test_window_lists_searches_and_opens_labels(qtbot, window, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    window.show_overview()
    ov = window._overview_window
    ov.resize(900, 600)
    qtbot.waitExposed(ov)
    assert len(ov.canvas.labels) == 23 and ov.count.text() == "23 labels"
    target = next(lbl for lbl in window.library.labels if lbl.id != window.current.id)
    window.library_panel.search.setText("iets dat nergens staat")  # filter hides the target
    rect = next(r for r, lid in ov.canvas._hits if lid == target.id)
    ov.canvas.labelClicked.emit(ov.canvas.label_at(QPointF(rect.center())))
    assert window.current.id == target.id
    assert ov.canvas.current == target.id

    ov.search.setText(target.tray_id)
    assert [lbl.id for lbl in ov.canvas.labels] == [target.id]
    out = tmp_path / "uit.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    assert ov.export("pdf") == out and out.exists()


def test_window_follows_library_changes(window) -> None:  # noqa: ANN001
    window.show_overview()
    ov = window._overview_window
    window.new_label()
    assert len(ov.canvas.labels) == 24
