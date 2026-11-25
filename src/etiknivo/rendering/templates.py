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

from dataclasses import dataclass

from etiknivo.i18n import tr
from etiknivo.model import (
    BUILTIN_FIELDS,
    FIELD_RE,
    PART_FIELDS,
    PICTOGRAM_FIELD,
    SLOT_BOTTOM,
    SLOT_MAIN,
    SLOT_TOP,
    TEMPLATE_INFO,
    TRAY_RE,
    CodeKind,
    CodeSize,
    ElementKind,
    HAlign,
    Label,
    LabelElement,
    LabelTemplate,
    PictureKind,
    UserTemplate,
    find_user_template,
    part_field,
)

_TRAY_RE = TRAY_RE

#: the cells of the specification grid are separated by this character
CELL_SEPARATOR = "|"

#: how the size choice (Klein, Middel, Groot) widens a pictogram or QR column
COLUMN_SCALE = {CodeSize.SMALL: 0.8, CodeSize.MEDIUM: 1.0, CodeSize.LARGE: 1.2}

#: what a template starts the lines with: (size in pt, bold, alignment) for the
#: top, main and bottom line.  The size is the largest; a text that does not
#: fit its box gets smaller.
TEMPLATE_STYLES: dict[LabelTemplate, tuple[tuple[float, bool, HAlign], ...]] = {
    LabelTemplate.LOCATION: ((8, False, HAlign.LEFT), (16, True, HAlign.LEFT),
                             (7, False, HAlign.LEFT)),
    LabelTemplate.VALUE: ((7, False, HAlign.LEFT), (22, True, HAlign.CENTER),
                          (7, False, HAlign.CENTER)),
    LabelTemplate.HEADER: ((6.5, True, HAlign.LEFT), (15, True, HAlign.CENTER),
                           (7, False, HAlign.CENTER)),
    LabelTemplate.ICON: ((8, False, HAlign.LEFT), (15, True, HAlign.LEFT),
                         (6.5, False, HAlign.LEFT)),
    LabelTemplate.QR: ((8, False, HAlign.LEFT), (15, True, HAlign.LEFT),
                       (6.5, False, HAlign.LEFT)),
    LabelTemplate.GRID: ((13, True, HAlign.LEFT), (13, True, HAlign.LEFT),
                         (7.5, False, HAlign.LEFT)),
    LabelTemplate.DISTANCE: ((6.5, False, HAlign.LEFT), (34, True, HAlign.CENTER),
                             (6.5, False, HAlign.LEFT)),
    LabelTemplate.ZONES: ((6, True, HAlign.LEFT), (15, True, HAlign.LEFT),
                          (7, False, HAlign.LEFT)),
    **{t: ((7, False, HAlign.LEFT), (15, True, HAlign.LEFT), (6.5, False, HAlign.LEFT))
       for t in (LabelTemplate.BAR_CALM, LabelTemplate.BAR_TRAY)},
    # beside the tray box or the QR code the text column is narrower
    **{t: ((7, False, HAlign.LEFT), (14, True, HAlign.LEFT), (6, False, HAlign.LEFT))
       for t in (LabelTemplate.BAR_LOCATION, LabelTemplate.BAR_QR)},
}

#: the parts of a line's look a template sets
_LOOK = ("font_size_pt", "bold", "italic", "align")


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
        """The tray ID, or "" when the user switched it off for the template."""
        return self.label.tray_id.strip() if self.label.template_tray else ""

    def has_code(self) -> bool:
        return self.label.code.kind != CodeKind.NONE

    def code_room(self) -> float:
        """Height of the text under the QR code (0 when switched off)."""
        return 3.0 * self.s if self.label.code.caption else 0.0

    def has_picture(self) -> bool:
        pic = self.label.picture
        return (pic.kind == PictureKind.SYMBOL and bool(pic.symbol)) or \
            (pic.kind == PictureKind.IMAGE and bool(pic.image_png))

    # -- adding elements -------------------------------------------------------------

    def text(self, x: float, y: float, w: float, h: float, text: str, pt: float, *,
             bold: bool = False, align: HAlign = HAlign.LEFT, role: str = "",
             slot: int | None = None) -> None:
        """A text in a box.  A line's text takes the line's look (its size as
        the largest size, bold, italic, font, alignment), so the template is a
        starting point the user can change; the template's own texts (tray ID,
        code caption) take *pt*, *bold* and *align*."""
        if not text or w <= 0 or h <= 0:
            return
        if slot is not None:
            line = self.label.lines[slot]
            el = LabelElement(ElementKind.TEXT, x_mm=x, y_mm=y, w_mm=w, h_mm=h, text=text,
                              font_family=line.font_family, font_size_pt=line.font_size_pt,
                              bold=line.bold, italic=line.italic, align=line.align)
        else:
            main = self.label.lines[SLOT_MAIN]
            el = LabelElement(ElementKind.TEXT, x_mm=x, y_mm=y, w_mm=w, h_mm=h, text=text,
                              font_family=main.font_family,
                              font_size_pt=round(pt * self.s, 1), bold=bold, align=align)
        self.items.append(Placed(el, role, slot))

    def column(self, base: float, part: str) -> float:
        """Width of the pictogram or QR column: *base* scaled by its size choice."""
        size = getattr(self.label, part).size
        return base * COLUMN_SCALE[size]

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
        cap = self.code_room()
        q = min(w, self.h - cap)
        y = (self.h - q - cap) / 2
        self.element(ElementKind.QR, x + (w - q) / 2, y, q, q, text=content)
        if cap:
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


