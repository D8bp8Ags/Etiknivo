"""Ready-made label layouts (templates).

Each template arranges the parts a label already has (the three lines, the
tray ID, the QR code's content and the pictogram) in fixed boxes, after how
professional bin, component and 5S labels are laid out.  The texts keep
coming from the label, so changing a line changes the label; only the
arrangement is fixed.  The boxes scale with the printable area, so a template
works on every roll.

The result is a list of loose elements (as in the free layout) plus, for each
text, the *role* it plays.  The render engine draws them; labels of one
category with the same template share the font size per role.  Switching a
templated label to the free layout starts from exactly these elements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from etiknivo.i18n import tr
from etiknivo.model import (
    BUILTIN_FIELDS,
    FIELD_RE,
    SLOT_BOTTOM,
    SLOT_MAIN,
    SLOT_TOP,
    ElementKind,
    HAlign,
    Label,
    LabelElement,
    LabelTemplate,
    PictureKind,
)

#: tray IDs like A17, A-17 or AB 3: letters, then the rest
_TRAY_RE = re.compile(r"^\s*([A-Za-z]{1,3})[\s\-.]?(\d.*?)\s*$")

#: the cells of the specification grid are separated by this character
CELL_SEPARATOR = "|"


@dataclass
class Placed:
    """One element of a template; *role* names a text so labels of the same
    category can share its size ("" for everything else)."""

    element: LabelElement
    role: str = ""
    #: the line this text shows, for the "fitted to" hint in the editor
    slot: int | None = None


class _Builder:
    def __init__(self, label: Label, w: float, h: float) -> None:
        self.label = label
        self.w, self.h = w, h
        #: everything scales with the height; 12 mm is the Fichero's printhead
        self.s = h / 12.0
        self.items: list[Placed] = []
        self.warnings: list[str] = []

    # -- what the label has ------------------------------------------------------

    def line(self, slot: int) -> str:
        """The raw text of a line when it shows something, else ""."""
        ln = self.label.lines[slot]
        if not ln.enabled or not self.label.resolve(ln.text)[0].strip():
            return ""
        return ln.text

    @property
    def tray(self) -> str:
        return self.label.tray_id.strip()

    def has_picture(self) -> bool:
        pic = self.label.picture
        return (pic.kind == PictureKind.SYMBOL and bool(pic.symbol)) or \
            (pic.kind == PictureKind.IMAGE and bool(pic.image_png))

    # -- adding elements -------------------------------------------------------------

    def text(self, x: float, y: float, w: float, h: float, text: str, pt: float, *,
             bold: bool = False, align: HAlign = HAlign.LEFT, role: str = "",
             slot: int | None = None) -> None:
        if not text or w <= 0 or h <= 0:
            return
        line = self.label.lines[slot if slot is not None else SLOT_MAIN]
        el = LabelElement(ElementKind.TEXT, x_mm=x, y_mm=y, w_mm=w, h_mm=h, text=text,
                          font_family=line.font_family, font_size_pt=round(pt * self.s, 1),
                          bold=bold, italic=line.italic, align=align)
        self.items.append(Placed(el, role, slot))

    def element(self, kind: ElementKind, x: float, y: float, w: float, h: float,
                **kw: object) -> None:
        el = LabelElement(kind, x_mm=x, y_mm=y, w_mm=w, h_mm=h, **kw)  # type: ignore[arg-type]
        self.items.append(Placed(el))

    def rule_v(self, x: float, y: float, h: float) -> None:
        """A vertical line of two dots."""
        self.element(ElementKind.LINE, x, y, 0.25, h)

    def rule_h(self, x: float, y: float, w: float) -> None:
        self.element(ElementKind.LINE, x, y, w, 0.25)

    def picture(self, x: float, y: float, w: float, h: float) -> None:
        pic = self.label.picture
        if pic.kind == PictureKind.SYMBOL:
            self.element(ElementKind.SYMBOL, x, y, w, h, symbol=pic.symbol)
        else:
            self.element(ElementKind.IMAGE, x, y, w, h, image_png=pic.image_png)

    def qr_with_text(self, x: float, w: float) -> None:
        """QR code of the code's content, with that content readable below it;
        the two together are centred in the height."""
        s = self.s
        content = self.label.code.text.strip() or tray_field()
        cap = 3.0 * s
        q = min(w, self.h - cap)
        y = (self.h - q - cap) / 2
        self.element(ElementKind.QR, x + (w - q) / 2, y, q, q, text=content)
        self.text(x, y + q + 0.1 * s, w, cap - 0.1 * s, content, 7.5, bold=True,
                  align=HAlign.CENTER, role="code")

    def stack(self, x: float, y: float, w: float, h: float,
              rows: list[tuple[int, float, float, bool]], align: HAlign = HAlign.LEFT,
              prefix: str = "") -> None:
        """The lines in *rows* ((slot, share of the height, size in pt, bold))
        under each other; empty lines leave their room to the others."""
        shown = [(slot, part, pt, bold) for slot, part, pt, bold in rows if self.line(slot)]
        total = sum(part for _, part, _, _ in shown)
        for slot, part, pt, bold in shown:
            rh = h * part / total
            self.text(x, y, w, rh, self.line(slot), pt, bold=bold, align=align,
                      role=f"{prefix}{slot}", slot=slot)
            y += rh

    def header_bar(self, x: float, w: float, height: float) -> float:
        """Top line (in capitals) and the tray ID white on a black bar; returns
        the height used."""
        top, tray = self.line(SLOT_TOP), self.tray
        if not top and not tray:
            return 0.0
        s = self.s
        pad = 0.5 * s
        tray_w = min(7.0 * s, w * 0.35) if tray else 0.0
        self.text(x + pad, 0.15 * s, w - 2 * pad - tray_w, height - 0.3 * s, capitals(top),
                  6.5, bold=True, role="bar", slot=SLOT_TOP)
        self.text(x + w - pad - tray_w, 0.15 * s, tray_w, height - 0.3 * s, tray_field(), 7,
                  bold=True, align=HAlign.RIGHT, role="tray")
        self.element(ElementKind.INVERT, x, 0, w, height)
        return height


def apply_template(label: Label, template: LabelTemplate) -> None:
    """Give *label* *template*, with what that template is built around: a
    pictogram (a fitting symbol) or the QR code's content (the tray ID)."""
    from etiknivo.rendering.symbols import suggest_symbol

    label.template = template
    pic = label.picture
    if template in (LabelTemplate.ICON, LabelTemplate.ZONES) and pic.kind == PictureKind.NONE:
        pic.kind = PictureKind.SYMBOL
        # the most specific text first: "LED" says more than "Halfgeleiders"
        pic.symbol = suggest_symbol(label.top.text, label.name, label.main.text,
                                    label.category) or pic.symbol
    if template in (LabelTemplate.QR, LabelTemplate.ZONES) and not label.code.text.strip():
        label.code.text = tray_field()


