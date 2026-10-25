"""Free layout: loose elements that can be placed anywhere."""

from __future__ import annotations

import pytest
from PIL import Image, ImageChops
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

from etiknivo.model import (
    CodeKind,
    ElementKind,
    Label,
    LabelElement,
    LayoutPreset,
    PictureKind,
    copy_format,
    make_label,
)
from etiknivo.rendering.engine import RenderEngine
from tests.test_gui import window  # noqa: F401 - fixture

zxingcpp = pytest.importorskip("zxingcpp")


def free_label(*elements: LabelElement) -> Label:
    lbl = make_label("B7", "Diodes", "1N4148")
    lbl.layout = LayoutPreset.FREE
    lbl.elements = list(elements)
    return lbl


def black(img: Image.Image, box: tuple[int, int, int, int]) -> int:
    return sum(1 for v in img.convert("L").crop(box).get_flattened_data() if v == 0)


def test_elements_survive_saving() -> None:
    lbl = free_label(LabelElement(ElementKind.TEXT, 1, 2, 10, 3, text="{Lade}", bold=True),
                     LabelElement(ElementKind.SYMBOL, 12, 1, 5, 5, symbol="diode"))
    back = Label.from_dict(lbl.to_dict())
    assert back.is_free and back.elements == lbl.elements
    junk = LabelElement.from_dict({"kind": "line", "w_mm": -4, "h_mm": "0"})
    assert junk.w_mm == junk.h_mm == 0.125  # at least one dot


def test_converting_keeps_the_label_identical(engine: RenderEngine) -> None:
    lbl = make_label("A1", "R", "10 kΩ", "1%")
    lbl.code.kind, lbl.code.text = CodeKind.QR, "{Lade}"
    lbl.picture.kind, lbl.picture.symbol = PictureKind.SYMBOL, "resistor"
    lbl.style.separators = True
    first = engine.render(lbl)
    assert first.warnings == []
    before = first.mono
    lbl.elements = engine.to_elements(lbl)
    assert [e.kind for e in lbl.elements] == [ElementKind.TEXT] * 3 + [ElementKind.LINE] * 2 + \
        [ElementKind.QR, ElementKind.SYMBOL]
    lbl.apply_layout(LayoutPreset.FREE)
    after = engine.render(lbl)
    assert after.warnings == []
    assert ImageChops.difference(before, after.mono).getbbox() is None


def test_text_shrinks_to_its_box(engine: RenderEngine) -> None:
    lbl = free_label(LabelElement(ElementKind.TEXT, 0, 0, 20, 3, text="Lange tekst hier",
                                  font_size_pt=20))
    r = engine.render(lbl)
    lb = r.lines[0]
    assert lb.size_pt < 20 and not lb.overflow
    x0, y0, x1, y1 = r.element_boxes[lbl.elements[0].id]
    assert x0 - 0.5 <= lb.x0 and lb.x1 <= x1 + 0.5 and y0 - 0.5 <= lb.y0 and lb.y1 <= y1 + 0.5


def test_codes_scan_and_fields_fill_in(engine: RenderEngine) -> None:
    lbl = free_label(LabelElement(ElementKind.QR, 0, 0, 11, 11, text="{Lade}-{Nr}"),
                     LabelElement(ElementKind.BARCODE, 12, 3, 13, 6, text="{Lade}"))
    img = engine.render(lbl.for_copy(2, 3)).mono.convert("L")
    big = img.resize((img.width * 4, img.height * 4), Image.Resampling.NEAREST)
    assert sorted(r.text for r in zxingcpp.read_barcodes(big)) == ["B7", "B7-2"]


def test_lines_frames_and_warnings(engine: RenderEngine) -> None:
    px0, py0 = engine.printable_box[:2]
    lbl = free_label(LabelElement(ElementKind.LINE, 0, 5, 10, 0.125),
                     LabelElement(ElementKind.BOX, 12, 1, 8, 8))
    r = engine.render(lbl)
    assert r.warnings == []
    assert black(r.mono, (px0, py0 + 40, px0 + 80, py0 + 41)) == 80  # 10 mm, one dot high
    frame = (px0 + 96, py0 + 8, px0 + 160, py0 + 72)
    assert black(r.mono, frame) == 64 * 4 - 4  # outline only
    lbl.elements[0].move_to(-3, 5)
    assert any("buiten het printbare gebied" in w for w in engine.render(lbl).warnings)
    assert any("geen elementen" in w for w in engine.render(free_label()).warnings)


