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
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace

from PIL import Image, ImageChops, ImageDraw, ImageOps

from etiknivo.i18n import tr
from etiknivo.model import (
    CodeKind,
    CodeSize,
    ElementKind,
    HAlign,
    Label,
    LabelElement,
    PictureKind,
    TextLine,
    VAlign,
)
from etiknivo.printing.profiles import FICHERO_5836, PrinterProfile
from etiknivo.rendering import codes, pictures, symbols
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
#: a label whose text needs this much less than the median of its category keeps
#: its own size instead of making the whole category smaller
SHARED_OUTLIER_PT = 1.0
QR_MAX_MODULE_PX = 4  # 0.5 mm per module is plenty for a phone camera
QR_MIN_MODULE_PX = 2  # smaller modules (0.125 mm) do not scan reliably
#: largest module per QR size choice: 0.25, 0.375 and 0.5 mm
QR_SIZE_MODULE_PX = {CodeSize.SMALL: 2, CodeSize.MEDIUM: 3, CodeSize.LARGE: QR_MAX_MODULE_PX}
QR_GAP_MM = 1.5  # between QR code and text: room for the quiet zone
BAR_MAX_MODULE_PX = 3
BAR_HEIGHT_MM = 3.5
BAR_GAP_MM = 0.75
PICTURE_GAP_MM = 1.0
PICTURE_MAX_WIDTH = 0.5  # share of the room left for text
#: size a pictogram takes per size choice (share of the content height); the
#: same on every label, whatever the text: the text makes room, not the pictogram
PICTURE_SCALE = {CodeSize.SMALL: 0.4, CodeSize.MEDIUM: 0.6, CodeSize.LARGE: 0.85}
SEPARATOR_GAP_PX = 3  # minimum line gap with separators: white, line, white
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
    #: "shared": made smaller to match the rest of the category; "own": the
    #: category shares a larger size, but this text needs a smaller one
    shared: str = ""


@dataclass(frozen=True)
class CategoryShare:
    """What the labels of one category share so they look alike (see
    :meth:`RenderEngine.category_share`)."""

    #: largest font size per line slot
    sizes: tuple[tuple[int, float], ...] = ()
    #: per line slot the room above and below the baseline, as a share of the
    #: font size: the highest ascender and lowest descender in the category, so
    #: every label puts its baselines in the same place ("Zwart" and "Gemengd")
    extents: tuple[tuple[int, float, float], ...] = ()

    def cap(self, slot: int) -> float | None:
        return dict(self.sizes).get(slot)

    def extent(self, slot: int) -> tuple[float, float] | None:
        for s, top, bottom in self.extents:
            if s == slot:
                return top, bottom
        return None


@dataclass
class PlacedCode:
    """A QR code or barcode laid out in whole printer dots."""

    kind: CodeKind
    text: str
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 in design dots
    module_px: int
    rects: list[tuple[int, int, int, int]]  # dark areas, design dots
    text_area: tuple[float, float, float, float]  # what is left for the text lines


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
    code: PlacedCode | None = None
    picture_box: tuple[int, int, int, int] | None = None
    text_area: tuple[float, float, float, float] = (0, 0, 0, 0)  # room the lines had
    #: free layout: element id -> its box in design dots
    element_boxes: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)

    @property
    def has_overflow(self) -> bool:
        return any(lb.overflow for lb in self.lines)

    def raster_bytes(self) -> bytes:
        """Packed raster for the printer: MSB first, 1 = black (heater on)."""
        return raster_to_bytes(self.raster)


def raster_to_bytes(img: Image.Image) -> bytes:
    """PIL mode '1' stores white as 1; the printer wants black as 1."""
    if img.mode != "1":
        raise ValueError(tr("Verwacht mode '1', kreeg '{mode}'", mode=img.mode))
    return ImageOps.invert(img.convert("L")).convert("1").tobytes()



def _warn_unknown(names: list[str], warnings: list[str]) -> None:
    for name in names:
        warnings.append(tr("Onbekend veld {{{name}}}: voeg '{name}' toe bij "
                           "Specificaties", name=name))


def _code_text(label: Label, text: str, warnings: list[str]) -> str | None:
    """What a QR code or barcode contains, or None (with a warning) when there
    is nothing sensible to encode."""
    resolved, unknown = label.resolve(text)
    _warn_unknown(unknown, warnings)
    if unknown:  # a code with "{Name}" in it would scan as nonsense: leave it out
        return None
    resolved = resolved.strip()
    if not resolved:
        warnings.append(tr("De code is leeg: vul de tekst voor de code in"))
        return None
    return resolved


def _qr_matrix(text: str, warnings: list[str]) -> list[list[bool]] | None:
    try:
        return codes.qr_matrix(text)
    except codes.CodeError:
        warnings.append(tr("Tekst is te lang voor een QR-code (maximaal {n} tekens)",
                           n=codes.qr_capacity()))
        return None


def _barcode_modules(text: str, warnings: list[str]) -> list[bool] | None:
    try:
        return codes.code128_modules(text)
    except codes.CodeError as e:
        warnings.append(tr("Teken(s) {chars} kunnen niet in een barcode; gebruik "
                           "letters, cijfers en leestekens zonder accenten", chars=str(e)))
        return None


