"""QR codes and Code 128 barcodes: encoders, layout on the label, GUI."""

from __future__ import annotations

import pytest
from PIL import Image

from etiknivo.model import SLOT_BOTTOM, CodeKind, HAlign, Label, make_label
from etiknivo.rendering import codes
from etiknivo.rendering.engine import RenderEngine

zxingcpp = pytest.importorskip("zxingcpp")


def _qr_image(matrix: list[list[bool]], scale: int = 4) -> Image.Image:
    n = len(matrix)
    img = Image.new("L", ((n + 8) * scale,) * 2, 255)
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                img.paste(0, ((c + 4) * scale, (r + 4) * scale, (c + 5) * scale, (r + 5) * scale))
    return img


def _bar_image(modules: list[bool], scale: int = 3) -> Image.Image:
    img = Image.new("L", ((len(modules) + 20) * scale, 60), 255)
    for i, bar in enumerate(modules):
        if bar:
            img.paste(0, ((i + 10) * scale, 5, (i + 11) * scale, 55))
    return img


def _read(img: Image.Image) -> list[str]:
    return [r.text for r in zxingcpp.read_barcodes(img)]


@pytest.mark.parametrize("text", ["A14", "1", "Ω µ 10 kΩ · ¼ W", "https://example.com/ne555",
                                  "x" * 60, "y" * codes.qr_capacity()])
def test_qr_reads_back(text: str) -> None:
    m = codes.qr_matrix(text)
    assert len(m) in (21, 25, 29, 33, 37, 41)
    assert _read(_qr_image(m)) == [text]


def test_qr_too_long() -> None:
    with pytest.raises(codes.CodeError):
        codes.qr_matrix("z" * (codes.qr_capacity() + 1))


@pytest.mark.parametrize("text", ["A14", "12", "9", "1234", "12345", "ABC123456", "B-07 1k",
                                  "000123456789X", "a1b2c3"])
def test_code128_reads_back(text: str) -> None:
    mods = codes.code128_modules(text)
    assert len(mods) % 11 == 2  # symbols of 11 modules plus a stop of 13
    assert _read(_bar_image(mods)) == [text]


def test_code128_digits_are_compact() -> None:
    assert len(codes.code128_modules("12345678")) < len(codes.code128_modules("ABCDEFGH"))


def test_code128_rejects_unsupported() -> None:
    with pytest.raises(codes.CodeError):
        codes.code128_modules("10 kΩ")


def _label(kind: CodeKind, text: str = "{Lade}", side: HAlign = HAlign.LEFT) -> Label:
    lbl = make_label("A14", "Antennes", "2,4 GHz", "Wi-Fi · u.FL")
    lbl.code.kind, lbl.code.text, lbl.code.side = kind, text, side
    return lbl


def _decoded(engine: RenderEngine, lbl: Label) -> list[str]:
    mono = engine.render(lbl).mono.convert("L")
    return _read(mono.resize((mono.width * 4, mono.height * 4), Image.Resampling.NEAREST))


@pytest.mark.parametrize("side", [HAlign.LEFT, HAlign.RIGHT])
def test_qr_on_label_scans_and_text_moves_aside(side: HAlign) -> None:
    eng = RenderEngine()
    lbl = _label(CodeKind.QR, "https://example.com/ne555", side)
    r = eng.render(lbl)
    assert not r.warnings and r.code is not None and r.code.module_px >= 2
    x0, _y0, x1, _y1 = r.code.box
    px0, py0, px1, py1 = eng.printable_box
    assert px0 <= x0 and x1 <= px1 and py0 <= r.code.box[1] and r.code.box[3] <= py1
    for lb in r.lines:
        assert lb.x1 <= x0 if side == HAlign.RIGHT else lb.x0 >= x1
    assert _decoded(eng, lbl) == ["https://example.com/ne555"]


def test_barcode_replaces_bottom_line_and_scans() -> None:
    eng = RenderEngine()
    lbl = _label(CodeKind.CODE128)
    r = eng.render(lbl)
    assert not r.warnings
    assert SLOT_BOTTOM not in {lb.slot for lb in r.lines}
    assert lbl.bottom.text == "Wi-Fi · u.FL"  # kept for when the barcode is switched off
    assert all(lb.y1 <= r.code.box[1] for lb in r.lines)
    assert _decoded(eng, lbl) == ["A14"]


def test_barcode_alone_uses_full_height() -> None:
    eng = RenderEngine()
    lbl = make_label("A14", "", "")
    lbl.code.kind = CodeKind.CODE128
    r = eng.render(lbl)
    assert r.code.box[3] - r.code.box[1] > 60 and not r.warnings


def test_code_warnings() -> None:
    eng = RenderEngine()
    assert any("Ω" in w for w in eng.render(_label(CodeKind.CODE128, "10 kΩ")).warnings)
    assert any("Spanning" in w for w in eng.render(_label(CodeKind.QR, "{Spanning}")).warnings)
    assert eng.render(_label(CodeKind.QR, "{Spanning}")).code is None
    assert any("leeg" in w for w in eng.render(_label(CodeKind.QR, " ")).warnings)
    long = eng.render(_label(CodeKind.QR, "x" * 500))
    assert long.code is None and long.warnings


def test_code_follows_fields_and_survives_json() -> None:
    lbl = _label(CodeKind.QR, "{Datasheet}", HAlign.RIGHT)
    lbl.specs["Datasheet"] = "https://example.com/a"
    key = lbl.render_key()
    back = Label.from_dict(lbl.to_dict())
    assert (back.code.kind, back.code.text, back.code.side) == (CodeKind.QR, "{Datasheet}",
                                                                 HAlign.RIGHT)
    lbl.specs["Datasheet"] = "https://example.com/b"
    assert lbl.render_key() != key
    assert Label.from_dict({"code": {"kind": "onbekend"}}).code.kind == CodeKind.NONE
    assert Label.from_dict({}).code.kind == CodeKind.NONE


def test_properties_panel_sets_code(qtbot) -> None:  # noqa: ANN001
    from etiknivo.gui.properties_panel import PropertiesPanel

    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    lbl = _label(CodeKind.NONE)
    panel.set_label(lbl)
    assert not panel.code_text.isEnabled()
    panel.code_kind.setCurrentIndex(2)  # QR right
    assert (lbl.code.kind, lbl.code.side) == (CodeKind.QR, HAlign.RIGHT)
    panel.code_kind.setCurrentIndex(3)  # barcode
    assert lbl.code.kind == CodeKind.CODE128
    assert "barcode" in panel.lines[SLOT_BOTTOM].note.text()
    panel.code_text.setText("")
    panel.code_field_btn.insert_field("Naam")
    assert lbl.code.text == "{Naam}"
    other = _label(CodeKind.QR, side=HAlign.LEFT)
    panel.set_label(other)
    assert panel.code_kind.currentIndex() == 1
    assert "barcode" not in panel.lines[SLOT_BOTTOM].title()


def test_about_hides_home_folder(tmp_path) -> None:  # noqa: ANN001
    from pathlib import Path

    from etiknivo.gui.dialogs import short_path

    assert short_path(Path.home() / "Library" / "Logs") == "~/Library/Logs"
    assert short_path(Path("/opt/x")) == str(Path("/opt/x"))
