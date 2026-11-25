"""Built-in test and calibration labels."""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from etiknivo.i18n import format_datetime, tr
from etiknivo.model import Label, LayoutPreset, make_label
from etiknivo.rendering.engine import RenderEngine
from etiknivo.rendering.fonts import FontRegistry, pil_font


def test_label(density_name: str = "") -> Label:
    """A normal label that exercises bold text and special characters."""
    lbl = make_label("", "Etiknivo test · " + format_datetime(datetime.now()), "10 kΩ · 4,7 µF",
                     "25 °C · ¼ W · 3×5" + (f" – {density_name}" if density_name else ""),
                     layout=LayoutPreset.CATEGORY_MAIN_SPEC)
    lbl.name = tr("Testlabel")
    return lbl


def calibration_raster(engine: RenderEngine) -> tuple[Image.Image, Image.Image]:
    """Calibration pattern.  Returns ``(mono_design, native_raster)``.

    The pattern marks the edge of the safe printable area, the centre lines
    and a millimetre ruler along both long edges.  The frame stays clear of
    the label edges, so all four sides are visible and the white space at
    both ends can be compared: when it is equal, the print is centred.
    Calibration offsets are applied, so after adjusting them a new test print
    verifies the result.
    """
    w, h = engine.design_size
    x0, y0, x1, y1 = engine.printable_box
    img = Image.new("1", (w, h), 1)
    d = ImageDraw.Draw(img)
    d.rectangle((x0, y0, x1 - 1, y1 - 1), outline=0)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    d.line((cx, y0, cx, y1 - 1), fill=0)
    d.line((x0, cy, x1 - 1, cy), fill=0)
    dpm = engine.profile.dots_per_mm
    for mm in range(0, (x1 - x0) // dpm + 1):
        x = min(x1 - 1, x0 + mm * dpm)
        ln = 8 if mm % 5 == 0 else 4
        d.line((x, y0, x, y0 + ln), fill=0)
        d.line((x, y1 - 1 - ln, x, y1 - 1), fill=0)
    font = pil_font(FontRegistry.fallback(True).path, 0, 14)
    cal = engine.calibration
    d.text((x0 + 12, cy - 18), "CAL", font=font, fill=0)
    small = pil_font(FontRegistry.fallback().path, 0, 11)
    d.text((x0 + 12, cy + 4), f"feed {cal.offset_feed_px:+d}", font=small, fill=0)
    d.text((x0 + 12, cy + 18), f"head {cal.offset_head_px:+d}", font=small, fill=0)
    d.text((cx + 6, cy - 18), "→ feed", font=small, fill=0)
    return img, engine.to_raster(img)


#: Nested frames of the edge test, one every millimetre from the edge inwards.
EDGE_TEST_FRAMES = 5


def edge_test_raster(engine: RenderEngine, extra_px: int = 0,
                     head_px: int | None = None) -> tuple[Image.Image, Image.Image]:
    """Edge test: measures how much of the raster really lands on the label.

    Returns ``(band, native_raster)``; *band* is the full printhead band over
    the whole label length in design orientation.  Unlike the calibration
    test it ignores the safe margins and every offset (built-in or set by the
    user): :data:`EDGE_TEST_FRAMES` nested frames are drawn 1 mm apart from the
    very first dot inwards, two dots thick.  Counting the frame lines that
    are visible on each side of the printed label shows how many millimetres
    are lost there; if all are visible, the white paper outside the outer
    frame is space the printhead cannot reach.

    *extra_px* makes the raster that many rows longer (negative: shorter) than
    the label, to see how the printer places a raster that is not label length.
    *head_px* sends a raster of that many dots across instead of the printhead
    width, to see whether the head has more dots than the profile uses.
    """
    p = engine.profile
    w, dpm = max(8 * p.dots_per_mm, p.label_length_px + extra_px), p.dots_per_mm
    h = head_px or p.printhead_px
    band = Image.new("1", (w, h), 1)
    d = ImageDraw.Draw(band)
    for k in range(EDGE_TEST_FRAMES):
        for t in (0, 1):
            i = k * dpm + t
            if 2 * i < min(w, h):
                d.rectangle((i, i, w - 1 - i, h - 1 - i), outline=0)
    inner = (EDGE_TEST_FRAMES - 1) * dpm + 2
    font = pil_font(FontRegistry.fallback(True).path, 0, 11)
    text = tr("▲ boven · randentest")
    tx0, ty0, tx1, ty1 = d.textbbox((0, 0), text, font=font)
    if tx1 - tx0 <= w - 2 * inner - 4 and ty1 - ty0 <= h - 2 * inner - 2:
        d.text(((w - (tx1 - tx0)) // 2 - tx0, (h - (ty1 - ty0)) // 2 - ty0), text,
               font=font, fill=0)
    raster = band.transpose(Image.Transpose.ROTATE_270 if engine.calibration.rotate_clockwise
                            else Image.Transpose.ROTATE_90)
    assert raster.size == (h, w), raster.size
    return band, raster