#: templates built around a pictogram, and around the QR code's content
#: the templates with a black bar of the category and the pictogram
BAR_TEMPLATES = (LabelTemplate.BAR_CALM, LabelTemplate.BAR_TRAY, LabelTemplate.BAR_LOCATION,
                 LabelTemplate.BAR_QR)
PICTURE_TEMPLATES = (LabelTemplate.ICON, LabelTemplate.ZONES, *BAR_TEMPLATES)
CODE_TEMPLATES = (LabelTemplate.QR, LabelTemplate.ZONES, LabelTemplate.BAR_QR)
#: templates that show the tray ID as a text of their own
TRAY_TEMPLATES = tuple(t for t in LabelTemplate
                       if t not in (LabelTemplate.NONE, LabelTemplate.CUSTOM, *CODE_TEMPLATES))


def template_look(template: LabelTemplate) -> list[dict[str, object]]:
    """The look a template starts the three lines with."""
    return [{"font_size_pt": float(pt), "bold": bold, "italic": False, "align": align}
            for pt, bold, align in TEMPLATE_STYLES[template]]


# -- the user's own templates ---------------------------------------------------------

#: field name (any language, lower case) -> line slot
_LINE_ALIASES = {alias: slot for slot, key in enumerate(("top", "main", "bottom"))
                 for alias in PART_FIELDS[key][1]}
_CODE_ALIASES = set(PART_FIELDS["code"][1])
_TRAY_ALIASES = {*BUILTIN_FIELDS["tray_id"][1], *PART_FIELDS["tray_row"][1],
                 *PART_FIELDS["tray_number"][1]}


def _only_field(text: str) -> str:
    """The field name (lower case) when *text* is one field and nothing else."""
    m = FIELD_RE.fullmatch(text.strip())
    return m.group(1).strip().casefold() if m else ""


def line_slot(el: LabelElement) -> int | None:
    """The line a text element of an own template shows, when it shows just that."""
    if el.kind != ElementKind.TEXT:
        return None
    return _LINE_ALIASES.get(_only_field(el.text))


def _fields_in(text: str) -> set[str]:
    return {m.group(1).strip().casefold() for m in FIELD_RE.finditer(text)}


def custom_template(label: Label) -> UserTemplate | None:
    """The user's own template *label* uses, if any (and if it still exists)."""
    if label.template != LabelTemplate.CUSTOM:
        return None
    return find_user_template(label.custom_template)


def uses_picture(label: Label) -> bool:
    """Whether the label's template shows the label's pictogram."""
    tpl = custom_template(label)
    if tpl is not None:
        return any(el.kind == ElementKind.SYMBOL and el.symbol == PICTOGRAM_FIELD
                   for el in tpl.elements)
    return label.template in PICTURE_TEMPLATES


def uses_code(label: Label) -> bool:
    """Whether the label's template shows the label's QR code."""
    tpl = custom_template(label)
    if tpl is not None:
        return any(el.kind in (ElementKind.QR, ElementKind.BARCODE)
                   and _fields_in(el.text) & _CODE_ALIASES for el in tpl.elements)
    return label.template in CODE_TEMPLATES


def shows_tray(label: Label) -> bool:
    """Whether the label's template shows the tray ID as a text of its own."""
    tpl = custom_template(label)
    if tpl is not None:
        return any(el.kind == ElementKind.TEXT and _fields_in(el.text) & _TRAY_ALIASES
                   for el in tpl.elements)
    return label.template in TRAY_TEMPLATES


