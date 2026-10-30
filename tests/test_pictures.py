"""Pictograms on labels: own symbols and the user's own images."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from etiknivo.model import CodeKind, CodeSize, HAlign, Label, PictureKind, VAlign, make_label
from etiknivo.rendering import pictures, symbols
from etiknivo.rendering.engine import RenderEngine


@pytest.mark.parametrize("key", list(symbols.SYMBOLS))
def test_every_symbol_draws_ink_inside(key: str) -> None:
    img = symbols.draw_symbol(key, 96)
    assert img.size == (96, 96)
    ink = img.point(lambda v: 255 if v < 128 else 0).histogram()[255]
    assert 150 < ink < 96 * 96 * 0.6, ink
    assert img.getpixel((0, 0)) == 255 or key in ("ground",)


def _black_box(lbl: Label) -> tuple[int, int, int, int] | None:
    return RenderEngine().render(lbl).mono.convert("L").point(lambda v: 255 - v).getbbox()


def _label(kind: PictureKind, side: HAlign = HAlign.LEFT) -> Label:
    lbl = make_label("A1", "Weerstand", "10 kΩ", "¼ W")
    lbl.picture.kind, lbl.picture.side = kind, side
    return lbl


@pytest.mark.parametrize("side", [HAlign.LEFT, HAlign.RIGHT])
def test_symbol_beside_text(side: HAlign) -> None:
    eng = RenderEngine()
    plain = eng.render(_label(PictureKind.NONE))
    r = eng.render(_label(PictureKind.SYMBOL, side))
    assert not r.warnings and not r.has_overflow
    px0, _py0, px1, _py1 = eng.printable_box
    bx0, _by0, bx1, _by1 = r.picture_box
    fx0, _fy0, fx1, _fy1 = symbols.ink_box(_label(PictureKind.SYMBOL).picture.symbol)
    if side == HAlign.LEFT:
        assert min(lb.x0 for lb in r.lines) > bx0 + fx1 * (bx1 - bx0)  # right of its ink
        assert r.mono.crop((px0, 0, px0 + 60, r.mono.height)).getextrema()[0] == 0  # ink
    else:
        assert max(lb.x1 for lb in r.lines) < bx0 + fx0 * (bx1 - bx0)
    assert plain.lines[1].size_pt >= r.lines[1].size_pt


def test_picture_and_qr_share_the_label() -> None:
    lbl = _label(PictureKind.SYMBOL, HAlign.LEFT)
    lbl.code.kind = CodeKind.QR
    lbl.code.side = HAlign.LEFT
    r = RenderEngine().render(lbl)
    assert r.code is not None
    # text sits right of both the QR code and the symbol
    assert min(lb.x0 for lb in r.lines) > r.code.box[2] + 40


def test_picture_sizes() -> None:
    eng = RenderEngine()
    heights = {}
    for size in CodeSize:
        lbl = make_label("A1", "R", "", "")  # short text: no shrinking back
        lbl.picture.kind, lbl.picture.size = PictureKind.SYMBOL, size
        r = eng.render(lbl)
        assert not r.warnings and not r.has_overflow
        heights[size] = r.picture_box[3] - r.picture_box[1]
    assert heights[CodeSize.SMALL] < heights[CodeSize.MEDIUM] < heights[CodeSize.LARGE]
    # labels from before the choice keep their size
    assert Label.from_dict({"picture": {"kind": "symbol"}}).picture.size == CodeSize.MEDIUM


@pytest.mark.parametrize("side", [HAlign.LEFT, HAlign.RIGHT])
@pytest.mark.parametrize("valign", list(VAlign))
def test_picture_six_positions(side: HAlign, valign: VAlign) -> None:
    eng = RenderEngine()
    lbl = _label(PictureKind.SYMBOL, side)
    lbl.picture.valign, lbl.picture.size = valign, CodeSize.SMALL
    r = eng.render(lbl)
    assert not r.warnings and not r.has_overflow
    _cx0, cy0, _cx1, cy1 = r.content_box
    bx0, by0, bx1, by1 = r.picture_box
    fx0, fy0, fx1, fy1 = symbols.ink_box(lbl.picture.symbol)
    ink_top, ink_bottom = by0 + fy0 * (by1 - by0), by0 + fy1 * (by1 - by0)
    if valign == VAlign.TOP:
        assert abs(ink_top - cy0) <= 1
    elif valign == VAlign.BOTTOM:
        assert abs(ink_bottom - cy1) <= 1
    else:
        assert abs((by0 - cy0) - (cy1 - by1)) <= 1
    if side == HAlign.LEFT:
        assert min(lb.x0 for lb in r.lines) > bx0 + fx1 * (bx1 - bx0)
    else:
        assert max(lb.x1 for lb in r.lines) < bx0 + fx0 * (bx1 - bx0)
    back = Label.from_dict(lbl.to_dict()).picture
    assert (back.side, back.valign, back.size) == (side, valign, CodeSize.SMALL)
    assert Label.from_dict({"picture": {"kind": "symbol"}}).picture.valign == VAlign.CENTER


def _logo(tmp_path: Path) -> Path:
    img = Image.new("RGBA", (300, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((20, 20, 280, 130), fill=(200, 0, 0, 255))
    d.ellipse((120, 45, 180, 105), fill=(255, 255, 255, 255))
    path = tmp_path / "logo.png"
    img.save(path)
    return path


def test_own_image_is_trimmed_stored_and_drawn(tmp_path: Path) -> None:
    data = pictures.load_file(_logo(tmp_path))
    img = pictures.decode(data)
    assert img is not None and img.mode == "L"
    assert img.size == (256, 107) or abs(img.width / img.height - 261 / 111) < 0.05
    lbl = _label(PictureKind.IMAGE)
    lbl.picture.image_png = data
    back = Label.from_dict(lbl.to_dict())
    assert back.picture.image_png == data and back.picture.kind == PictureKind.IMAGE
    r = RenderEngine().render(back)
    assert not r.warnings
    assert min(lb.x0 for lb in r.lines) > 60


def test_image_problems_warn(tmp_path: Path) -> None:
    lbl = _label(PictureKind.IMAGE)
    assert any("afbeelding" in w for w in RenderEngine().render(lbl).warnings)
    lbl.picture.kind, lbl.picture.symbol = PictureKind.SYMBOL, "bestaat-niet"
    assert any("bestaat-niet" in w for w in RenderEngine().render(lbl).warnings)
    bad = tmp_path / "x.png"
    bad.write_text("geen plaatje")
    with pytest.raises(pictures.ImageError):
        pictures.load_file(bad)
    assert Label.from_dict({"picture": {"kind": "raar"}}).picture.kind == PictureKind.NONE


def test_panel_picture_controls(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    from etiknivo.gui.properties_panel import PropertiesPanel

    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    lbl = _label(PictureKind.NONE)
    panel.set_label(lbl)
    assert not panel.pic_symbol.isEnabled() and not panel.pic_image_btn.isEnabled()
    panel.pic_kind.setCurrentIndex(1)
    panel.pic_symbol.setCurrentIndex(panel.pic_symbol.findData("diode"))
    panel.pic_pos.setCurrentIndex(5)  # right, bottom
    panel.pic_sizes[2].click()
    assert (lbl.picture.kind, lbl.picture.symbol, lbl.picture.side, lbl.picture.valign,
            lbl.picture.size) == (PictureKind.SYMBOL, "diode", HAlign.RIGHT, VAlign.BOTTOM,
                                  CodeSize.LARGE)
    assert panel._pic_size_box.isVisibleTo(panel)
    assert panel.pic_symbol.isEnabled()
    assert panel.set_image_file(_logo(tmp_path))
    assert lbl.picture.kind == PictureKind.IMAGE and lbl.picture.image_png
    assert panel.pic_image_btn.isEnabled()

    svg = tmp_path / "logo.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
                   '<rect x="2" y="2" width="36" height="16" fill="black"/></svg>')
    assert panel.set_image_file(svg)
    img = pictures.decode(lbl.picture.image_png)
    assert img is not None and img.width > img.height


def test_panel_rejects_unreadable_file(qtbot, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    from PySide6.QtWidgets import QMessageBox

    from etiknivo.gui.properties_panel import PropertiesPanel

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a))
    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    lbl = _label(PictureKind.NONE)
    panel.set_label(lbl)
    bad = tmp_path / "kapot.jpg"
    bad.write_bytes(b"nee")
    assert not panel.set_image_file(bad)
    assert shown and lbl.picture.kind == PictureKind.NONE


def test_tight_label_with_qr_and_symbol_never_overlaps() -> None:
    """On a small label the symbol gives way and long lines are cut short,
    so nothing is printed over the QR code or the symbol."""
    from etiknivo.printing.profiles import FICHERO_5836

    eng = RenderEngine(FICHERO_5836.with_label(30, 12))
    lbl = make_label("A1", "Schuifpotmeters", "10 kΩ", "Mono · 75 / 88 mm")
    lbl.lines[0].text = "{Categorie}"
    lbl.code.kind = CodeKind.QR
    lbl.picture.kind, lbl.picture.symbol = PictureKind.SYMBOL, "connector"
    r = eng.render(lbl)
    bx0, _by0, bx1, _by1 = r.picture_box
    ink_right = bx0 + symbols.ink_box("connector")[2] * (bx1 - bx0)
    assert r.code is not None and bx0 + symbols.ink_box("connector")[0] * (bx1 - bx0) \
        >= r.code.box[2]
    assert all(lb.x0 >= ink_right and lb.x1 <= eng.printable_box[2] + 0.5 for lb in r.lines)
    assert any("ingekort" in w for w in r.warnings)
