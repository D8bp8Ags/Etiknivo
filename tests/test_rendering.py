"""Render engine: raster size, orientation, special characters, overflow."""

from __future__ import annotations

import pytest
from PIL import Image

from etiknivo.model import HAlign, Label, LayoutPreset, make_label
from etiknivo.rendering import engine as engine_mod
from etiknivo.rendering.engine import RenderEngine, raster_to_bytes
from etiknivo.rendering.fonts import FontRegistry, missing_glyphs
from etiknivo.rendering.patterns import calibration_raster
from etiknivo.rendering.patterns import test_label as make_test_label
from etiknivo.settings import Calibration
from etiknivo.storage.library import seed_labels

SPECIAL = "Ω µ ° × ¼ – ″ ·"


def ink_bbox(img: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box of black pixels (works for mode '1' and 'L')."""
    inv = Image.eval(img.convert("L"), lambda v: 255 - v)
    return inv.getbbox()


def black_count(img: Image.Image) -> int:
    return img.convert("L").histogram()[0]


# -- geometry ---------------------------------------------------------------------------


def test_native_raster_is_96_by_240(engine: RenderEngine) -> None:
    r = engine.render(make_label("A01", "Schuifpotmeters", "10 kΩ", "Mono"))
    assert r.raster.mode == "1"
    assert r.raster.size == (96, 240)
    assert engine.profile.printhead_px == 96  # never the fictitious 112 px of 14 mm paper


def test_raster_bytes_layout(engine: RenderEngine) -> None:
    r = engine.render(make_label("", "", "X"))
    data = r.raster_bytes()
    assert len(data) == 12 * 240  # 12 bytes per 96-dot row, 240 rows
    black = Image.new("1", (96, 240), 0)
    assert raster_to_bytes(black) == b"\xff" * 2880  # 1 = heater on (black)
    white = Image.new("1", (96, 240), 1)
    assert raster_to_bytes(white) == b"\x00" * 2880


def test_design_canvas_and_printable_band(engine: RenderEngine) -> None:
    assert engine.design_size == (240, 112)  # 30 × 14 mm at 8 dots/mm
    assert engine.printable_box == (0, 8, 240, 104)  # central 96 dots
    r = engine.render(make_label("", "", "WWWWWWWWWWWW", "", layout=LayoutPreset.SINGLE))
    # nothing may be printed on paper outside the printhead
    assert ink_bbox(r.mono.crop((0, 0, 240, 8))) is None
    assert ink_bbox(r.mono.crop((0, 104, 240, 112))) is None


def test_mono_matches_raster_exactly(engine: RenderEngine) -> None:
    """The preview raster is exactly what gets sent (no calibration offset)."""
    r = engine.render(make_label("A09", "Weerstand", "150 Ω", "¼ W"))
    band = r.mono.crop(engine.printable_box)
    assert engine.raster_to_design(r.raster).tobytes() == band.tobytes()


# -- orientation --------------------------------------------------------------------------


def _left_aligned_label() -> Label:
    lbl = make_label("", "", "I", "", layout=LayoutPreset.SINGLE)
    lbl.main.align = HAlign.LEFT
    lbl.style.autofit = False
    lbl.main.font_size_pt = 10
    return lbl


def test_orientation_counter_clockwise_default(engine: RenderEngine) -> None:
    r = engine.render(_left_aligned_label())
    d = ink_bbox(r.mono)
    assert d is not None and d[2] < 40  # ink at the left of the design
    x0, y0, x1, y1 = ink_bbox(r.raster)
    # rotated 90° counter-clockwise: design-left → raster-bottom
    assert y0 > 200
    # design-top ↔ raster-left
    assert x0 < 48


def test_orientation_clockwise_option() -> None:
    eng = RenderEngine(calibration=Calibration(rotate_clockwise=True))
    r = eng.render(_left_aligned_label())
    _x0, _y0, _x1, y1 = ink_bbox(r.raster)
    assert y1 < 40  # design-left → raster-top
    assert eng.raster_to_design(r.raster).size == (240, 96)


def test_content_rotation_180(engine: RenderEngine) -> None:
    lbl = _left_aligned_label()
    lbl.style.rotation = 180
    d = ink_bbox(engine.render(lbl).mono)
    assert d[0] > 200  # now at the right edge


def test_calibration_offset_shifts_raster() -> None:
    lbl = _left_aligned_label()
    base = RenderEngine(calibration=Calibration()).render(lbl)
    shifted = RenderEngine(calibration=Calibration(offset_feed_px=10, offset_head_px=-3)).render(lbl)
    b0, b1 = ink_bbox(base.raster), ink_bbox(shifted.raster)
    assert b1[1] == b0[1] - 10  # feed +10 → 10 rows earlier in CCW raster
    assert b1[0] == b0[0] - 3


# -- text quality ---------------------------------------------------------------------------


def test_special_characters_are_supported(engine: RenderEngine) -> None:
    face = FontRegistry.fallback()
    assert missing_glyphs(face, SPECIAL) == ""
    assert missing_glyphs(FontRegistry.fallback(bold=True), SPECIAL) == ""
    r = engine.render(make_label("", "", "10 kΩ ¼ W", "25 °C · 3×5 – 1 MΩ · 4,7 µF · 0,85″"))
    assert not r.warnings
    # each special glyph renders its own distinct shape (no identical tofu boxes)
    shapes = set()
    for ch in "Ωµ°×¼–″":
        lbl = make_label("", "", ch, "", layout=LayoutPreset.SINGLE)
        lbl.style.autofit = False
        img = engine.render(lbl).mono
        assert black_count(img) > 10, ch
        shapes.add(img.tobytes())
    assert len(shapes) == 7


def test_missing_glyph_falls_back_to_dejavu(monkeypatch, engine: RenderEngine) -> None:
    calls = []

    def fake_missing(face, text):  # first face "lacks" Ω, fallback has everything
        calls.append(face.family)
        return "Ω" if len(calls) == 1 else ""

    monkeypatch.setattr(engine_mod, "missing_glyphs", fake_missing)
    r = engine.render(make_label("", "", "10 kΩ", "", layout=LayoutPreset.SINGLE))
    assert any("mist teken" in w for w in r.warnings)
    assert black_count(r.mono) > 50


def test_small_text_stays_legible(engine: RenderEngine) -> None:
    lbl = make_label("", "", "Small 5 pt text", "", layout=LayoutPreset.SINGLE)
    lbl.style.autofit = False
    lbl.main.bold = False
    lbl.main.font_size_pt = 5
    r = engine.render(lbl)
    bb = ink_bbox(r.mono)
    assert bb is not None and 6 <= bb[3] - bb[1] <= 20  # real glyphs, not a smear
    assert black_count(r.mono) > 60


def test_supersampling_produces_antialiased_gray(engine: RenderEngine) -> None:
    r = engine.render(make_label("", "", "Antialias", ""))
    grays = [v for v in r.gray.tobytes() if 0 < v < 255]
    assert grays, "box-filter downsampling must produce intermediate grey values"
    assert r.mono.mode == "1"


def test_threshold_controls_weight() -> None:
    lbl = make_label("", "", "Weight", "")
    light = RenderEngine(calibration=Calibration(threshold=80)).render(lbl)
    dark = RenderEngine(calibration=Calibration(threshold=200)).render(lbl)
    assert black_count(dark.mono) > black_count(light.mono)


# -- overflow / auto-fit -------------------------------------------------------------------


def test_long_text_autofits_without_clipping(engine: RenderEngine) -> None:
    lbl = make_label("", "Categorie", "Een heel erg lange onderdeelnaam", "Specificatie")
    r = engine.render(lbl)
    assert not r.has_overflow
    assert r.lines[1].size_pt < r.lines[1].requested_pt
    cx0, cy0, cx1, cy1 = r.content_box
    bb = ink_bbox(r.mono)
    assert bb[0] >= cx0 - 1 and bb[2] <= cx1 + 1
    assert bb[1] >= 8 and bb[3] <= 104


def test_overflow_detected_without_autofit(engine: RenderEngine) -> None:
    lbl = make_label("", "", "Een heel erg lange onderdeelnaam", "", layout=LayoutPreset.SINGLE)
    lbl.style.autofit = False
    r = engine.render(lbl)
    assert r.has_overflow
    assert any("buiten het printbare gebied" in w for w in r.warnings)


def test_too_much_text_warns_even_with_autofit(engine: RenderEngine) -> None:
    lbl = make_label("", "", "X" * 200, "", layout=LayoutPreset.SINGLE)
    r = engine.render(lbl)
    assert r.has_overflow
    assert any("minimale lettergrootte" in w for w in r.warnings)


def test_too_tall_block_overflows_vertically(engine: RenderEngine) -> None:
    lbl = make_label("", "Top", "Main", "Bottom")
    lbl.style.autofit = False
    for ln in lbl.lines:
        ln.font_size_pt = 16
    assert engine.render(lbl).has_overflow


@pytest.mark.parametrize("lbl", seed_labels(), ids=lambda lbl: lbl.tray_id)
def test_all_seed_labels_fit(engine: RenderEngine, lbl: Label) -> None:
    r = engine.render(lbl)
    assert r.raster.size == (96, 240)
    assert not r.has_overflow, r.warnings
    assert not r.warnings
    bb = ink_bbox(r.mono)
    assert 8 <= bb[1] and bb[3] <= 104  # nothing cut off at the printhead edge
    assert 0 < bb[0] and bb[2] < 240


def test_empty_label_warns(engine: RenderEngine) -> None:
    r = engine.render(Label())
    assert r.warnings and ink_bbox(r.mono) is None


def test_border_and_invert(engine: RenderEngine) -> None:
    lbl = make_label("", "", "B", "", layout=LayoutPreset.SINGLE)
    lbl.style.border = True
    r = engine.render(lbl)
    assert r.mono.getpixel((0, 8)) == 0 and r.mono.getpixel((239, 103)) == 0
    lbl.style.border = False
    lbl.style.invert = True
    inv = engine.render(lbl)
    assert black_count(inv.mono) > 240 * 96 // 2


def test_italic_and_bold_render(engine: RenderEngine) -> None:
    lbl = make_label("", "", "Stijl", "", layout=LayoutPreset.SINGLE)
    lbl.style.autofit = False
    lbl.main.font_size_pt = 12
    lbl.main.bold = False
    regular = engine.render(lbl).mono
    lbl.main.bold = True
    bold = engine.render(lbl).mono
    lbl.main.bold, lbl.main.italic = False, True
    italic = engine.render(lbl).mono
    assert black_count(bold) > black_count(regular)
    assert italic.tobytes() != regular.tobytes()


def test_test_and_calibration_patterns(engine: RenderEngine) -> None:
    r = engine.render(make_test_label("Normaal"))
    assert r.raster.size == (96, 240) and not r.has_overflow
    mono, raster = calibration_raster(engine)
    assert raster.size == (96, 240)
    # frame of the printable band is drawn
    assert mono.getpixel((0, 8)) == 0 and mono.getpixel((239, 103)) == 0