def start_look(label: Label) -> list[dict[str, object]] | None:
    """The look the label's template starts the lines with (None for none).
    An own template takes it from the first text of each line; a line it does
    not show keeps its look."""
    tpl = custom_template(label)
    if tpl is not None:
        looks: list[dict[str, object]] = [{}, {}, {}]
        for el in tpl.elements:
            slot = line_slot(el)
            if slot is not None and not looks[slot]:
                looks[slot] = {"font_size_pt": el.font_size_pt, "bold": el.bold,
                               "italic": el.italic, "align": el.align}
        return [look or {key: getattr(line, key) for key in _LOOK}
                for look, line in zip(looks, label.lines)]
    if label.template in TEMPLATE_STYLES:
        return template_look(label.template)
    return None


def template_from_builtin(template: LabelTemplate, area_mm: tuple[float, float],
                          name: str = "") -> UserTemplate:
    """A copy of a ready-made template as an own template, to change: its
    elements with fields in place of a sample label's texts."""
    from etiknivo.model import make_label

    grid = template == LabelTemplate.GRID
    lbl = make_label("A17", tr("Halfgeleiders"), tr("Rood"),
                     "Ø 3 mm | THT | 20 mA | 2 V" if grid else "Ø 3 mm THT")
    lbl.top.text, lbl.top.enabled = "LED", True
    lbl.picture.kind, lbl.picture.symbol = PictureKind.SYMBOL, "led"
    apply_template(lbl, template)
    items, _ = template_items(lbl, area_mm)
    line_field = [part_field(k) for k in ("top", "main", "bottom")]
    elements: list[LabelElement] = []
    cell = 0
    for item in items:
        el = item.element
        if el.kind in (ElementKind.SYMBOL, ElementKind.IMAGE):
            el.kind, el.symbol, el.image_png = ElementKind.SYMBOL, PICTOGRAM_FIELD, ""
        elif el.kind in (ElementKind.QR, ElementKind.BARCODE):
            el.text = part_field("code")
        elif el.kind == ElementKind.TEXT:
            if item.role == "cell":
                cell += 1
                el.text = part_field(f"cell{cell}")
            elif item.role == "head":
                el.text = f"{line_field[0]} {line_field[1]}"
            elif item.role == "bar":
                el.text = line_field[0].upper()
            elif item.slot is not None:
                el.text = line_field[item.slot]
            elif item.role == "code":
                el.text = part_field("code")
            elif item.role == "tray_row":
                el.text = part_field("tray_row")
            elif item.role == "tray_no":
                el.text = part_field("tray_number")
            elif item.role == "tray":
                el.text = tray_field()
        el.id = LabelElement().id
        elements.append(el)
    return UserTemplate(name=name or tr(TEMPLATE_INFO[template][0]), width_mm=area_mm[0],
                        height_mm=area_mm[1], elements=elements)


def _custom(b: _Builder) -> None:
    """An own template: its elements scaled to the area, filled from the label."""
    tpl = custom_template(b.label)
    if tpl is None:
        b.warnings.append(tr("Het eigen sjabloon van dit label bestaat niet meer: kies een "
                             "ander sjabloon"))
        return
    lbl = b.label
    sx, sy = b.w / tpl.width_mm, b.h / tpl.height_mm
    for n, src in enumerate(tpl.elements):
        el = LabelElement(**{**src.__dict__})
        el.x_mm, el.y_mm = src.x_mm * sx, src.y_mm * sy
        el.w_mm, el.h_mm = max(0.125, src.w_mm * sx), max(0.125, src.h_mm * sy)
        el.font_size_pt = round(src.font_size_pt * sy, 2)
        fields = _fields_in(el.text) if el.has_text else set()
        role, slot = "", None
        if el.kind == ElementKind.SYMBOL and el.symbol == PICTOGRAM_FIELD:
            if not b.has_picture():
                continue
            pic = lbl.picture
            if pic.kind == PictureKind.SYMBOL:
                el.symbol = pic.symbol
            else:
                el.kind, el.symbol, el.image_png = ElementKind.IMAGE, "", pic.image_png
        elif el.kind in (ElementKind.QR, ElementKind.BARCODE):
            if fields & _CODE_ALIASES and lbl.code.kind == CodeKind.NONE:
                continue
        elif el.kind == ElementKind.TEXT:
            only = _only_field(el.text)
            slot = _LINE_ALIASES.get(only)
            if slot is not None:
                line = lbl.lines[slot]
                el.font_family, el.font_size_pt = line.font_family, line.font_size_pt
                el.bold, el.italic, el.align = line.bold, line.italic, line.align
                role = f"line{slot}"
            elif only in _CODE_ALIASES:
                if lbl.code.kind == CodeKind.NONE or not lbl.code.caption:
                    continue
                role = "code"
            elif fields and fields <= _TRAY_ALIASES:
                if not lbl.template_tray:
                    continue
                role = "tray"
            else:
                role = f"text{n}"
        b.items.append(Placed(el, role, slot))