def tray_field() -> str:
    """``{Lade}`` in the current language, so the free layout shows it as typed."""
    return "{" + tr(BUILTIN_FIELDS["tray_id"][0]) + "}"


def capitals(text: str) -> str:
    """*text* in capitals, leaving ``{field}`` names as typed."""
    out, pos = [], 0
    for m in FIELD_RE.finditer(text):
        out.append(text[pos:m.start()].upper())
        out.append(m.group(0))
        pos = m.end()
    out.append(text[pos:].upper())
    return "".join(out)


# -- the templates ---------------------------------------------------------------------

def _location(b: _Builder) -> None:
    s, w, h = b.s, b.w, b.h
    x = 0.0
    if b.tray:
        box_w = min(8.0 * s, w * 0.35)
        b.element(ElementKind.BOX, 0, 1.0 * s, box_w, h - 2.0 * s)
        m = _TRAY_RE.match(b.tray)
        inner = box_w - 1.0 * s
        if m:
            b.text(0.5 * s, 1.5 * s, inner, 3.25 * s, m.group(1), 11, bold=True,
                   align=HAlign.CENTER, role="tray_row")
            b.text(0.5 * s, 4.9 * s, inner, 5.6 * s, m.group(2), 20, bold=True,
                   align=HAlign.CENTER, role="tray_no")
        else:
            b.text(0.5 * s, 1.5 * s, inner, h - 3.0 * s, tray_field(), 16, bold=True,
                   align=HAlign.CENTER, role="tray")
        x = box_w + 1.0 * s
    b.stack(x, 0, w - x, h, [(SLOT_TOP, 3.0, 8, False), (SLOT_MAIN, 5.25, 16, True),
                             (SLOT_BOTTOM, 3.75, 7, False)])


