"""Other label rolls: one setting for the roll in the printer, used everywhere."""

from __future__ import annotations

from etiknivo.model import make_label
from etiknivo.printing.profiles import FICHERO_5836
from etiknivo.rendering.engine import RenderEngine
from etiknivo.settings import Settings, load_settings


def test_with_label_changes_geometry() -> None:
    p = FICHERO_5836.with_label(40, 12)
    assert p.label_size == (40, 12) and p.key == FICHERO_5836.key
    assert p.native_raster_size == (96, 320)
    assert p.printable_offset_px == 0 and p.printable_across_px == 96
    assert FICHERO_5836.label_size == (30, 14)  # the base profile is untouched
    wide = FICHERO_5836.with_label(50, 15)
    assert wide.printable_offset_px == 12


def test_with_label_clamps() -> None:
    assert FICHERO_5836.with_label(500, 1).label_size == (100, 6)
    assert FICHERO_5836.with_label(15, 14).feed_margin_mm == FICHERO_5836.feed_margin_mm


def test_render_on_other_roll() -> None:
    for length, height in FICHERO_5836.label_sizes:
        prof = FICHERO_5836.with_label(length, height)
        r = RenderEngine(prof).render(make_label("A1", "Weerstand", "10 kΩ", "¼ W"))
        assert r.raster.size == prof.native_raster_size
        assert r.mono.size == (prof.label_length_px, prof.label_across_px)
        assert not r.has_overflow


def _window(qtbot, settings: Settings):  # noqa: ANN001, ANN202
    from etiknivo.gui import main_window as mw
    from etiknivo.settings import data_dir
    from etiknivo.storage.library import open_library

    lib, _ = open_library(data_dir() / "library.json")
    win = mw.MainWindow(lib, settings, poll_interval=3600)
    qtbot.addWidget(win)
    return win


def test_gui_switches_roll_live_and_remembers(qtbot) -> None:  # noqa: ANN001
    win = _window(qtbot, Settings(use_mock_printer=True))
    pp = win.printer_panel
    assert pp.roll.currentText() == "30 × 14 mm"
    assert pp.roll.itemText(pp.roll.count() - 1) == "Aangepast…"
    pp.roll.setCurrentIndex(1)
    pp.roll.activated.emit(1)  # 40 × 14
    assert win.profile.label_size == (40, 14)
    assert win.engine.profile is win.profile
    assert win.raster_view.result.raster.size == (96, 320)
    assert "320" in win.raster_caption.text() and "320" in win.native.text()
    assert load_settings().label_size_mm == [40, 14]

    again = _window(qtbot, load_settings())
    assert again.profile.label_size == (40, 14)
    assert again.printer_panel.roll.currentText() == "40 × 14 mm"


def test_custom_roll(qtbot, monkeypatch) -> None:  # noqa: ANN001
    from etiknivo.gui import dialogs

    monkeypatch.setattr(dialogs.LabelSizeDialog, "exec",
                        lambda self: (self.length.setValue(25), self.height_mm.setValue(10),
                                      dialogs.LabelSizeDialog.DialogCode.Accepted)[-1])
    win = _window(qtbot, Settings(use_mock_printer=True))
    pp = win.printer_panel
    custom = pp.roll.count() - 1
    pp.roll.setCurrentIndex(custom)
    pp.roll.activated.emit(custom)
    assert win.profile.label_size == (25, 10)
    assert pp.roll.currentText() == "25 × 10 mm"  # custom size listed and selected
    assert win.raster_view.result.raster.size == (96, 200)

    monkeypatch.setattr(dialogs.LabelSizeDialog, "exec",
                        lambda self: dialogs.LabelSizeDialog.DialogCode.Rejected)
    custom = pp.roll.count() - 1
    pp.roll.setCurrentIndex(custom)
    pp.roll.activated.emit(custom)
    assert win.profile.label_size == (25, 10)
    assert pp.roll.currentText() == "25 × 10 mm"


def test_broken_setting_falls_back(qtbot) -> None:  # noqa: ANN001
    win = _window(qtbot, Settings(use_mock_printer=True, label_size_mm=["x"]))  # type: ignore[list-item]
    assert win.profile.label_size == (30, 14)