def line_looks(label: Label) -> list[dict[str, object]]:
    return [{key: getattr(line, key) for key in _LOOK} for line in label.lines]


def _set_looks(label: Label, looks: list[dict[str, object]]) -> None:
    for line, look in zip(label.lines, looks):
        for key in _LOOK:
            if key in look:
                value = look[key]
                setattr(line, key, HAlign(value) if key == "align" else value)


def differs_from_template(label: Label) -> bool:
    """Whether the user changed the lines' look since the template set it."""
    look = start_look(label)
    return look is not None and line_looks(label) != look


def reset_to_template(label: Label) -> None:
    """The lines' look back to what the template starts with."""
    look = start_look(label)
    if look is not None:
        _set_looks(label, look)
        label.picture.size = label.code.size = CodeSize.MEDIUM


def apply_template(label: Label, template: LabelTemplate, custom_id: str = "") -> None:
    """Give *label* *template*: the lines get the template's starting look
    (size, bold, alignment), which the user can change afterwards, and the
    label gets what the template is built around: a pictogram (a fitting
    symbol) or a QR code of the tray ID.

    What a template switched on by itself is switched off again when the
    label goes to a template that does not need it (for example back to the
    lines under each other); what the user set up stays.  Going back to the
    lines under each other also gives the lines back the look they had
    before the first template.  *custom_id* names the user's own template
    when *template* is CUSTOM."""
    from etiknivo.rendering.symbols import suggest_symbol

    custom_id = custom_id if template == LabelTemplate.CUSTOM else ""
    if template == label.template and custom_id == label.custom_template:
        return
    if label.template == LabelTemplate.NONE and template != LabelTemplate.NONE:
        label.looks_before_template = line_looks(label)
    label.template, label.custom_template = template, custom_id
    look = start_look(label)
    if look is not None:
        _set_looks(label, look)
    elif label.looks_before_template:
        _set_looks(label, label.looks_before_template)
        label.looks_before_template = []
    pic, code = label.picture, label.code
    added = label.template_added
    wants_picture, wants_code = uses_picture(label), uses_code(label)
    if "picture" in added and not wants_picture:
        pic.kind = PictureKind.NONE
        added.remove("picture")
    if "code" in added and not wants_code:
        code.kind = CodeKind.NONE
        added.remove("code")
    if "code_text" in added and not wants_code:
        code.text = ""
        added.remove("code_text")
    if wants_picture and pic.kind == PictureKind.NONE:
        pic.kind = PictureKind.SYMBOL
        # the most specific text first: "LED" says more than "Halfgeleiders"
        pic.symbol = suggest_symbol(label.top.text, label.name, label.main.text,
                                    label.category) or pic.symbol
        added.append("picture")
    if "code_barcode" in added and not wants_code:
        code.kind = CodeKind.CODE128
        added.remove("code_barcode")
    if wants_code and code.kind != CodeKind.QR:
        added.append("code" if code.kind == CodeKind.NONE else "code_barcode")
        code.kind = CodeKind.QR
    if wants_code and not code.text.strip():
        code.text = tray_field()
        added.append("code_text")


def category_field() -> str:
    """``{Categorie}`` in the current language."""
    return "{" + tr(BUILTIN_FIELDS["category"][0]) + "}"


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
        col = min(b.column(7.5 * s, "picture"), w * 0.4)
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
    x = 0.0
    if b.has_code():
        room = h - b.code_room()
        col = min(b.column(room, "code"), room, w * 0.45)
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
        col = min(b.column(7.5 * s, "picture"), w * 0.25)
        b.picture(0.25 * s, 1.0 * s, col - 0.5 * s, h - 2.0 * s)
        b.rule_v(col + 0.25 * s, 0.75 * s, h - 1.5 * s)
        x0 = col + 1.0 * s
    if b.has_code():
        room = h - b.code_room()
        col = min(b.column(room, "code"), room, w * 0.3)
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


#: height of the category bar, at a printhead of 12 mm
BAR_MM = 3.4