def test_copy_format_takes_the_free_layout() -> None:
    src = free_label(LabelElement(ElementKind.TEXT, 1, 1, 10, 3, text="{Naam}"),
                     LabelElement(ElementKind.LINE, 0, 5, 20, 0.25))
    dst = make_label("C1", "Diodes", "Zener")
    copy_format(src, dst, {"layout"})
    assert dst.is_free and [e.text for e in dst.elements] == ["{Naam}", ""]
    dst.elements[0].text = "eigen"
    src.elements[0].x_mm = 4
    copy_format(src, dst, {"layout"})
    assert dst.elements[0].x_mm == 4 and dst.elements[0].text == "eigen"


def test_free_layout_in_the_window(qtbot, window) -> None:  # noqa: ANN001, F811
    pp, dv = window.properties, window.design_view
    before = window.engine.render(window.current).mono
    pp.mode_free.click()
    lbl = window.current
    assert lbl.is_free and len(lbl.elements) == 3 + (lbl.picture.kind != PictureKind.NONE)
    assert pp.elements.isVisible() and not pp.lines[0].isVisible()
    assert ImageChops.difference(before, window.engine.render(lbl).mono).getbbox() is None

    # pick and drag the first element: it moves in whole dots and stays selected
    window.update_preview()
    el = lbl.elements[0]
    x, y = el.x_mm, el.y_mm
    start = dv.element_rect(el).center()
    step = dv.label_rect().width() / window.engine.design_size[0]  # screen px per dot
    QTest.mousePress(dv, Qt.MouseButton.LeftButton, pos=start.toPoint())
    end = start + QPointF(10 * step, 3 * step)
    QTest.mouseMove(dv, end.toPoint())
    QTest.mouseRelease(dv, Qt.MouseButton.LeftButton, pos=end.toPoint())
    assert pp.elements.current() is el and dv.selected == el.id
    assert el.x_mm == pytest.approx(x + 10 / 8, abs=0.13)
    assert el.y_mm == pytest.approx(y + 3 / 8, abs=0.13)
    assert pp.elements.x.value() == pytest.approx(el.x_mm, abs=0.005)
    assert window.is_dirty()

    # arrow keys nudge one dot, Delete removes
    QTest.keyClick(dv, Qt.Key.Key_Right)
    assert el.x_mm == pytest.approx(x + 10 / 8 + 1 / 8, abs=0.13)
    QTest.keyClick(dv, Qt.Key.Key_Delete)
    assert el not in lbl.elements and pp.elements.list.count() == len(lbl.elements)

    # add from the panel; undo brings the deleted element back
    before_delete = len(lbl.elements) + 1
    added = pp.elements.add(ElementKind.QR)
    assert added in lbl.elements and dv.selected == added.id
    assert added.text == "{Lade}"
    window.undo()
    window.undo()
    assert len(window.current.elements) == before_delete


def test_a_symbol_fills_its_box(engine: RenderEngine) -> None:
    """A free symbol leaves out the white space around its drawing, and only
    its ink counts for the printable area."""
    star = LabelElement(ElementKind.SYMBOL, 2, 1, 8, 8, symbol="star")
    r = engine.render(free_label(star))
    assert r.warnings == []
    bx0, by0, bx1, by1 = (round(v) for v in engine.element_box(star))
    ink = r.mono.crop((bx0, by0, bx1, by1)).point(lambda v: 255 - v).getbbox()
    assert ink is not None and ink[1] <= 1 and ink[3] >= by1 - by0 - 1  # top to bottom
    star.x_mm = -3
    assert any(star.title in w for w in engine.render(free_label(star)).warnings)


def test_back_to_free_asks_when_the_lines_changed(window, monkeypatch) -> None:  # noqa: ANN001, F811
    pp = window.properties
    lbl = window.current
    pp.mode_free.click()
    made = lbl.elements
    lbl.elements[0].x_mm += 1  # an edit in the free layout
    pp.mode_lines.click()
    assert not lbl.is_free and pp.lines[0].isVisible()
    asked: list[bool] = []
    monkeypatch.setattr(type(pp), "_ask_rebuild", lambda self: asked.append(True) or False)
    pp.mode_free.click()  # nothing changed: the free layout comes back as it was
    assert lbl.elements is made and not asked
    pp.mode_lines.click()
    pp.lines[1].text.setText("Iets anders")
    pp.lines[1].text.textEdited.emit("Iets anders")
    pp.mode_free.click()  # lines changed: asked, and "keep" keeps the edit
    assert asked == [True] and lbl.elements is made
    pp.mode_lines.click()
    monkeypatch.setattr(type(pp), "_ask_rebuild", lambda self: True)
    pp.mode_free.click()  # "make again" uses the new text
    assert lbl.elements is not made
    assert any(e.text == "Iets anders" for e in lbl.elements)