def _value(b: _Builder) -> None:
    s, w, h = b.s, b.w, b.h
    top, tray = b.line(SLOT_TOP), b.tray
    head = 2.6 * s if (top or tray) else 0.0
    foot = 2.6 * s if b.line(SLOT_BOTTOM) else 0.0
    tray_w = min(7.0 * s, w * 0.35) if tray else 0.0
    b.text(0, 0, w - tray_w, head, top, 7, role="top", slot=SLOT_TOP)
    b.text(w - tray_w, 0, tray_w, head, tray_field(), 7, bold=True, align=HAlign.RIGHT,
           role="tray")
    b.text(0, head, w, h - head - foot, b.line(SLOT_MAIN), 22, bold=True,
           align=HAlign.CENTER, role="main", slot=SLOT_MAIN)
    b.text(0, h - foot, w, foot, b.line(SLOT_BOTTOM), 7, align=HAlign.CENTER,
           role="bottom", slot=SLOT_BOTTOM)


def _header(b: _Builder) -> None:
    s, w, h = b.s, b.w, b.h
    bar = b.header_bar(0, w, 3.0 * s)
    y = bar + (0.25 * s if bar else 0.0)
    b.stack(0, y, w, h - y, [(SLOT_MAIN, 5.75, 15, True), (SLOT_BOTTOM, 2.75, 7, False)],
            align=HAlign.CENTER)


def _icon(b: _Builder) -> None:
    s, w, h = b.s, b.w, b.h
    x = 0.0
    if b.has_picture():
        col = min(7.5 * s, w * 0.3)
        b.picture(0.25 * s, 1.0 * s, col - 0.5 * s, h - 2.0 * s)
        b.rule_v(col + 0.25 * s, 0.75 * s, h - 1.5 * s)
        x = col + 1.25 * s
    else:
        b.warnings.append(tr("Kies een pictogram voor dit sjabloon"))
    _text_with_tray(b, x, w - x)


def _text_with_tray(b: _Builder, x: float, w: float) -> None:
    """Top line with the tray ID on its right, the main line, the bottom line."""
    s, h = b.s, b.h
    top_h = 3.0 * s if (b.line(SLOT_TOP) or b.tray) else 0.0
    tray_w = min(5.5 * s, w * 0.35) if b.tray else 0.0
    b.text(x, 0, w - tray_w, top_h, b.line(SLOT_TOP), 8, role="top", slot=SLOT_TOP)
    b.text(x + w - tray_w, 0, tray_w, top_h, tray_field(), 6.5, bold=True, align=HAlign.RIGHT,
           role="tray")
    b.stack(x, top_h, w, h - top_h, [(SLOT_MAIN, 5.25, 15, True),
                                     (SLOT_BOTTOM, 3.25, 6.5, False)])


def _qr(b: _Builder) -> None:
    s, w, h = b.s, b.w, b.h
    col = min(h - 3.0 * s, w * 0.4)
    b.qr_with_text(0, col)
    x = col + 1.0 * s
    b.stack(x, 0, w - x, h, [(SLOT_TOP, 3.0, 8, False), (SLOT_MAIN, 5.25, 15, True),
                             (SLOT_BOTTOM, 3.25, 6.5, False)])


