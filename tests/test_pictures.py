"""Pictograms on labels: own symbols and the user's own images."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from etiknivo.model import CodeKind, HAlign, Label, PictureKind, make_label
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
    if side == HAlign.LEFT:
        assert min(lb.x0 for lb in r.lines) > px0 + 80
        assert r.mono.crop((px0, 0, px0 + 60, r.mono.height)).getextrema()[0] == 0  # ink
    else:
        assert max(lb.x1 for lb in r.lines) < px1 - 80
    assert plain.lines[1].size_pt >= r.lines[1].size_pt


def test_picture_and_qr_share_the_label() -> None:
    lbl = _label(PictureKind.SYMBOL, HAlign.LEFT)
    lbl.code.kind = CodeKind.QR
    lbl.code.side = HAlign.LEFT
    r = RenderEngine().render(lbl)
    assert r.code is not None
    # text sits right of both the QR code and the symbol
    assert min(lb.x0 for lb in r.lines) > r.code.box[2] + 40


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
    panel.pic_side.setCurrentIndex(1)
    assert (lbl.picture.kind, lbl.picture.symbol, lbl.picture.side) == (
        PictureKind.SYMBOL, "diode", HAlign.RIGHT)
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