def _category_bar(b: _Builder, tray: bool = False) -> float:
    """The category and the pictogram (and with *tray* the tray ID) white on a
    black bar over the full width; returns the height used."""
    s, w = b.s, b.w
    category = b.label.category.strip()
    tray = tray and bool(b.tray)
    if not category and not b.has_picture() and not tray:
        return 0.0
    bar = BAR_MM * s
    right = w - 0.4 * s
    if b.has_picture():
        right = w - 3.8 * s
        b.picture(right, 0.25 * s, 3.4 * s, bar - 0.5 * s)
        right -= 0.4 * s
    if tray:
        tray_w = min(5.0 * s, w * 0.2)
        b.text(right - tray_w, 0.15 * s, tray_w, bar - 0.3 * s, tray_field(), 7, bold=True,
               align=HAlign.RIGHT, role="tray")
        right -= tray_w + 0.6 * s
    if category:
        b.text(0.4 * s, 0.15 * s, right - 0.4 * s, bar - 0.3 * s, category_field(), 7,
               bold=True, role="category")
    b.element(ElementKind.INVERT, 0, 0, w, bar)
    return bar


def _bar_lines(b: _Builder, x: float, y: float, w: float, tray: bool = False) -> None:
    """The lines below the bar: the top line small (with *tray* the tray ID on
    its right), the main line large, the bottom line small."""
    s, h = b.s, b.h
    tray = tray and bool(b.tray)
    top = b.line(SLOT_TOP)
    if top or tray:
        top_h = 2.4 * s
        tray_w = min(6.0 * s, w * 0.35) if tray else 0.0
        b.text(x, y + 0.1 * s, w - tray_w, top_h - 0.1 * s, top, 7, role="top", slot=SLOT_TOP)
        b.text(x + w - tray_w, y + 0.1 * s, tray_w, top_h - 0.1 * s,
               tray_field() if tray else "", 7, bold=True, align=HAlign.RIGHT, role="tray")
        y += top_h
    # the bottom line keeps a little room under it for descenders such as |
    b.stack(x, y, w, h - y - 0.3 * s, [(SLOT_MAIN, 3.7, 15, True),
                                      (SLOT_BOTTOM, 2.3, 6.5, False)])


def _bar_calm(b: _Builder) -> None:
    s = b.s
    y = _category_bar(b)
    _bar_lines(b, 0.3 * s, y, b.w - 0.6 * s, tray=True)


#: below this width (at a 12 mm printhead) the tray ID does not fit in the bar
#: next to the category, and goes to the right of the top line instead
_BAR_TRAY_MIN_MM = 24.0


def _bar_tray(b: _Builder) -> None:
    s = b.s
    in_bar = b.w / s >= _BAR_TRAY_MIN_MM
    y = _category_bar(b, tray=in_bar)
    _bar_lines(b, 0.3 * s, y, b.w - 0.6 * s, tray=not in_bar)


def _bar_location(b: _Builder) -> None:
    s, h = b.s, b.h
    y = _category_bar(b)
    x = 0.3 * s
    if b.tray:
        box_w = min(7.5 * s, b.w * 0.3)
        top = y + 0.5 * s
        b.element(ElementKind.BOX, 0, top, box_w, h - top)
        b.text(0.4 * s, top + 0.3 * s, box_w - 0.8 * s, h - top - 0.6 * s, tray_field(), 14,
               bold=True, align=HAlign.CENTER, role="tray")
        x = box_w + 0.8 * s
    _bar_lines(b, x, y, b.w - x - 0.2 * s)


def _bar_qr(b: _Builder) -> None:
    s, w, h = b.s, b.w, b.h
    y = _category_bar(b)
    x1 = w - 0.3 * s
    if b.has_code():
        content = b.label.code.text.strip() or tray_field()
        cap = 2.2 * s if b.label.code.caption else 0.0
        room = h - y - 0.4 * s - cap
        q = min(b.column(room, "code"), room, w * 0.3)
        col = max(q, 6.6 * s) if cap else q
        cx = w - col
        qy = y + 0.4 * s + (room - q) / 2
        b.element(ElementKind.QR, cx + (col - q) / 2, qy, q, q, text=content)
        if cap:
            b.text(cx, h - cap, col, cap, content, 6.5, bold=True, align=HAlign.CENTER,
                   role="code")
        x1 = cx - 0.6 * s
    _bar_lines(b, 0.3 * s, y, x1 - 0.3 * s)


_BUILDERS = {
    LabelTemplate.LOCATION: _location,
    LabelTemplate.VALUE: _value,
    LabelTemplate.HEADER: _header,
    LabelTemplate.ICON: _icon,
    LabelTemplate.QR: _qr,
    LabelTemplate.GRID: _grid,
    LabelTemplate.DISTANCE: _distance,
    LabelTemplate.ZONES: _zones,
    LabelTemplate.BAR_CALM: _bar_calm,
    LabelTemplate.BAR_TRAY: _bar_tray,
    LabelTemplate.BAR_LOCATION: _bar_location,
    LabelTemplate.BAR_QR: _bar_qr,
    LabelTemplate.CUSTOM: _custom,
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
