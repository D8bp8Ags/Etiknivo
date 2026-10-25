"""Label overview: every label as it prints, grouped by category.

Used for the overview sheet that can be saved as PDF (A4 pages, labels at
their real size, to print and hang next to the drawers) or as one long PNG.
The page is drawn at twice the printer resolution, so every printer dot
becomes exactly 2 × 2 pixels and the labels stay crisp.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

from etiknivo import APP_NAME
from etiknivo.i18n import tr
from etiknivo.model import Label
from etiknivo.rendering.engine import RenderEngine
from etiknivo.rendering.fonts import FontRegistry, pil_font
from etiknivo.storage.atomic import atomic_write_bytes

A4_MM = (210.0, 297.0)
MARGIN_MM = 12.0
GAP_MM = 4.0  # between label cards
CAPTION_MM = 7.0  # name and tray below each label
HEADING_MM = 9.0  # category heading
TITLE_MM = 12.0  # sheet title on the first page
FOOTER_MM = 8.0
PAPER_RADIUS_MM = 1.0

INK = (29, 29, 31)
MUTED = (110, 110, 118)
RULE = (210, 210, 216)
LABEL_EDGE = (190, 190, 198)


def overview_order(labels: Iterable[Label]) -> list[tuple[str, list[Label]]]:
    """Labels grouped by category (alphabetically, uncategorised last),
    each group sorted by tray ID and then name."""
    groups: dict[str, list[Label]] = {}
    for lbl in labels:
        groups.setdefault(lbl.category, []).append(lbl)
    order = sorted(groups, key=lambda c: (c == "", c.casefold()))
    return [(cat, sorted(groups[cat], key=lambda lbl: (lbl.tray_id == "", lbl.tray_id.casefold(),
                                                       lbl.name.casefold())))
            for cat in order]


def category_title(category: str) -> str:
    return category or tr("(zonder categorie)")


@dataclass
class _Sheet:
    """Drawing helper with millimetre coordinates."""

    px_per_mm: float
    width_mm: float
    height_mm: float

    def __post_init__(self) -> None:
        self.image = Image.new("RGB", (self.px(self.width_mm), self.px(self.height_mm)), "white")
        self.draw = ImageDraw.Draw(self.image)

    def px(self, mm: float) -> int:
        return round(mm * self.px_per_mm)

    def text(self, x_mm: float, y_mm: float, text: str, size_mm: float, colour: tuple,
             bold: bool = False, max_mm: float | None = None, anchor: str = "la") -> None:
        face = FontRegistry.fallback(bold=bold)
        font = pil_font(face.path, face.index, size_mm * self.px_per_mm)
        if max_mm is not None:
            limit = self.px(max_mm)
            if font.getlength(text) > limit:
                while text and font.getlength(text + "…") > limit:
                    text = text[:-1]
                text = text.rstrip() + "…"
        self.draw.text((self.px(x_mm), self.px(y_mm)), text, font=font, fill=colour,
                       anchor=anchor)

    def rule(self, x0_mm: float, y_mm: float, x1_mm: float) -> None:
        self.draw.line((self.px(x0_mm), self.px(y_mm), self.px(x1_mm), self.px(y_mm)),
                       fill=RULE, width=max(1, self.px(0.2)))


class OverviewLayout:
    """Flows headings and label cards over pages of a fixed width."""

    def __init__(self, engine: RenderEngine, width_mm: float, page_mm: float | None, *,
                 margin_mm: float = MARGIN_MM, gap_mm: float = GAP_MM,
                 heading_mm: float = HEADING_MM, caption_mm: float = CAPTION_MM,
                 title_mm: float = TITLE_MM) -> None:
        self.engine = engine
        self.label_w, self.label_h = engine.profile.label_size
        self.width_mm = width_mm
        self.page_mm = page_mm  # None: one long page
        self.margin, self.gap, self.heading, self.title = margin_mm, gap_mm, heading_mm, title_mm
        self.inner = width_mm - 2 * margin_mm
        self.cols = max(1, int((self.inner + gap_mm) // (self.label_w + gap_mm)))
        #: left edge of the grid: centred in the space between the margins
        self.left_mm = margin_mm + (self.inner - self.cols * (self.label_w + gap_mm)
                                    + gap_mm) / 2
        self.row_mm = self.label_h + caption_mm + gap_mm

    def x_mm(self, col: int) -> float:
        return self.left_mm + col * (self.label_w + self.gap)

    def span_mm(self, span: int) -> float:
        return span * self.label_w + (span - 1) * self.gap

    def pages(self, groups: list[tuple[str, list[Label]]]) -> list[list[tuple]]:
        """Items per page: (kind, y_mm, payload, column, columns spanned) with
        kind "title", "heading" or "label".

        Small categories share a band: they sit side by side, each under its
        own heading, so a library of many small drawers stays compact.  A
        category with more labels than fit on one row gets full rows."""
        pages: list[list[tuple]] = [[("title", self.margin, None, 0, self.cols)]]
        y = self.margin + self.title
        bottom = (self.page_mm - self.margin - FOOTER_MM) if self.page_mm else float("inf")
        band: list[tuple[str, list[Label]]] = []

        def room(height: float) -> None:
            nonlocal y
            if y + height > bottom:
                pages.append([])
                y = self.margin

        def flush() -> None:
            nonlocal y, band
            if not band:
                return
            room(self.heading + self.row_mm)
            col = 0
            for cat, labels in band:
                pages[-1].append(("heading", y, category_title(cat), col, len(labels)))
                for n, lbl in enumerate(labels):
                    pages[-1].append(("label", y + self.heading, lbl, col + n, 1))
                col += len(labels)
            y += self.heading + self.row_mm
            band = []

        for cat, labels in groups:
            if len(labels) <= self.cols:
                if sum(len(lbls) for _, lbls in band) + len(labels) > self.cols:
                    flush()
                band.append((cat, labels))
                continue
            flush()
            rows = [labels[i:i + self.cols] for i in range(0, len(labels), self.cols)]
            for n, row in enumerate(rows):
                room(self.row_mm + (self.heading if n == 0 else 0))  # a heading stays with a row
                if n == 0 or not pages[-1]:
                    title = category_title(cat) + ("" if n == 0 else " " + tr("(vervolg)"))
                    pages[-1].append(("heading", y, title, 0, self.cols))
                    y += self.heading
                for col, lbl in enumerate(row):
                    pages[-1].append(("label", y, lbl, col, 1))
                y += self.row_mm
        flush()
        self.end_mm = y
        return pages


def overview_pages(engine: RenderEngine, labels: Iterable[Label], *, paginate: bool = True,
                   today: date | None = None) -> list[Image.Image]:
    """The overview as images: A4 pages, or (without *paginate*) one long
    sheet of A4 width."""
    labels = list(labels)
    groups = overview_order(labels)
    width_mm = A4_MM[0]
    layout = OverviewLayout(engine, width_mm, A4_MM[1] if paginate else None)
    pages = layout.pages(groups)
    ppm = engine.profile.dots_per_mm * 2
    day = today or date.today()
    out: list[Image.Image] = []
    renders: dict[str, Image.Image] = {}

    for number, items in enumerate(pages, start=1):
        height = A4_MM[1] if paginate else layout.end_mm + MARGIN_MM
        sheet = _Sheet(ppm, width_mm, height)
        for kind, y, payload, col, span in items:
            x, span_mm = layout.x_mm(col), layout.span_mm(span)
            if kind == "title":
                sheet.text(layout.left_mm, y, tr("Labeloverzicht"), 5.0, INK, bold=True)
                sheet.text(width_mm - layout.left_mm, y + 1.2,
                           tr("{n} labels · {date}", n=len(labels), date=day.strftime("%d-%m-%Y")),
                           3.0, MUTED, anchor="ra")
            elif kind == "heading":
                sheet.text(x, y + 2.0, payload, 3.4, INK, bold=True, max_mm=span_mm)
                sheet.rule(x, y + 6.6, x + span_mm)
            else:
                lbl: Label = payload
                if lbl.id not in renders:
                    renders[lbl.id] = engine.render(lbl).mono.convert("L")
                _paste_label(sheet, renders[lbl.id], x, y, layout.label_w, layout.label_h)
                cap_y = y + layout.label_h + 1.2
                sheet.text(x, cap_y, lbl.name, 2.4, INK, bold=True, max_mm=layout.label_w)
                if lbl.tray_id:
                    sheet.text(x, cap_y + 3.0, lbl.tray_id, 2.2, MUTED, max_mm=layout.label_w)
        if paginate:
            sheet.text(width_mm / 2, A4_MM[1] - MARGIN_MM, tr("{app} · pagina {n} van {total}",
                       app=APP_NAME, n=number, total=len(pages)), 2.4, MUTED, anchor="ms")
        out.append(sheet.image)
    return out


def _paste_label(sheet: _Sheet, mono: Image.Image, x_mm: float, y_mm: float,
                 w_mm: float, h_mm: float) -> None:
    """The label as a piece of die-cut paper: rounded outline, exact dots inside."""
    x, y = sheet.px(x_mm), sheet.px(y_mm)
    w, h = sheet.px(w_mm), sheet.px(h_mm)
    img = mono.resize((w, h), Image.Resampling.NEAREST).convert("RGB")
    mask = Image.new("L", (w, h), 0)
    r = sheet.px(PAPER_RADIUS_MM)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    sheet.image.paste(img, (x, y), mask)
    sheet.draw.rounded_rectangle((x - 1, y - 1, x + w, y + h), r, outline=LABEL_EDGE,
                                 width=max(1, sheet.px(0.15)))


def export_overview_pdf(engine: RenderEngine, labels: Iterable[Label], path: Path) -> int:
    """A4 PDF with the labels at real size.  Returns the number of pages."""
    pages = overview_pages(engine, labels)
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", resolution=float(engine.profile.dpi * 2), save_all=True,
                  append_images=pages[1:], title=tr("Labeloverzicht"))
    atomic_write_bytes(path, buf.getvalue())
    return len(pages)


def export_overview_png(engine: RenderEngine, labels: Iterable[Label], path: Path) -> None:
    img = overview_pages(engine, labels, paginate=False)[0]
    buf = io.BytesIO()
    dpi = engine.profile.dpi * 2
    img.save(buf, "PNG", dpi=(dpi, dpi))
    atomic_write_bytes(path, buf.getvalue())


#: (title, function) for the export buttons of the overview window
EXPORTS: dict[str, tuple[str, Callable[..., object]]] = {
    "pdf": ("PDF (*.pdf)", export_overview_pdf),
    "png": ("PNG (*.png)", export_overview_png),
}