def _grid(b: _Builder) -> None:
    s, w, h = b.s, b.w, b.h
    head = " ".join(t for t in (b.line(SLOT_TOP), b.line(SLOT_MAIN)) if t)
    head_h = 4.75 * s if head or b.tray else 0.0
    tray_w = min(5.5 * s, w * 0.3) if b.tray else 0.0
    b.text(0, 0, w - tray_w, head_h, head, 13, bold=True, role="head", slot=SLOT_MAIN)
    b.text(w - tray_w, 0, tray_w, head_h, tray_field(), 8, bold=True, align=HAlign.RIGHT,
           role="tray")
    cells = [c.strip() for c in b.line(SLOT_BOTTOM).split(CELL_SEPARATOR) if c.strip()]
    if not cells:
        return
    y = head_h
    if head_h:
        b.rule_h(0, y + 0.1 * s, w)
        y += 0.75 * s
    cells = cells[:6]
    cols = 1 if len(cells) == 1 else 2
    rows = (len(cells) + cols - 1) // cols
    cw, rh = w / cols, (h - y) / rows
    if cols == 2:
        b.rule_v(w / 2 - 0.125 * s, y + 0.25 * s, h - y - 0.25 * s)
    for i, cell in enumerate(cells):
        cx = (i % cols) * cw + (0.75 * s if i % cols else 0.0)
        b.text(cx, y + (i // cols) * rh, cw - 0.75 * s, rh, cell,
               7.5, role="cell", slot=SLOT_BOTTOM)


def _distance(b: _Builder) -> None:
    s, w, h = b.s, b.w, b.h
    small = b.line(SLOT_TOP) or b.line(SLOT_BOTTOM)
    small_slot = SLOT_TOP if b.line(SLOT_TOP) else SLOT_BOTTOM
    foot = 2.4 * s if (small or b.tray) else 0.0
    b.text(0, 0, w, h - foot, b.line(SLOT_MAIN), 34, bold=True, align=HAlign.CENTER,
           role="main", slot=SLOT_MAIN)
    b.text(0, h - foot, w / 2, foot, small, 6.5, role="small", slot=small_slot)
    b.text(w / 2, h - foot, w / 2, foot, tray_field() if b.tray else "", 6.5, bold=True,
           align=HAlign.RIGHT, role="tray")


def _zones(b: _Builder) -> None:
    s, w, h = b.s, b.w, b.h
    x0, x1 = 0.0, w
    if b.has_picture():
        col = min(7.5 * s, w * 0.2)
        b.picture(0.25 * s, 1.0 * s, col - 0.5 * s, h - 2.0 * s)
        b.rule_v(col + 0.25 * s, 0.75 * s, h - 1.5 * s)
        x0 = col + 1.0 * s
    if b.label.code.text.strip() or b.tray:
        col = min(h - 3.0 * s, w * 0.25)
        b.qr_with_text(w - col, col)
        x1 = w - col - 1.0 * s
    tw = x1 - x0
    top = b.line(SLOT_TOP)
    bar = 0.0
    if top:
        b.text(x0 + 0.5 * s, 0.15 * s, tw - 1.0 * s, 2.45 * s, capitals(top), 6, bold=True,
               role="bar", slot=SLOT_TOP)
        b.element(ElementKind.INVERT, x0, 0, tw, 2.75 * s)
        bar = 3.0 * s
    b.stack(x0 + 0.5 * s, bar, tw - 0.5 * s, h - bar,
            [(SLOT_MAIN, 5.5, 15, True), (SLOT_BOTTOM, 3.0, 7, False)])


_BUILDERS = {
    LabelTemplate.LOCATION: _location,
    LabelTemplate.VALUE: _value,
    LabelTemplate.HEADER: _header,
    LabelTemplate.ICON: _icon,
    LabelTemplate.QR: _qr,
    LabelTemplate.GRID: _grid,
    LabelTemplate.DISTANCE: _distance,
    LabelTemplate.ZONES: _zones,
}


def template_items(label: Label, area_mm: tuple[float, float]) -> tuple[list[Placed], list[str]]:
    """The elements of *label*'s template in a printable area of *area_mm*
    (width, height), with warnings; empty for a label without a template."""
    build = _BUILDERS.get(label.template)
    if build is None:
        return [], []
    b = _Builder(label, *area_mm)
    build(b)
    for n, item in enumerate(b.items):  # the same ids every time, to find them back
        item.element.id = f"tpl{n}"
    if not any(p.element.kind == ElementKind.TEXT for p in b.items) and \
            not b.warnings:
        b.warnings.append(tr("Dit sjabloon heeft tekst nodig: vul de regels of de lade-ID in"))
    return b.items, b.warnings
