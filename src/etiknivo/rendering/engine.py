"""The single render engine used for both preview and printing.

Coordinate systems
------------------
*Design orientation*: the label as the user sees it, landscape, 30 × 14 mm.
For the Fichero this is 240 × 112 dots (8 dots/mm).  Only the central band of
96 dots (the physical printhead width) can be printed; the remaining 8 dots on
each long edge are paper the head never touches.  Along the feed a safe margin
(2 mm at each end) is kept blank as well, because the label position is only
known to about a millimetre.

*Native raster*: what the printer receives: 96 dots wide (one printhead row)
× 240 rows (the label length).  The design image is rotated 90° to get there.

Pipeline
--------
1. Lay out the visible text lines in the printable band (minus margins),
   shrinking fonts when auto-fit is on.
2. Draw at ``supersample`` × resolution with antialiasing.
3. Downsample with a box filter (area average) to printer resolution.
4. Threshold to 1-bit.  This is the *exact* bitmap that will be printed.
5. Apply the printer's built-in feed offset plus the calibration offsets, crop
   the printhead band and rotate to the native raster.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageOps

from etiknivo.model import HAlign, Label, TextLine, VAlign
from etiknivo.printing.profiles import FICHERO_5836, PrinterProfile
from etiknivo.rendering.fonts import (
    FontFace,
    FontRegistry,
    default_registry,
    missing_glyphs,
    pil_font,
)
from etiknivo.settings import Calibration

log = logging.getLogger(__name__)

MIN_FONT_PT = 4.0  # below this text is no longer legible at 203 dpi
ITALIC_SHEAR = 0.2


@dataclass
class LineBox:
    """Where a line ended up, in design-orientation dots (printer resolution)."""

    slot: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size_pt: float
    requested_pt: float
    overflow: bool = False


@dataclass
class RenderResult:
    profile: PrinterProfile
    gray: Image.Image  # "L", full label, design orientation, printer resolution
    hires: Image.Image  # "L", full label at supersampled resolution (for the edit view)
    mono: Image.Image  # "1", full label, design orientation, exactly what prints (before calibration)
    raster: Image.Image  # "1", native printer orientation (e.g. 96 × 240), calibration applied
    lines: list[LineBox] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    content_box: tuple[float, float, float, float] = (0, 0, 0, 0)  # x0,y0,x1,y1 in dots

    @property
    def has_overflow(self) -> bool:
        return any(lb.overflow for lb in self.lines)

    def raster_bytes(self) -> bytes:
        """Packed raster for the printer: MSB first, 1 = black (heater on)."""
        return raster_to_bytes(self.raster)


def raster_to_bytes(img: Image.Image) -> bytes:
    """PIL mode '1' stores white as 1; the printer wants black as 1."""
    if img.mode != "1":
        raise ValueError(f"Verwacht mode '1', kreeg '{img.mode}'")
    return ImageOps.invert(img.convert("L")).convert("1").tobytes()


@dataclass
class _Prepared:
    slot: int
    line: TextLine
    face: FontFace
    text: str


class RenderEngine:
    """Renders :class:`Label` objects for a given printer profile."""

    def __init__(
        self,
        profile: PrinterProfile = FICHERO_5836,
        calibration: Calibration | None = None,
        fonts: FontRegistry | None = None,
    ) -> None:
        self.profile = profile
        self.calibration = calibration or Calibration()
        self.fonts = fonts or default_registry()

    # -- geometry ------------------------------------------------------------------

    @property
    def design_size(self) -> tuple[int, int]:
        return self.profile.label_length_px, self.profile.label_across_px

    @property
    def head_band(self) -> tuple[int, int, int, int]:
        """Full printhead band over the whole label length: (x0, y0, x1, y1)."""
        top = self.profile.printable_offset_px
        return 0, top, self.profile.label_length_px, top + self.profile.printable_across_px

    @property
    def printable_box(self) -> tuple[int, int, int, int]:
        """Safe printable area in design dots: the head band minus the feed margins."""
        x0, y0, x1, y1 = self.head_band
        m = self.profile.feed_margin_px
        return x0 + m, y0, x1 - m, y1

    def pt_to_px(self, pt: float) -> float:
        return pt * self.profile.dpi / 72.0

    def mm_to_px(self, mm: float) -> float:
        return mm * self.profile.dots_per_mm

    # -- public API ----------------------------------------------------------------

    def render(self, label: Label) -> RenderResult:
        ss = max(1, int(self.calibration.supersample))
        w, h = self.design_size
        px0, py0, px1, py1 = self.printable_box
        style = label.style
        mh, mv = self.mm_to_px(style.margin_h_mm), self.mm_to_px(style.margin_v_mm)
        content = (px0 + mh, py0 + mv, px1 - mh, py1 - mv)
        avail_w = max(1.0, content[2] - content[0])
        avail_h = max(1.0, content[3] - content[1])
        warnings: list[str] = []

        prepared = self._prepare_lines(label, warnings)
        sizes = [ln.line.font_size_pt for ln in prepared]
        spacing = self.mm_to_px(style.line_spacing_mm)

        if style.autofit and prepared:
            sizes = self._autofit(prepared, sizes, avail_w, avail_h, spacing)

        boxes = [self._measure(p, s) for p, s in zip(prepared, sizes)]
        heights = [b[3] - b[1] for b in boxes]
        block_h = sum(heights) + spacing * max(0, len(prepared) - 1)
        if style.valign == VAlign.TOP:
            y = content[1]
        elif style.valign == VAlign.BOTTOM:
            y = content[3] - block_h
        else:
            y = content[1] + (avail_h - block_h) / 2

        hires = Image.new("L", (w * ss, h * ss), 255)
        draw = ImageDraw.Draw(hires)
        line_boxes: list[LineBox] = []
        for p, size, bbox, lh in zip(prepared, sizes, boxes, heights):
            lw = bbox[2] - bbox[0]
            if p.line.align == HAlign.LEFT:
                x = content[0]
            elif p.line.align == HAlign.RIGHT:
                x = content[2] - lw
            else:
                x = content[0] + (avail_w - lw) / 2
            self._draw_line(hires, p, size, x - bbox[0], y - bbox[1], ss)
            overflow = (lw > avail_w + 0.5) or (x < px0 - 0.5) or (x + lw > px1 + 0.5) \
                or (y < py0 - 0.5) or (y + lh > py1 + 0.5)
            line_boxes.append(LineBox(p.slot, p.text, x, y, x + lw, y + lh, size,
                                      p.line.font_size_pt, overflow))
            y += lh + spacing

        if block_h > avail_h + 0.5:
            for lb in line_boxes:
                if lb.y0 < content[1] - 0.5 or lb.y1 > content[3] + 0.5:
                    lb.overflow = True
        for lb in line_boxes:
            if lb.overflow:
                warnings.append(f"Regel '{lb.text}' valt buiten het printbare gebied")
            elif lb.size_pt < lb.requested_pt - 0.05:
                pass  # shrunk to fit: expected behaviour, not a warning
        if style.autofit and any(lb.overflow for lb in line_boxes):
            warnings.append(f"Tekst past niet, zelfs niet bij de minimale lettergrootte "
                            f"({MIN_FONT_PT:g} pt). Kort de tekst in of verklein de marges.")
        if not prepared:
            warnings.append("Label bevat geen zichtbare tekst")

        if style.border:
            draw.rectangle((px0 * ss, py0 * ss, px1 * ss - 1, py1 * ss - 1), outline=0, width=ss)
        if style.rotation == 180:
            hires = hires.rotate(180)
        if style.invert:
            band = hires.crop((px0 * ss, py0 * ss, px1 * ss, py1 * ss))
            hires.paste(ImageOps.invert(band), (px0 * ss, py0 * ss))

        gray = hires.resize((w, h), Image.Resampling.BOX) if ss > 1 else hires.copy()
        mono = self.threshold(gray)
        # Paper outside the printhead can never be printed: blank it.
        mono = self._mask_unprintable(mono)
        raster = self.to_raster(mono)
        return RenderResult(self.profile, gray, hires, mono, raster, line_boxes, warnings, content)

    def threshold(self, gray: Image.Image) -> Image.Image:
        t = int(self.calibration.threshold)
        return gray.point(lambda v: 0 if v < t else 255, mode="1")

    def to_raster(self, mono: Image.Image) -> Image.Image:
        """Apply calibration, crop the printhead band and rotate to the native
        printer orientation (head width × label length)."""
        cal = self.calibration
        px0, py0, px1, py1 = self.head_band
        shifted = Image.new("1", mono.size, 1)
        feed = self.profile.feed_offset_px + int(cal.offset_feed_px)
        shifted.paste(mono, (feed, int(cal.offset_head_px)))
        band = shifted.crop((px0, py0, px1, py1))
        if band.height < self.profile.printhead_px:  # label narrower than the head
            padded = Image.new("1", (band.width, self.profile.printhead_px), 1)
            padded.paste(band, (0, (self.profile.printhead_px - band.height) // 2))
            band = padded
        # Counter-clockwise by default (top of the design → first dot of each row);
        # selectable in the calibration settings.
        raster = band.transpose(Image.Transpose.ROTATE_270 if cal.rotate_clockwise
                                else Image.Transpose.ROTATE_90)
        assert raster.size == self.profile.native_raster_size, raster.size
        return raster

    def raster_to_design(self, raster: Image.Image) -> Image.Image:
        """Inverse rotation of :meth:`to_raster` (for showing the band as designed)."""
        return raster.transpose(Image.Transpose.ROTATE_90 if self.calibration.rotate_clockwise
                                else Image.Transpose.ROTATE_270)

    def raster_on_label(self, raster: Image.Image) -> Image.Image:
        """The raster in design orientation as it lands on the label: the printer's
        built-in feed offset, which only compensates for where the printer starts
        printing, is undone so the preview shows the real position."""
        band = self.raster_to_design(raster)
        shift = self.profile.feed_offset_px
        if not shift:
            return band
        out = Image.new("1", band.size, 1)
        out.paste(band, (-shift, 0))
        return out

    # -- internals -----------------------------------------------------------------

    def _mask_unprintable(self, mono: Image.Image) -> Image.Image:
        px0, py0, px1, py1 = self.printable_box
        out = Image.new("1", mono.size, 1)
        out.paste(mono.crop((px0, py0, px1, py1)), (px0, py0))
        return out

    def _prepare_lines(self, label: Label, warnings: list[str]) -> list[_Prepared]:
        out: list[_Prepared] = []
        for slot, line in label.visible_lines():
            resolved, unknown = label.resolve(line.text)
            for name in unknown:
                warnings.append(f"Onbekend veld {{{name}}}: voeg '{name}' toe bij "
                                "Specificaties")
            text = " ".join(resolved.split("\n")).strip()
            face = self.fonts.resolve(line.font_family, line.bold, line.italic)
            missing = missing_glyphs(face, text)
            if missing:
                fb = self.fonts.fallback(line.bold, line.italic)
                if not missing_glyphs(fb, text):
                    warnings.append(f"Lettertype '{line.font_family}' mist teken(s) {missing}; "
                                    f"'{fb.family}' gebruikt voor deze regel")
                    face = fb
                else:
                    warnings.append(f"Teken(s) {missing} kunnen niet worden weergegeven")
            elif face.family != line.font_family:
                warnings.append(f"Lettertype '{line.font_family}' niet gevonden; "
                                f"'{face.family}' gebruikt")
            out.append(_Prepared(slot, line, face, text))
        return out

    def _font(self, p: _Prepared, size_pt: float, ss: int = 1):  # type: ignore[no-untyped-def]
        return pil_font(p.face.path, p.face.index, round(self.pt_to_px(size_pt) * ss * 4) / 4)

    def _stroke(self, p: _Prepared, size_pt: float, ss: int = 1) -> int:
        if not p.face.synthetic_bold:
            return 0
        return max(1, round(self.pt_to_px(size_pt) * ss * 0.04))

    def _measure(self, p: _Prepared, size_pt: float) -> tuple[float, float, float, float]:
        """Ink bounding box at printer resolution, relative to the baseline origin."""
        ss = 4  # measure at high resolution for sub-dot accuracy
        font = self._font(p, size_pt, ss)
        l, t, r, b = font.getbbox(p.text, anchor="ls", stroke_width=self._stroke(p, size_pt, ss))
        if p.face.synthetic_italic:
            r += (b - t) * ITALIC_SHEAR
        return l / ss, t / ss, r / ss, b / ss

    def _autofit(self, prepared: list[_Prepared], sizes: list[float], avail_w: float,
                 avail_h: float, spacing: float) -> list[float]:
        sizes = list(sizes)
        # 1. each line independently narrow enough
        for i, p in enumerate(prepared):
            for _ in range(12):
                l, _t, r, _b = self._measure(p, sizes[i])
                width = r - l
                if width <= avail_w or sizes[i] <= MIN_FONT_PT:
                    break
                sizes[i] = max(MIN_FONT_PT, sizes[i] * min(0.98, avail_w / width))
        # 2. whole block low enough: scale all lines together
        for _ in range(20):
            boxes = [self._measure(p, s) for p, s in zip(prepared, sizes)]
            total = sum(b[3] - b[1] for b in boxes) + spacing * (len(prepared) - 1)
            if total <= avail_h or all(s <= MIN_FONT_PT for s in sizes):
                break
            factor = min(0.98, max(0.5, (avail_h - spacing * (len(prepared) - 1))
                                   / max(1e-6, total - spacing * (len(prepared) - 1))))
            sizes = [max(MIN_FONT_PT, s * factor) for s in sizes]
        return sizes

    def _draw_line(self, canvas: Image.Image, p: _Prepared, size_pt: float, x: float, y: float,
                   ss: int) -> None:
        """Draw one line with its baseline origin at design position (x, y)."""
        font = self._font(p, size_pt, ss)
        stroke = self._stroke(p, size_pt, ss)
        if not p.face.synthetic_italic:
            ImageDraw.Draw(canvas).text((x * ss, y * ss), p.text, font=font, fill=0, anchor="ls",
                                        stroke_width=stroke, stroke_fill=0)
            return
        # Synthetic italic: render to a mask and shear it.
        l, t, r, b = font.getbbox(p.text, anchor="ls", stroke_width=stroke)
        hgt = int(b - t) + 2
        extra = int(hgt * ITALIC_SHEAR) + 2
        mask = Image.new("L", (int(r - l) + extra + 2, hgt), 0)
        ImageDraw.Draw(mask).text((-l + 1, -t + 1), p.text, font=font, fill=255, anchor="ls",
                                  stroke_width=stroke, stroke_fill=255)
        sheared = mask.transform(mask.size, Image.Transform.AFFINE,
                                 (1, ITALIC_SHEAR, -ITALIC_SHEAR * hgt, 0, 1, 0),
                                 resample=Image.Resampling.BILINEAR)
        canvas.paste(0, (int(x * ss + l - 1), int(y * ss + t - 1)), sheared)
