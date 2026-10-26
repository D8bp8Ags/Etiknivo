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
