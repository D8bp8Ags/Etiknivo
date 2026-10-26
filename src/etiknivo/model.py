"""Label data model.

A :class:`Label` always carries three text *slots* (top, main, bottom).  The
layout preset only decides which slots are visible and how they are styled,
so switching layouts never throws text away.

All dimensions are stored in millimetres or points; conversion to printer
pixels happens exclusively in :mod:`etiknivo.rendering`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from etiknivo.i18n import N_, format_date, tr

SCHEMA_VERSION = 1

#: Slot indices.  Slot 0 is the small top line (usually the category),
#: slot 1 the large main line, slot 2 the specification line.
SLOT_TOP, SLOT_MAIN, SLOT_BOTTOM = 0, 1, 2
SLOT_NAMES = (N_("Bovenregel"), N_("Hoofdregel"), N_("Onderregel"))  # tr() when shown

DEFAULT_FONT = "DejaVu Sans"

#: ``{Name}`` in a text line shows the value of that field on the label.
FIELD_RE = re.compile(r"\{([^{}\n]+)\}")
#: Fields every label has, besides its own specifications: shown name and the
#: names it answers to in either language.
BUILTIN_FIELDS = {
    "name": (N_("Naam"), ("naam", "name")),
    "tray_id": (N_("Lade"), ("lade", "tray")),
    "category": (N_("Categorie"), ("categorie", "category")),
}
#: Fields filled in at print time: today's date, the number of this copy
#: within the print job and the job's number of copies.  Outside printing
#: (preview, export) they show copy 1 of 1.
PRINT_FIELDS = {
    "date": (N_("Datum"), ("datum", "date")),
    "number": (N_("Nr"), ("nr", "no")),
    "count": (N_("Aantal"), ("aantal", "count")),
}


def spec_name(key: str) -> str:
    """The field name of a specification.  Braces typed around it are not part
    of the name: a specification "{Spanning}" is used as {Spanning}."""
    return key.strip().strip("{}").strip()


def today_text(day: date | None = None) -> str:
    """Today's date as shown by ``{Datum}``: 24-10-2026, or ISO in English."""
    return format_date(day or date.today())