def _bar_module(module: int, warnings: list[str]) -> int:
    """Width of one barcode module in dots, with a warning when it is too thin."""
    if module < 1:
        warnings.append(tr("Tekst is te lang voor een barcode op dit etiket"))
    elif module == 1:
        warnings.append(tr("De barcode heeft erg dunne streepjes; kort de tekst in als "
                           "hij slecht scant"))
    return module

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
        #: the other labels, so a category can share its font sizes
        #: (see :meth:`category_share`); None renders every label on its own
        self.peers: Callable[[], Iterable[Label]] | None = None
        self._own_fit: dict[tuple, dict[int, float]] = {}
        self._extent_cache: dict[tuple, tuple[float, float]] = {}
        self._share_cache: dict[tuple, CategoryShare] = {}

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
        return self._render(label, self.category_share(label))

    def category_share(self, label: Label) -> CategoryShare | None:
        """What the label shares with its category, or None when it lays out
        its text on its own.

        Every label in the category that has auto-fit with "same size in the
        category" on gets, so a drawer cabinet looks even:

        * per line the same room above and below the baseline, so lines sit
          at the same height whatever letters they hold;
        * per line the smallest font size any of them needs.  Only lines
          with the same chosen size are compared.  A label that needs much
          less than the others (more than :data:`SHARED_OUTLIER_PT` under the
          median) keeps its own smaller size rather than pulling the whole
          category down."""
        if self.peers is None or not _shares_sizes(label):
            return None
        group = [label] + [p for p in self.peers()
                           if p.id != label.id and p.category == label.category
                           and _shares_sizes(p)]
        if len(group) < 2:
            return None
        key = (tuple(m.render_key() for m in group), self.profile,
               self.calibration.supersample)
        if key not in self._share_cache:
            if len(self._share_cache) > 2000:
                self._share_cache.clear()
            self._share_cache[key] = self._share_of(label, group)
        return self._share_cache[key]

    def _share_of(self, label: Label, group: list[Label]) -> CategoryShare:
        extents = self._group_extents(group)
        share = CategoryShare(extents=extents)
        fits = [self._own_fit_of(m, share) for m in group]
        caps: dict[int, float] = {}
        for slot in fits[0]:
            want = label.lines[slot].font_size_pt
            sizes = sorted(f[slot] for m, f in zip(group, fits)
                           if slot in f and abs(m.lines[slot].font_size_pt - want) < 0.01)
            if len(sizes) < 2:
                continue
            median = sizes[(len(sizes) - 1) // 2]
            caps[slot] = min(s for s in sizes if s >= median - SHARED_OUTLIER_PT)
        return replace(share, sizes=tuple(sorted(caps.items())))

    def size_caps(self, label: Label) -> dict[int, float] | None:
        """The shared font size per line slot (see :meth:`category_share`)."""
        share = self.category_share(label)
        return dict(share.sizes) or None if share else None

    def _group_extents(self, group: list[Label]) -> tuple[tuple[int, float, float], ...]:
        """Per slot the highest top and lowest bottom of the ink in the
        group, relative to the baseline and as a share of the font size."""
        found: dict[int, tuple[float, float]] = {}
        for m in group:
            for slot, line in m.visible_lines():
                p = self._prepare_text(m, slot, line, [])
                if not p.text:
                    continue
                top, bottom = self._extent(p)
                old = found.get(slot)
                found[slot] = (top, bottom) if old is None else (min(old[0], top),
                                                                  max(old[1], bottom))
        return tuple((slot, round(t, 3), round(b, 3)) for slot, (t, b) in sorted(found.items()))

    def _extent(self, p: _Prepared) -> tuple[float, float]:
        """Ink top and bottom of a line relative to its baseline, per point."""
        key = (p.face.path, p.face.index, p.face.synthetic_bold, p.text)
        hit = self._extent_cache.get(key)
        if hit is None:
            if len(self._extent_cache) > 20000:
                self._extent_cache.clear()
            ref = 20.0
            _l, t, _r, b = self._measure(p, ref)
            hit = (t / ref, b / ref)
            self._extent_cache[key] = hit
        return hit

    def _own_fit_of(self, label: Label, share: CategoryShare) -> dict[int, float]:
        """The font size per slot the label gets with the category's line
        extents but its own sizes."""
        key = (label.render_key(), share, self.profile, self.calibration.supersample)
        hit = self._own_fit.get(key)
        if hit is None:
            if len(self._own_fit) > 4000:
                self._own_fit.clear()
            r = self._render(label, share)
            hit = {lb.slot: lb.size_pt for lb in r.lines}
            self._own_fit[key] = hit
        return hit

    def _render(self, label: Label, share: CategoryShare | None) -> RenderResult:
        if label.is_free:
            return self._render_free(label)
        if label.style.rotation in (90, 270):
            return self._render_turned(label, share)
        ss = max(1, int(self.calibration.supersample))
        w, h = self.design_size
        px0, py0, px1, py1 = self.printable_box
        style = label.style
        mh, mv = self.mm_to_px(style.margin_h_mm), self.mm_to_px(style.margin_v_mm)
        content = (px0 + mh, py0 + mv, px1 - mh, py1 - mv)
        warnings: list[str] = []

        prepared = self._prepare_lines(label, warnings)
        sizes = [ln.line.font_size_pt for ln in prepared]
        spacing = self.mm_to_px(style.line_spacing_mm)
        if style.separators and len(prepared) > 1:
            spacing = max(spacing, SEPARATOR_GAP_PX)  # room for the line and white around it
        code: PlacedCode | None
        stack = self._fit_stack(label, content, warnings) if is_stacked(label) else None
        if stack is not None:
            code, picture = stack
            area = picture[2]
        else:
            code = self._place_code(label, content, bool(prepared), warnings)
            area = code.text_area if code else content
            picture = self._place_picture(label, area, warnings,
                                          PICTURE_SCALE[label.picture.size])
            if picture is not None:
                area = picture[2]
        avail_w = max(1.0, area[2] - area[0])
        avail_h = max(1.0, area[3] - area[1])

        if style.autofit and prepared:
            sizes = self._autofit(prepared, sizes, avail_w, avail_h, spacing, share)
        shared = [""] * len(prepared)
        for n, p in enumerate(prepared):
            cap = share.cap(p.slot) if share else None
            if cap is None:
                continue
            if sizes[n] > cap + 0.05:
                sizes[n], shared[n] = cap, "shared"
            elif sizes[n] < cap - 0.05:
                shared[n] = "own"

        # A line that is still too wide is cut short with "…" rather than
        # printed over the code or pictogram; it still gets a warning.
        cut = {n: p.text for n, p in enumerate(prepared)
               if self._width(p, sizes[n]) > avail_w + 0.5}
        prepared = [self._shorten(p, sizes[n], avail_w) if n in cut else p
                    for n, p in enumerate(prepared)]
        boxes = [self._vbox(p, s, share) for p, s in zip(prepared, sizes)]
        heights = [b[3] - b[1] for b in boxes]
        block_h = sum(heights) + spacing * max(0, len(prepared) - 1)
        if style.valign == VAlign.TOP:
            y = area[1]
        elif style.valign == VAlign.BOTTOM:
            y = area[3] - block_h
        else:
            y = area[1] + (avail_h - block_h) / 2

        hires = Image.new("L", (w * ss, h * ss), 255)
        draw = ImageDraw.Draw(hires)
        line_boxes: list[LineBox] = []
        for n, (p, size, bbox, lh) in enumerate(zip(prepared, sizes, boxes, heights)):
            if n and style.separators:
                mid = round(y - spacing / 2 - 0.5)  # one dot, centred in the gap
                draw.rectangle((round(area[0]) * ss, mid * ss, round(area[2]) * ss - 1,
                                (mid + 1) * ss - 1), fill=0)
            lw = bbox[2] - bbox[0]
            if p.line.align == HAlign.LEFT:
                x = area[0]
            elif p.line.align == HAlign.RIGHT:
                x = area[2] - lw
            else:
                x = area[0] + (avail_w - lw) / 2
            self._draw_line(hires, p, size, x - bbox[0], y - bbox[1], ss)
            overflow = (n in cut) or (lw > avail_w + 0.5) or (x < area[0] - 0.5) \
                or (x + lw > area[2] + 0.5) or (y < py0 - 0.5) or (y + lh > py1 + 0.5)
            line_boxes.append(LineBox(p.slot, cut.get(n, p.text), x, y, x + lw, y + lh, size,
                                      p.line.font_size_pt, overflow, shared[n]))
            y += lh + spacing

        if block_h > avail_h + 0.5:
            for lb in line_boxes:
                if lb.y0 < area[1] - 0.5 or lb.y1 > area[3] + 0.5:
                    lb.overflow = True
        for n, lb in enumerate(line_boxes):
            if n in cut:
                warnings.append(tr("Regel '{text}' past niet en is ingekort", text=lb.text))
            elif lb.overflow:  # shrinking to fit is expected and not worth a warning
                warnings.append(tr("Regel '{text}' valt buiten het printbare gebied",
                                   text=lb.text))
        if style.autofit and any(lb.overflow for lb in line_boxes):
            warnings.append(tr("Tekst past niet, zelfs niet bij de minimale lettergrootte "
                               "({pt} pt). Kort de tekst in of verklein de marges.",
                               pt=f"{MIN_FONT_PT:g}"))
        if not prepared and code is None and picture is None:
            warnings.append(tr("Label bevat geen zichtbare tekst"))
        if picture is not None:
            self._draw_picture(hires, picture[0], picture[1], ss)
        if code is not None:
            for x0, y0, x1, y1 in code.rects:
                draw.rectangle((x0 * ss, y0 * ss, x1 * ss - 1, y1 * ss - 1), fill=0)

        if style.rotation == 180:
            hires = hires.rotate(180)
        result = self._finish(hires, label, ss, line_boxes, warnings, content, code)
        result.picture_box = picture[0] if picture is not None else None
        result.text_area = area
        return result

    def _finish(self, hires: Image.Image, label: Label, ss: int, line_boxes: list[LineBox],
                warnings: list[str], content: tuple[float, float, float, float],
                code: PlacedCode | None) -> RenderResult:
        """Border, inversion, downsampling, 1-bit and the printer raster."""
        style = label.style
        w, h = self.design_size
        px0, py0, px1, py1 = self.printable_box
        if style.border:
            ImageDraw.Draw(hires).rectangle((px0 * ss, py0 * ss, px1 * ss - 1, py1 * ss - 1),
                                            outline=0, width=ss)
        if style.invert:
            band = hires.crop((px0 * ss, py0 * ss, px1 * ss, py1 * ss))
            hires.paste(ImageOps.invert(band), (px0 * ss, py0 * ss))

        gray = hires.resize((w, h), Image.Resampling.BOX) if ss > 1 else hires.copy()
        mono = self.threshold(gray)
        # Paper outside the printhead can never be printed: blank it.
        mono = self._mask_unprintable(mono)
        raster = self.to_raster(mono)
        return RenderResult(self.profile, gray, hires, mono, raster, line_boxes, warnings, content,
                            code)

    # -- free layout -------------------------------------------------------------------

    def element_box(self, el: LabelElement) -> tuple[float, float, float, float]:
        """An element's box in design dots."""
        px0, py0 = self.printable_box[:2]
        x0, y0 = px0 + self.mm_to_px(el.x_mm), py0 + self.mm_to_px(el.y_mm)
        return x0, y0, x0 + self.mm_to_px(el.w_mm), y0 + self.mm_to_px(el.h_mm)

    def _render_free(self, label: Label) -> RenderResult:
        """Free layout: every element in its own box."""
        ss = max(1, int(self.calibration.supersample))
        w, h = self.design_size
        px0, py0, px1, py1 = self.printable_box
        hires = Image.new("L", (w * ss, h * ss), 255)
        draw = ImageDraw.Draw(hires)
        warnings: list[str] = []
        line_boxes: list[LineBox] = []
        boxes: dict[str, tuple[float, float, float, float]] = {}
        for n, el in enumerate(label.elements):
            box = self.element_box(el)
            boxes[el.id] = box
            bx0, by0, bx1, by1 = box
            # for text, symbols and images the ink counts, not the box
            if el.kind == ElementKind.TEXT:
                lb = self._free_text(hires, label, n, el, box, ss, warnings)
                if lb is not None:
                    line_boxes.append(lb)
                    bx0, by0, bx1, by1 = lb.x0, lb.y0, lb.x1, lb.y1
                else:
                    bx0, by0, bx1, by1 = px0, py0, px0, py0
            elif el.kind in (ElementKind.SYMBOL, ElementKind.IMAGE):
                bx0, by0, bx1, by1 = (self._free_picture(hires, el, box, ss, warnings)
                                      or (px0, py0, px0, py0))
            if bx0 < px0 - 0.5 or by0 < py0 - 0.5 or bx1 > px1 + 0.5 or by1 > py1 + 0.5:
                warnings.append(tr("{element} valt deels buiten het printbare gebied",
                                   element=el.title))
            if el.kind in (ElementKind.TEXT, ElementKind.SYMBOL, ElementKind.IMAGE):
                continue
            if el.kind in (ElementKind.QR, ElementKind.BARCODE):
                for x0, y0, x1, y1 in self._free_code(label, el, box, warnings):
                    draw.rectangle((x0 * ss, y0 * ss, x1 * ss - 1, y1 * ss - 1), fill=0)
            else:
                ix0, iy0 = round(bx0), round(by0)
                ix1, iy1 = max(ix0 + 1, round(bx1)), max(iy0 + 1, round(by1))
                if el.kind == ElementKind.LINE:
                    draw.rectangle((ix0 * ss, iy0 * ss, ix1 * ss - 1, iy1 * ss - 1), fill=0)
                else:
                    draw.rectangle((ix0 * ss, iy0 * ss, ix1 * ss - 1, iy1 * ss - 1),
                                   outline=0, width=ss)
        if not label.elements:
            warnings.append(tr("Label bevat geen elementen: voeg er een toe"))
        for lb in line_boxes:
            if lb.overflow:
                warnings.append(tr("Tekst '{text}' past niet in zijn vak, zelfs niet bij de "
                                   "minimale lettergrootte", text=lb.text))
        # no rotation: elements are placed exactly where they should print
        result = self._finish(hires, label, ss, line_boxes, warnings,
                              (px0, py0, px1, py1), None)
        result.element_boxes = boxes
        return result

    def _free_text(self, canvas: Image.Image, label: Label, n: int, el: LabelElement,
                   box: tuple[float, float, float, float], ss: int,
                   warnings: list[str]) -> LineBox | None:
        p = self._prepare_text(label, n, el.as_line(), warnings)
        if not p.text:
            return None
        bx0, by0, bx1, by1 = box
        bw, bh = bx1 - bx0, by1 - by0
        size = el.font_size_pt
        for _ in range(24):
            l, t, r, b = self._measure(p, size)
            tw, th = r - l, b - t
            if (tw <= bw and th <= bh) or size <= MIN_FONT_PT:
                break
            size = max(MIN_FONT_PT, size * min(0.98, bw / max(tw, 1e-6), bh / max(th, 1e-6)))
        l, t, r, b = self._measure(p, size)
        tw, th = r - l, b - t
        if el.align == HAlign.LEFT:
            x = bx0
        elif el.align == HAlign.RIGHT:
            x = bx1 - tw
        else:
            x = bx0 + (bw - tw) / 2
        y = by0 + (bh - th) / 2
        self._draw_line(canvas, p, size, x - l, y - t, ss)
        return LineBox(n, p.text, x, y, x + tw, y + th, size, el.font_size_pt,
                       tw > bw + 0.5 or th > bh + 0.5)

    def _free_code(self, label: Label, el: LabelElement, box: tuple[float, float, float, float],
                   warnings: list[str]) -> list[tuple[int, int, int, int]]:
        text = _code_text(label, el.text, warnings)
        if text is None:
            return []
        bx0, by0, bx1, by1 = box
        if el.kind == ElementKind.QR:
            matrix = _qr_matrix(text, warnings)
            if matrix is None:
                return []
            n = len(matrix)
            module = int(min(bx1 - bx0, by1 - by0) // n)
            if module < QR_MIN_MODULE_PX:
                warnings.append(tr("QR-code wordt te klein om te scannen; kort de tekst in"))
                module = max(1, module)
            size = n * module
            x0 = round(bx0 + (bx1 - bx0 - size) / 2)
            y0 = round(by0 + (by1 - by0 - size) / 2)
            return [(x0 + c * module, y0 + r * module, x0 + (c + 1) * module,
                     y0 + (r + 1) * module)
                    for r, row in enumerate(matrix) for c, dark in enumerate(row) if dark]
        modules = _barcode_modules(text, warnings)
        if modules is None:
            return []
        module = _bar_module(int((bx1 - bx0) // len(modules)), warnings)
        if module < 1:
            return []
        x0 = round(bx0 + (bx1 - bx0 - len(modules) * module) / 2)
        y0, y1 = round(by0), max(round(by0) + 1, round(by1))
        return [(x0 + i * module, y0, x0 + (i + 1) * module, y1)
                for i, bar in enumerate(modules) if bar]

    def _free_picture(self, canvas: Image.Image, el: LabelElement,
                      box: tuple[float, float, float, float], ss: int,
                      warnings: list[str]) -> tuple[float, float, float, float] | None:
        """Draws the symbol or image of *el*; returns its ink box in design
        dots, or None when there is nothing to draw."""
        bx0, by0, bx1, by1 = box
        if el.kind == ElementKind.SYMBOL:
            if el.symbol not in symbols.SYMBOLS:
                warnings.append(tr("Kies een symbool"))
                return None
            return self._free_symbol(canvas, el.symbol, box, ss)
        img = pictures.decode(el.image_png)
        if img is None:
            warnings.append(tr("Geen afbeelding gekozen"))
            return None
        w, h = _fit(bx1 - bx0, by1 - by0, img.width / max(1, img.height))
        x0 = round(bx0 + (bx1 - bx0 - w) / 2)
        y0 = round(by0 + (by1 - by0 - h) / 2)
        iw, ih = max(1, round(w)), max(1, round(h))
        ink = self._draw_picture(canvas, (x0, y0, x0 + iw, y0 + ih), img, ss)
        return tuple(v / ss for v in ink) if ink else None  # type: ignore[return-value]

    @staticmethod
    def _free_symbol(canvas: Image.Image, key: str, box: tuple[float, float, float, float],
                     ss: int) -> tuple[float, float, float, float] | None:
        """A free symbol fills its box: the white space around the drawing
        is left out, so the box is what prints."""
        fx0, fy0, fx1, fy1 = symbols.ink_box(key)
        bx0, by0, bx1, by1 = box
        w, h = _fit(bx1 - bx0, by1 - by0, (fx1 - fx0) / (fy1 - fy0))
        size = max(1, round(max(w / (fx1 - fx0), h / (fy1 - fy0)) * ss))
        img = symbols.draw_symbol(key, size)
        ox = round((bx0 + (bx1 - bx0 - w) / 2) * ss - fx0 * size)
        oy = round((by0 + (by1 - by0 - h) / 2) * ss - fy0 * size)
        region = canvas.crop((ox, oy, ox + size, oy + size))
        canvas.paste(ImageChops.darker(region, img), (ox, oy))
        ink = ImageOps.invert(img).point(lambda v: 255 if v >= 128 else 0).getbbox()
        if not ink:
            return None
        return ((ox + ink[0]) / ss, (oy + ink[1]) / ss, (ox + ink[2]) / ss, (oy + ink[3]) / ss)

    def to_elements(self, label: Label) -> list[LabelElement]:
        """Loose elements that look like *label* does now: the starting point
        when a label switches to the free layout."""
        if label.is_free:
            return [replace(el) for el in label.elements]
        flat = label.clone(new_id=False)
        flat.style.rotation = 0
        r = self.render(flat)
        px0, py0 = self.printable_box[:2]
        dpm = self.profile.dots_per_mm

        def make(kind: ElementKind, box: tuple[float, float, float, float],
                 **kw: object) -> LabelElement:
            x0, y0, x1, y1 = box
            el = LabelElement(kind, **kw)  # type: ignore[arg-type]
            el.move_to((x0 - px0) / dpm, (y0 - py0) / dpm)
            el.resize((x1 - x0) / dpm, (y1 - y0) / dpm)
            return el

        out: list[LabelElement] = []
        for lb in r.lines:
            line = label.lines[lb.slot]
            pad = 1.0  # a dot of air around the ink, so the size stays the same
            out.append(make(ElementKind.TEXT, (lb.x0 - pad, lb.y0 - pad, lb.x1 + pad,
                                               lb.y1 + pad),
                            text=line.text, font_family=line.font_family,
                            font_size_pt=lb.size_pt, bold=line.bold,
                            italic=line.italic, align=line.align))
        if label.style.separators:
            ax0, _, ax1, _ = r.text_area
            for above, below in zip(r.lines, r.lines[1:]):
                mid = round((above.y1 + below.y0) / 2 - 0.5)
                out.append(make(ElementKind.LINE, (round(ax0), mid, round(ax1), mid + 1)))
        if r.code is not None:
            kind = ElementKind.QR if r.code.kind == CodeKind.QR else ElementKind.BARCODE
            out.append(make(kind, r.code.box, text=label.code.text))
        if r.picture_box is not None:
            pic = label.picture
            if pic.kind == PictureKind.SYMBOL:
                # a free symbol fills its box, so the box is the symbol's ink
                bx0, by0, bx1, by1 = r.picture_box
                fx0, fy0, fx1, fy1 = symbols.ink_box(pic.symbol)
                ink = (bx0 + fx0 * (bx1 - bx0), by0 + fy0 * (by1 - by0),
                       bx0 + fx1 * (bx1 - bx0), by0 + fy1 * (by1 - by0))
                out.append(make(ElementKind.SYMBOL, ink, symbol=pic.symbol))
            else:
                out.append(make(ElementKind.IMAGE, r.picture_box, image_png=pic.image_png))
        return out

    def _render_turned(self, label: Label, share: CategoryShare | None) -> RenderResult:
        """Text turned a quarter: lay the label out on an upright (portrait)
        version of the printable area, then turn it into place.  90° reads from
        bottom to top, 270° from top to bottom."""
        ss = max(1, int(self.calibration.supersample))
        px0, py0, px1, py1 = self.printable_box
        long_px, short_px = px1 - px0, py1 - py0
        dpm = self.profile.dots_per_mm
        upright = replace(self.profile, printhead_px=long_px, label_width_mm=short_px / dpm,
                          label_height_mm=long_px / dpm, feed_margin_mm=0.0, feed_offset_px=0)
        sub = RenderEngine(upright, self.calibration, self.fonts)
        flat = label.clone(new_id=False)
        flat.style.rotation = 0
        flat.style.border = flat.style.invert = False
        part = sub._render(flat, share)
        turned = part.hires.rotate(label.style.rotation, expand=True)
        w, h = self.design_size
        hires = Image.new("L", (w * ss, h * ss), 255)
        hires.paste(turned, (px0 * ss, py0 * ss))

        def place(x: float, y: float) -> tuple[float, float]:
            if label.style.rotation == 90:  # counter-clockwise
                return px0 + y, py0 + short_px - x
            return px0 + long_px - y, py0 + x

        boxes = []
        for lb in part.lines:
            (ax, ay), (bx, by) = place(lb.x0, lb.y0), place(lb.x1, lb.y1)
            boxes.append(replace(lb, x0=min(ax, bx), y0=min(ay, by), x1=max(ax, bx),
                                 y1=max(ay, by)))
        (ax, ay), (bx, by) = (place(part.content_box[0], part.content_box[1]),
                              place(part.content_box[2], part.content_box[3]))
        content = (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))
        return self._finish(hires, label, ss, boxes, list(part.warnings), content, None)

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

    def _place_code(self, label: Label, content: tuple[float, float, float, float],
                    has_text: bool, warnings: list[str]) -> PlacedCode | None:
        """Lay out the label's QR code or barcode inside *content*."""
        spec = label.code
        if spec.kind == CodeKind.NONE:
            return None
        text = _code_text(label, spec.text, warnings)
        if text is None:
            return None
        cx0, cy0, cx1, cy1 = content
        if spec.kind == CodeKind.QR:
            matrix = _qr_matrix(text, warnings)
            if matrix is None:
                return None
            n = len(matrix)
            module = min(QR_SIZE_MODULE_PX[spec.size], int((cy1 - cy0) // n))
            if module < QR_MIN_MODULE_PX:
                warnings.append(tr("QR-code wordt te klein om te scannen; kort de tekst in"))
                module = max(1, module)
            size = n * module
            x0 = round(cx0) if spec.side != HAlign.RIGHT else int(cx1) - size
            y0 = _vplace(spec.valign, cy0, cy1, size)
            rects = [(x0 + c * module, y0 + r * module, x0 + (c + 1) * module,
                      y0 + (r + 1) * module)
                     for r, row in enumerate(matrix) for c, dark in enumerate(row) if dark]
            gap = self.mm_to_px(QR_GAP_MM)
            area = ((x0 + size + gap, cy0, cx1, cy1) if spec.side != HAlign.RIGHT
                    else (cx0, cy0, x0 - gap, cy1))
            return PlacedCode(spec.kind, text, (x0, y0, x0 + size, y0 + size), module, rects, area)
        modules = _barcode_modules(text, warnings)
        if modules is None:
            return None
        module = _bar_module(min(BAR_MAX_MODULE_PX, int((cx1 - cx0) // len(modules))), warnings)
        if module < 1:
            return None
        width = len(modules) * module
        height = round(min(self.mm_to_px(BAR_HEIGHT_MM), (cy1 - cy0) * 0.45)) if has_text \
            else round(cy1 - cy0)
        x0 = round(cx0 + (cx1 - cx0 - width) / 2)
        y1 = int(cy1)
        y0 = y1 - height
        rects = [(x0 + i * module, y0, x0 + (i + 1) * module, y1)
                 for i, bar in enumerate(modules) if bar]
        area = (cx0, cy0, cx1, y0 - self.mm_to_px(BAR_GAP_MM))
        return PlacedCode(spec.kind, text, (x0, y0, x0 + width, y1), module, rects, area)

    def _fit_stack(self, label: Label, content: tuple[float, float, float, float],
                   warnings: list[str]) -> tuple[PlacedCode, tuple[
                       tuple[int, int, int, int], str | Image.Image,
                       tuple[float, float, float, float]]] | None:
        """QR code and pictogram under each other in one column at the side
        they share; None (nothing warned) when the QR code or the pictogram
        cannot be made, so the usual layout handles it."""
        text = _code_text(label, label.code.text, [])
        matrix = None
        if text is not None:
            try:
                matrix = codes.qr_matrix(text)
            except codes.CodeError:
                pass
        if matrix is None or self._picture_source(label, []) is None:
            return None
        tried: list[str] = []
        placed = self._place_stack(label, content, text, matrix,
                                   PICTURE_SCALE[label.picture.size], tried)
        if placed is None:
            return None
        warnings.extend(tried)
        return placed

    def _place_stack(self, label: Label, content: tuple[float, float, float, float],
                     text: str, matrix: list[list[bool]], scale: float,
                     warnings: list[str]) -> tuple[PlacedCode, tuple[
                         tuple[int, int, int, int], str | Image.Image,
                         tuple[float, float, float, float]]] | None:
        """One column of QR code and pictogram: the one set higher (top,
        middle, bottom) goes above.  Top sticks to the top edge, bottom to the
        bottom edge, middle right next to the other one."""
        spec, pic = label.code, label.picture
        source, aspect = self._picture_source(label, warnings)  # type: ignore[misc]
        cx0, cy0, cx1, cy1 = content
        height = cy1 - cy0
        gap = self.mm_to_px(PICTURE_GAP_MM)
        fx0, fy0, fx1, fy1 = (symbols.ink_box(source) if isinstance(source, str)
                              else (0.0, 0.0, 1.0, 1.0))
        ink_h = max(0.1, fy1 - fy0)
        # the QR code goes first (it has to scan); the pictogram keeps at least
        # half the height it would get beside the text
        n = len(matrix)
        keep = max(8.0, height * scale / 2 * ink_h)
        module = min(QR_SIZE_MODULE_PX[spec.size],
                     max(QR_MIN_MODULE_PX, int((height - gap - keep) // n)))
        if n * module > height - gap - 8:
            module = int((height - gap - 8) // n)
        if module < QR_MIN_MODULE_PX:
            warnings.append(tr("QR-code wordt te klein om te scannen; kort de tekst in"))
            if module < 1:
                return None
        qr = n * module
        h = int(min(height * scale, (height - qr - gap) / ink_h))
        w = round(h * aspect)
        max_w = int((cx1 - cx0) * PICTURE_MAX_WIDTH)
        if w > max_w:
            w = max_w
            h = max(1, round(w / aspect))
        if w < 8 or h < 8:  # 1 mm: no room
            warnings.append(tr("Geen ruimte voor het pictogram"))
            return None
        pic_ink_w, pic_ink_h = (fx1 - fx0) * w, ink_h * h
        column = max(qr, pic_ink_w)
        left = spec.side != HAlign.RIGHT
        col_x0 = cx0 if left else cx1 - column
        qx0 = round(col_x0 + (column - qr) / 2)
        px0 = round(col_x0 + (column - pic_ink_w) / 2 - fx0 * w)
        # vertical: ink heights of the upper and the lower part
        rank = {VAlign.TOP: 0, VAlign.CENTER: 1, VAlign.BOTTOM: 2}
        qr_above = rank[spec.valign] < rank[pic.valign]
        h_up, h_down = (qr, pic_ink_h) if qr_above else (pic_ink_h, qr)
        ends = {spec.valign, pic.valign}
        if VAlign.TOP in ends:
            up = cy0
            down = cy1 - h_down if VAlign.BOTTOM in ends else cy0 + h_up + gap
        else:
            down = cy1 - h_down
            up = down - gap - h_up
        qy0, ink_y = (up, down) if qr_above else (down, up)
        qy0 = round(qy0)
        py0 = round(ink_y - fy0 * h)
        rects = [(qx0 + c * module, qy0 + r * module, qx0 + (c + 1) * module,
                  qy0 + (r + 1) * module)
                 for r, row in enumerate(matrix) for c, dark in enumerate(row) if dark]
        text_gap = self.mm_to_px(QR_GAP_MM)
        area = ((col_x0 + column + text_gap, cy0, cx1, cy1) if left
                else (cx0, cy0, col_x0 - text_gap, cy1))
        code = PlacedCode(spec.kind, text, (qx0, qy0, qx0 + qr, qy0 + qr), module, rects, area)
        return code, ((px0, py0, px0 + w, py0 + h), source, area)

    def _place_picture(self, label: Label, area: tuple[float, float, float, float],
                       warnings: list[str], scale: float = 1.0,
                       ) -> tuple[tuple[int, int, int, int], str | Image.Image,
                                  tuple[float, float, float, float]] | None:
        """Box for the label's pictogram at the outer edge of *area*:
        (box in design dots, source, area left for the text) or None."""
        pic = label.picture
        found = self._picture_source(label, warnings)
        if found is None:
            return None
        source, aspect = found
        ax0, ay0, ax1, ay1 = area
        h = int((ay1 - ay0) * scale)
        w = round(h * aspect)
        max_w = int((ax1 - ax0) * PICTURE_MAX_WIDTH)
        if w > max_w:
            w = max_w
            h = max(1, round(w / aspect))
        if w < 8 or h < 8:  # 1 mm: no room
            warnings.append(tr("Geen ruimte voor het pictogram"))
            return None
        gap = self.mm_to_px(PICTURE_GAP_MM)
        # a symbol's white space does not push the text away, nor keep its ink
        # from the top or bottom edge
        fx0, fy0, fx1, fy1 = (symbols.ink_box(source) if isinstance(source, str)
                              else (0.0, 0.0, 1.0, 1.0))
        y0 = (_vplace(pic.valign, ay0, ay1, h) if pic.valign == VAlign.CENTER
              else _vplace(pic.valign, ay0 - fy0 * h, ay1 + (1 - fy1) * h, h))
        if pic.side == HAlign.RIGHT:
            x0 = round(ax1 - fx1 * w)
            rest = (ax0, ay0, x0 + fx0 * w - gap, ay1)
        else:
            x0 = round(ax0 - fx0 * w)
            rest = (x0 + fx1 * w + gap, ay0, ax1, ay1)
        return (x0, y0, x0 + w, y0 + h), source, rest

    @staticmethod
    def _picture_source(label: Label, warnings: list[str]
                        ) -> tuple[str | Image.Image, float] | None:
        """The pictogram to draw (symbol key or image) and its width/height."""
        pic = label.picture
        if pic.kind == PictureKind.SYMBOL:
            if pic.symbol not in symbols.SYMBOLS:
                warnings.append(tr("Onbekend symbool '{name}'", name=pic.symbol))
                return None
            return pic.symbol, 1.0
        if pic.kind == PictureKind.IMAGE:
            img = pictures.decode(pic.image_png)
            if img is None:
                warnings.append(tr("Geen afbeelding gekozen"))
                return None
            return img, img.width / max(1, img.height)
        return None

    @staticmethod
    def _draw_picture(canvas: Image.Image, box: tuple[int, int, int, int],
                      source: str | Image.Image, ss: int) -> tuple[int, int, int, int] | None:
        """Draws *source* in *box*; returns the box of its ink on *canvas*
        (None for a blank picture).  A symbol has white space around it, so
        its ink is smaller than the box."""
        x0, y0, x1, y1 = (v * ss for v in box)
        w, h = x1 - x0, y1 - y0
        if isinstance(source, str):
            img = symbols.draw_symbol(source, min(w, h))
            ox, oy = x0 + (w - img.width) // 2, y0 + (h - img.height) // 2
        else:
            img = source.resize((w, h), Image.Resampling.LANCZOS)
            ox, oy = x0, y0
        region = canvas.crop((ox, oy, ox + img.width, oy + img.height))
        canvas.paste(ImageChops.darker(region, img), (ox, oy))
        ink = ImageOps.invert(img.convert("L")).point(lambda v: 255 if v >= 128 else 0).getbbox()
        return (ox + ink[0], oy + ink[1], ox + ink[2], oy + ink[3]) if ink else None

    def _prepare_lines(self, label: Label, warnings: list[str]) -> list[_Prepared]:
        return [self._prepare_text(label, slot, line, warnings)
                for slot, line in label.visible_lines()]

    def _prepare_text(self, label: Label, slot: int, line: TextLine,
                      warnings: list[str]) -> _Prepared:
        resolved, unknown = label.resolve(line.text)
        _warn_unknown(unknown, warnings)
        text = " ".join(resolved.split("\n")).strip()
        face = self.fonts.resolve(line.font_family, line.bold, line.italic)
        missing = missing_glyphs(face, text)
        if missing:
            fb = self.fonts.fallback(line.bold, line.italic)
            if not missing_glyphs(fb, text):
                warnings.append(tr("Lettertype '{font}' mist teken(s) {chars}; '{fallback}' "
                                   "gebruikt voor deze regel", font=line.font_family,
                                   chars=missing, fallback=fb.family))
                face = fb
            else:
                warnings.append(tr("Teken(s) {chars} kunnen niet worden weergegeven",
                                   chars=missing))
        elif face.family != line.font_family:
            warnings.append(tr("Lettertype '{font}' niet gevonden; '{used}' gebruikt",
                               font=line.font_family, used=face.family))
        return _Prepared(slot, line, face, text)

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

    def _vbox(self, p: _Prepared, size_pt: float, share: CategoryShare | None
              ) -> tuple[float, float, float, float]:
        """Ink box of a line, made as tall as the category's tallest line in
        that slot so baselines line up from label to label."""
        l, t, r, b = self._measure(p, size_pt)
        ext = share.extent(p.slot) if share else None
        if ext is not None:
            t, b = min(t, ext[0] * size_pt), max(b, ext[1] * size_pt)
        return l, t, r, b

    def _width(self, p: _Prepared, size_pt: float) -> float:
        l, _t, r, _b = self._measure(p, size_pt)
        return r - l

    def _shorten(self, p: _Prepared, size_pt: float, avail_w: float) -> _Prepared:
        """*p* with its text cut short and ending in "…" so it fits *avail_w*."""
        text = p.text
        while len(text) > 1:
            text = text[:-1]
            short = replace(p, text=text.rstrip() + "…")
            if self._width(short, size_pt) <= avail_w + 0.5:
                return short
        return replace(p, text="…")

    def _autofit(self, prepared: list[_Prepared], sizes: list[float], avail_w: float,
                 avail_h: float, spacing: float,
                 share: CategoryShare | None = None) -> list[float]:
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
            boxes = [self._vbox(p, s, share) for p, s in zip(prepared, sizes)]
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


def _shares_sizes(label: Label) -> bool:
    """Whether the label takes part in its category's shared font sizes."""
    return (not label.is_free and label.style.autofit
            and label.style.same_size_in_category)


def is_stacked(label: Label) -> bool:
    """Whether the QR code and the pictogram stand under each other: both on
    the same side of the text, at different heights."""
    code, pic = label.code, label.picture
    return (code.kind == CodeKind.QR and pic.kind != PictureKind.NONE
            and code.side == pic.side and code.valign != pic.valign)


def _vplace(valign: VAlign, y0: float, y1: float, size: float) -> int:
    """Top of something *size* high at the top, middle or bottom of y0..y1."""
    if valign == VAlign.TOP:
        return round(y0)
    if valign == VAlign.BOTTOM:
        return round(y1 - size)
    return round(y0 + (y1 - y0 - size) / 2)


def _fit(w: float, h: float, aspect: float) -> tuple[float, float]:
    """The largest width and height of ratio *aspect* that fit in *w* × *h*."""
    return (h * aspect, h) if w / max(h, 1e-6) > aspect else (w, w / aspect)
