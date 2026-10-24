"""'Opmaak overnemen': copy the look of one label to others, text stays."""

from __future__ import annotations

from etiknivo.model import CodeKind, HAlign, LayoutPreset, PictureKind, copy_format, make_label
from etiknivo.settings import Settings


def _styled():  # noqa: ANN202
    src = make_label("A1", "Weerstand", "10 kΩ", "¼ W")
    src.apply_layout(LayoutPreset.MAIN_SPEC)
    src.main.font_size_pt = 18
    src.main.align = HAlign.LEFT
    src.style.border = True
    src.code.kind = CodeKind.QR
    src.picture.kind = PictureKind.SYMBOL
    src.picture.symbol = "diode"
    return src


def test_copy_format_parts_and_text_stays() -> None:
    src = _styled()
    dst = make_label("B2", "Condensator", "100 nF", "50 V")
    copy_format(src, dst, {"layout"})
    assert dst.layout == LayoutPreset.MAIN_SPEC and not dst.top.enabled
    assert dst.main.font_size_pt == 18 and dst.main.align == HAlign.LEFT
    assert dst.main.text == "100 nF" and dst.top.text == "Condensator"
    assert not dst.style.border and dst.code.kind == CodeKind.NONE
    copy_format(src, dst, {"style", "code", "picture"})
    assert dst.style.border and dst.code.kind == CodeKind.QR
    assert dst.picture.symbol == "diode"
    src.style.border = False  # deep copy: no shared state
    assert dst.style.border


def _window(qtbot):  # noqa: ANN001, ANN202
    from etiknivo.gui import main_window as mw
    from etiknivo.settings import data_dir
    from etiknivo.storage.library import open_library

    lib, _ = open_library(data_dir() / "library.json")
    win = mw.MainWindow(lib, Settings(use_mock_printer=True), poll_interval=3600)
    qtbot.addWidget(win)
    return win


def test_apply_format_to_category_with_undo(qtbot) -> None:  # noqa: ANN001
    win = _window(qtbot)
    first = win.library.labels[0]
    win.library_panel.select_ids([first.id])
    win.current.style.border = True
    win.current.picture.kind = PictureKind.SYMBOL
    others = win._format_targets("category", first.category)
    assert first.id not in others
    everyone = win._format_targets("all", "")
    assert len(everyone) == len(win.library) - 1
    texts = {i: win.library.get(i).main.text for i in everyone}
    n = win.apply_format(everyone, {"style", "picture"})
    assert n == len(everyone)
    for i in everyone:
        lbl = win.library.get(i)
        assert lbl.style.border and lbl.picture.kind == PictureKind.SYMBOL
        assert lbl.main.text == texts[i]
    win.undo()
    assert not any(win.library.get(i).style.border for i in everyone)


def test_dialog_targets_and_count(qtbot) -> None:  # noqa: ANN001
    from etiknivo.gui.dialogs import CopyFormatDialog

    src = _styled()
    counts = {"selection": 2, "category": 5, "all": 22}
    dlg = CopyFormatDialog(src, 2, ["Weerstand", "Diode"], lambda k, c: counts[k])
    qtbot.addWidget(dlg)
    assert dlg.target() == ("selection", "") and "2" in dlg.ok.text()
    dlg.on_category.setChecked(True)
    assert dlg.target() == ("category", "Weerstand") and "5" in dlg.ok.text()
    dlg.on_all.setChecked(True)
    assert "22" in dlg.ok.text()
    for box in dlg.parts.values():
        box.setChecked(False)
    assert not dlg.ok.isEnabled()
    dlg.parts["code"].setChecked(True)
    assert dlg.chosen_parts() == {"code"} and dlg.ok.isEnabled()

    none_selected = CopyFormatDialog(src, 0, ["Weerstand"], lambda k, c: counts[k])
    qtbot.addWidget(none_selected)
    assert not none_selected.on_selection.isEnabled()
    assert none_selected.target() == ("category", "Weerstand")