class HAlign(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class VAlign(StrEnum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class LayoutPreset(StrEnum):
    """The three standard layouts, a 'custom' mode for the three lines and
    'free': loose elements placed anywhere (see :class:`LabelElement`)."""

    SINGLE = "single"
    MAIN_SPEC = "main_spec"
    CATEGORY_MAIN_SPEC = "category_main_spec"
    CUSTOM = "custom"
    FREE = "free"


#: the layout stored for each quick choice of 1, 2 or 3 lines
LINE_COUNT_PRESETS = {1: LayoutPreset.SINGLE, 2: LayoutPreset.MAIN_SPEC,
                      3: LayoutPreset.CATEGORY_MAIN_SPEC}

def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class TextLine:
    """One line of text on a label."""

    text: str = ""
    enabled: bool = True
    font_family: str = DEFAULT_FONT
    font_size_pt: float = 8.0
    bold: bool = False
    italic: bool = False
    align: HAlign = HAlign.CENTER

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TextLine:
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        if "align" in kwargs:
            kwargs["align"] = HAlign(kwargs["align"])
        if "font_size_pt" in kwargs:
            kwargs["font_size_pt"] = float(kwargs["font_size_pt"])
        return cls(**kwargs)


@dataclass
class LabelFormat:
    """Physical label size.  Width runs along the roll (feed direction)."""

    width_mm: float = 30.0
    height_mm: float = 14.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LabelFormat:
        return cls(float(data.get("width_mm", 30.0)), float(data.get("height_mm", 14.0)))


@dataclass
class LabelStyle:
    """Label-wide layout properties."""

    valign: VAlign = VAlign.CENTER
    line_spacing_mm: float = 0.5
    margin_h_mm: float = 0.0  # on top of the profile's safe end margin
    margin_v_mm: float = 0.5
    autofit: bool = True
    #: 0, 90, 180 or 270 degrees counter-clockwise (content rotation, independent of
    #: the print orientation); 90 and 270 turn the text a quarter for upright labels
    rotation: int = 0
    border: bool = False
    #: thin line between text lines
    separators: bool = False
    invert: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LabelStyle:
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        if "valign" in kwargs:
            kwargs["valign"] = VAlign(kwargs["valign"])
        if "rotation" in kwargs:
            rot = int(kwargs["rotation"]) % 360
            kwargs["rotation"] = rot if rot in (0, 90, 180, 270) else 0
        return cls(**kwargs)


class CodeKind(StrEnum):
    NONE = "none"
    QR = "qr"
    CODE128 = "code128"


@dataclass
class LabelCode:
    """An optional QR code beside the text, or a Code 128 barcode in place of
    the bottom line.  *text* may contain ``{Name}`` fields."""

    kind: CodeKind = CodeKind.NONE
    text: str = "{Lade}"
    side: HAlign = HAlign.LEFT  # QR code: LEFT or RIGHT of the text

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LabelCode:
        c = cls()
        try:
            c.kind = CodeKind(data.get("kind", CodeKind.NONE))
        except ValueError:
            c.kind = CodeKind.NONE
        c.text = str(data.get("text", c.text))
        c.side = HAlign.RIGHT if data.get("side") == HAlign.RIGHT else HAlign.LEFT
        return c


class PictureKind(StrEnum):
    NONE = "none"
    SYMBOL = "symbol"
    IMAGE = "image"


@dataclass
class LabelPicture:
    """A pictogram beside the text: one of Etiknivo's symbols or an image of
    the user's own, stored in the label as a small greyscale PNG (base64), so
    the library stays self-contained."""

    kind: PictureKind = PictureKind.NONE
    symbol: str = "resistor"
    image_png: str = ""
    side: HAlign = HAlign.LEFT

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LabelPicture:
        p = cls()
        try:
            p.kind = PictureKind(data.get("kind", PictureKind.NONE))
        except ValueError:
            p.kind = PictureKind.NONE
        p.symbol = str(data.get("symbol", p.symbol))
        p.image_png = str(data.get("image_png", ""))
        p.side = HAlign.RIGHT if data.get("side") == HAlign.RIGHT else HAlign.LEFT
        return p


class ElementKind(StrEnum):
    TEXT = "text"
    QR = "qr"
    BARCODE = "barcode"
    SYMBOL = "symbol"
    IMAGE = "image"
    LINE = "line"
    BOX = "box"


ELEMENT_TITLES: dict[ElementKind, str] = {
    ElementKind.TEXT: N_("Tekst"),
    ElementKind.QR: N_("QR-code"),
    ElementKind.BARCODE: N_("Barcode"),
    ElementKind.SYMBOL: N_("Symbool"),
    ElementKind.IMAGE: N_("Afbeelding"),
    ElementKind.LINE: N_("Lijn"),
    ElementKind.BOX: N_("Kader"),
}

#: Smallest element side: one printer dot.
ELEMENT_MIN_MM = 0.125


@dataclass
class LabelElement:
    """A loose element of a label in the free layout.

    The box is in millimetres from the top-left corner of the printable area,
    in design orientation.  Text shrinks to fit its box; codes, symbols and
    images are scaled to fit and centred; a line fills its box (a thin box is
    a line); a frame is a one-dot outline of its box.
    """

    kind: ElementKind = ElementKind.TEXT
    x_mm: float = 0.0
    y_mm: float = 0.0
    w_mm: float = 10.0
    h_mm: float = 4.0
    text: str = ""  # text, or what a QR code or barcode contains
    font_family: str = DEFAULT_FONT
    font_size_pt: float = 10.0  # largest size; smaller when the box is too small
    bold: bool = False
    italic: bool = False
    align: HAlign = HAlign.CENTER
    symbol: str = ""
    image_png: str = ""  # base64 PNG, see rendering.pictures
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    @property
    def title(self) -> str:
        return tr(ELEMENT_TITLES[self.kind])

    @property
    def has_text(self) -> bool:
        return self.kind in (ElementKind.TEXT, ElementKind.QR, ElementKind.BARCODE)

    def as_line(self) -> TextLine:
        """Font settings of a text element, as the renderer knows them."""
        return TextLine(self.text, True, self.font_family, self.font_size_pt, self.bold,
                        self.italic, self.align)

    def move_to(self, x_mm: float, y_mm: float) -> None:
        self.x_mm, self.y_mm = round(x_mm, 6), round(y_mm, 6)

    def resize(self, w_mm: float, h_mm: float) -> None:
        self.w_mm = round(max(ELEMENT_MIN_MM, w_mm), 6)
        self.h_mm = round(max(ELEMENT_MIN_MM, h_mm), 6)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LabelElement:
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        kwargs["kind"] = ElementKind(kwargs.get("kind", ElementKind.TEXT))
        kwargs["align"] = HAlign(kwargs.get("align", HAlign.CENTER))
        for k in ("x_mm", "y_mm", "w_mm", "h_mm", "font_size_pt"):
            if k in kwargs:
                kwargs[k] = float(kwargs[k])
        el = cls(**kwargs)
        el.resize(el.w_mm, el.h_mm)
        return el


def default_lines() -> list[TextLine]:
    return [TextLine(), TextLine(), TextLine()]


@dataclass
class Label:
    """A single label in the library."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = field(default_factory=lambda: tr("Nieuw label"))
    tray_id: str = ""
    category: str = ""
    layout: LayoutPreset = LayoutPreset.CATEGORY_MAIN_SPEC
    lines: list[TextLine] = field(default_factory=default_lines)
    style: LabelStyle = field(default_factory=LabelStyle)
    format: LabelFormat = field(default_factory=LabelFormat)
    code: LabelCode = field(default_factory=LabelCode)
    picture: LabelPicture = field(default_factory=LabelPicture)
    #: loose elements, used when ``layout`` is FREE
    elements: list[LabelElement] = field(default_factory=list)
    #: :meth:`lines_key` of the lines the elements were made from
    elements_from: str = ""
    specs: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    created: str = field(default_factory=_now)
    modified: str = field(default_factory=_now)

    # -- convenience accessors -------------------------------------------------

    @property
    def top(self) -> TextLine:
        return self.lines[SLOT_TOP]

    @property
    def main(self) -> TextLine:
        return self.lines[SLOT_MAIN]

    @property
    def bottom(self) -> TextLine:
        return self.lines[SLOT_BOTTOM]

    def visible_lines(self) -> list[tuple[int, TextLine]]:
        """Slots that will actually be rendered (enabled and non-empty)."""
        return [(i, ln) for i, ln in enumerate(self.lines)
                if ln.enabled and self.resolve(ln.text)[0].strip()]

    # -- fields ----------------------------------------------------------------

    def field_names(self) -> list[str]:
        """Names usable as ``{Name}``: the specifications, then the built-ins."""
        own = [n for k in self.specs if (n := spec_name(k))]
        taken = {k.casefold() for k in own}
        builtin = [*BUILTIN_FIELDS.values(), *PRINT_FIELDS.values()]
        return own + [tr(shown) for shown, _ in builtin if tr(shown).casefold() not in taken]

    def print_values(self, number: int = 1, count: int = 1,
                     day: date | None = None) -> dict[str, str]:
        """Values of the print-time fields, except names a specification uses."""
        own = {spec_name(k).casefold() for k in self.specs}
        values = {"date": today_text(day), "number": str(number), "count": str(count)}
        return {alias: values[key] for key, (_, aliases) in PRINT_FIELDS.items()
                for alias in aliases if alias not in own}

    def field_values(self) -> dict[str, str]:
        values = {alias: getattr(self, attr) for attr, (_, aliases) in BUILTIN_FIELDS.items()
                  for alias in aliases}
        values.update(self.print_values())
        values.update({spec_name(k).casefold(): v for k, v in self.specs.items()})
        return values

    @property
    def is_free(self) -> bool:
        return self.layout == LayoutPreset.FREE

    def _texts(self) -> list[str]:
        return [ln.text for ln in self.lines] + [self.code.text] + \
            [el.text for el in self.elements if el.has_text]

    def uses_copy_number(self) -> bool:
        """Whether ``{Nr}`` appears, so every copy looks different."""
        aliases = set(PRINT_FIELDS["number"][1]) & set(self.print_values())
        return any(m.group(1).strip().casefold() in aliases
                   for text in self._texts() for m in FIELD_RE.finditer(text))

    def for_copy(self, number: int, count: int, day: date | None = None) -> Label:
        """A copy of this label with the print-time fields filled in for copy
        *number* of *count*."""
        values = self.print_values(number, count, day)

        def sub(m: re.Match[str]) -> str:
            return values.get(m.group(1).strip().casefold(), m.group(0))

        c = self.clone(new_id=False)
        for ln in c.lines:
            ln.text = FIELD_RE.sub(sub, ln.text)
        c.code.text = FIELD_RE.sub(sub, c.code.text)
        for el in c.elements:
            el.text = FIELD_RE.sub(sub, el.text)
        return c

    def resolve(self, text: str) -> tuple[str, list[str]]:
        """*text* with ``{Name}`` fields filled in (case-insensitive).
        Returns the text and the names of unknown fields, which stay as typed."""
        values = self.field_values()
        unknown: list[str] = []

        def sub(m: re.Match[str]) -> str:
            key = m.group(1).strip().casefold()
            if key in values:
                return values[key]
            unknown.append(m.group(1).strip())
            return m.group(0)

        return FIELD_RE.sub(sub, text), unknown

    def display_text(self, line: TextLine) -> str:
        return self.resolve(line.text)[0]

    def touch(self) -> None:
        self.modified = _now()

    # -- layouts ---------------------------------------------------------------

    def apply_layout(self, preset: LayoutPreset) -> None:
        """Switch layout.  Text in every slot is kept; only visibility and
        default styling change.  The free layout keeps the lines too; its
        elements are made by the renderer (``RenderEngine.to_elements``)."""
        self.layout = LayoutPreset(preset)
        if preset in (LayoutPreset.CUSTOM, LayoutPreset.FREE):
            return
        top, main, bottom = self.lines
        main.enabled = True
        main.bold = True
        main.italic = False
        main.align = HAlign.CENTER
        top.align = bottom.align = HAlign.CENTER
        top.bold = bottom.bold = False
        if preset == LayoutPreset.SINGLE:
            top.enabled = bottom.enabled = False
            main.font_size_pt = 20.0
        elif preset == LayoutPreset.MAIN_SPEC:
            top.enabled = False
            bottom.enabled = True
            main.font_size_pt = 16.0
            bottom.font_size_pt = 8.0
        else:
            top.enabled = bottom.enabled = True
            top.font_size_pt = 6.5
            main.font_size_pt = 14.0
            bottom.font_size_pt = 7.0
        self.style.valign = VAlign.CENTER
        self.style.autofit = True

    def show_lines(self, count: int) -> None:
        """Quick choice of how many lines show: 1 (the main line), 2 (main
        and bottom) or 3.  Fonts, sizes and alignment stay as they are."""
        enabled = {1: (False, True, False), 2: (False, True, True)}.get(count, (True,) * 3)
        for line, on in zip(self.lines, enabled):
            line.enabled = on
        self.layout = LINE_COUNT_PRESETS.get(count, LayoutPreset.CATEGORY_MAIN_SPEC)

    def line_count(self) -> int | None:
        """1, 2 or 3 when the lines that show match a quick choice, else None."""
        enabled = tuple(line.enabled for line in self.lines)
        return {(False, True, False): 1, (False, True, True): 2,
                (True, True, True): 3}.get(enabled)  # type: ignore[arg-type]

    def lines_key(self) -> str:
        """Hash of what the free layout's elements are made from."""
        d = {"lines": [asdict(x) for x in self.lines], "code": asdict(self.code),
             "picture": asdict(self.picture)}
        return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()

    # -- (de)serialisation -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["layout"] = str(self.layout)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Label:
        lines = [TextLine.from_dict(x) for x in data.get("lines", [])][:3]
        while len(lines) < 3:
            lines.append(TextLine(enabled=False))
        lbl = cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            name=str(data.get("name", "")),
            tray_id=str(data.get("tray_id", "")),
            category=str(data.get("category", "")),
            layout=LayoutPreset(data.get("layout", LayoutPreset.CUSTOM)),
            lines=lines,
            style=LabelStyle.from_dict(data.get("style", {})),
            format=LabelFormat.from_dict(data.get("format", {})),
            code=LabelCode.from_dict(data.get("code") or {}),
            picture=LabelPicture.from_dict(data.get("picture") or {}),
            elements=[LabelElement.from_dict(x) for x in data.get("elements") or []
                      if isinstance(x, dict)],
            elements_from=str(data.get("elements_from", "")),
            specs={str(k): str(v) for k, v in (data.get("specs") or {}).items()},
            notes=str(data.get("notes", "")),
        )
        if data.get("created"):
            lbl.created = str(data["created"])
        if data.get("modified"):
            lbl.modified = str(data["modified"])
        return lbl

    def clone(self, *, new_id: bool = True) -> Label:
        c = copy.deepcopy(self)
        if new_id:
            c.id = uuid.uuid4().hex
            c.created = c.modified = _now()
        return c

    def render_key(self) -> str:
        """Stable hash of everything that affects the rendered output."""
        d = {"lines": [asdict(x) for x in self.lines], "style": asdict(self.style),
             "format": asdict(self.format), "code": asdict(self.code),
             "picture": asdict(self.picture), "layout": str(self.layout),
             "elements": [asdict(x) for x in self.elements] if self.is_free else [],
             "fields": self.field_values()}
        return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


#: Parts of a label's look that "Opmaak overnemen" can copy; the text stays.
FORMAT_PARTS = {
    "layout": N_("Layout en lettertypen"),
    "style": N_("Opmaak (uitlijning, marges, rand, rotatie)"),
    "code": N_("QR-code of barcode"),
    "picture": N_("Pictogram"),
}


def copy_format(src: Label, dst: Label, parts: set[str] | list[str]) -> None:
    """Give *dst* the look of *src* for the chosen *parts*; texts, names,
    specifications and notes stay as they are."""
    if "layout" in parts:
        dst.layout = src.layout
        for s_line, d_line in zip(src.lines, dst.lines):
            d_line.enabled = s_line.enabled
            d_line.font_family = s_line.font_family
            d_line.font_size_pt = s_line.font_size_pt
            d_line.bold = s_line.bold
            d_line.italic = s_line.italic
            d_line.align = s_line.align
        if src.is_free:
            # same positions and fonts; a label that had the same elements keeps its texts
            old = dst.elements
            dst.elements = copy.deepcopy(src.elements)
            if [e.kind for e in old] == [e.kind for e in src.elements]:
                for new, mine in zip(dst.elements, old):
                    new.text, new.symbol, new.image_png = mine.text, mine.symbol, mine.image_png
    if "style" in parts:
        dst.style = copy.deepcopy(src.style)
    if "code" in parts:
        dst.code = copy.deepcopy(src.code)
    if "picture" in parts:
        dst.picture = copy.deepcopy(src.picture)


def make_label(
    tray_id: str,
    category: str,
    main: str,
    spec: str = "",
    *,
    name: str | None = None,
    notes: str = "",
    layout: LayoutPreset | None = None,
) -> Label:
    """Create a label in the standard style (white, black text, no border,
    bold main text, smaller category/spec, centred, auto-fit)."""
    lbl = Label(tray_id=tray_id, category=category, notes=notes)
    lbl.lines[SLOT_TOP].text = category
    lbl.lines[SLOT_MAIN].text = main
    lbl.lines[SLOT_BOTTOM].text = spec
    if layout is None:
        if category and spec:
            layout = LayoutPreset.CATEGORY_MAIN_SPEC
        elif spec:
            layout = LayoutPreset.MAIN_SPEC
        else:
            layout = LayoutPreset.SINGLE
    lbl.apply_layout(layout)
    lbl.name = name or (f"{main} – {spec}" if spec else main) or tr("Nieuw label")
    return lbl
