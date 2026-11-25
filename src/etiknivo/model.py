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
import math
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from etiknivo.i18n import N_, format_date, tr

#: Version of the library file.  2 (Etiknivo 0.2): line, style, code and
#: picture fields added since 0.1.0 (``same_size_in_category``, ``valign`` and
#: ``size`` of the QR code and the pictogram, ``template`` of the label);
#: ``format`` is no longer used.
SCHEMA_VERSION = 2


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
#: Fields for the parts of a label, made for templates of the user's own
#: (usable in any text): the three lines, the cells of the bottom line
#: (split at "|"), the code's content and the tray ID split in its letters and
#: its number.  A line field typed in capitals, such as ``{BOVENREGEL}``, shows
#: the line in capitals.
PART_FIELDS = {
    "top": (N_("Bovenregel"), ("bovenregel", "top line")),
    "main": (N_("Hoofdregel"), ("hoofdregel", "main line")),
    "bottom": (N_("Onderregel"), ("onderregel", "bottom line")),
    **{f"cell{n}": (N_("Cel") + f" {n}", (f"cel {n}", f"cell {n}")) for n in range(1, 7)},
    "code": (N_("Code"), ("code",)),
    "tray_row": (N_("Laderij"), ("laderij", "tray row")),
    "tray_number": (N_("Ladenummer"), ("ladenummer", "tray number")),
}
#: in a template element's symbol: the label's own pictogram
PICTOGRAM_FIELD = "{Pictogram}"
#: tray IDs like A17, A-17 or AB 3: letters, then the rest
TRAY_RE = re.compile(r"^\s*([A-Za-z]{1,3})[\s\-.]?(\d.*?)\s*$")

#: What each built-in field shows, for the { } menu.
FIELD_HELP = {
    "name": N_("naam van het label"),
    "tray_id": N_("lade-ID, bv. A14"),
    "category": N_("categorie van het label"),
    "date": N_("datum van afdrukken"),
    "number": N_("volgnummer bij meerdere exemplaren: 1, 2, 3…"),
    "count": N_("totaal aantal exemplaren in de afdruk"),
    "top": N_("tekst van de bovenregel"),
    "main": N_("tekst van de hoofdregel"),
    "bottom": N_("tekst van de onderregel"),
    **{f"cell{n}": N_("deel van de onderregel tussen | tekens") for n in range(1, 7)},
    "code": N_("inhoud van de QR-code of barcode"),
    "tray_row": N_("letters van het lade-ID, bv. A van A17"),
    "tray_number": N_("nummer van het lade-ID, bv. 17 van A17"),
}


def field_help() -> dict[str, str]:
    """{shown field name: what it shows}, for the built-in fields."""
    return {_shown(shown): tr(FIELD_HELP[key])
            for key, (shown, _) in (*BUILTIN_FIELDS.items(), *PRINT_FIELDS.items(),
                                    *PART_FIELDS.items())}


def _shown(name: str) -> str:
    """A field's shown name; "Cel 2" is translated as "Cel" plus the number."""
    word, _, number = name.partition(" ")
    return f"{tr(word)} {number}" if number else tr(name)


def part_field_names() -> list[str]:
    """Shown names of :data:`PART_FIELDS`, for the { } menu of a template."""
    return [_shown(shown) for shown, _ in PART_FIELDS.values()]


def part_field(key: str) -> str:
    """``{Name}`` of a part field in the current language, e.g. ``{Hoofdregel}``."""
    return "{" + _shown(PART_FIELDS[key][0]) + "}"


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


class LabelTemplate(StrEnum):
    """A ready-made arrangement of the label's parts, after how professional
    labels are laid out (see :mod:`etiknivo.rendering.templates`).  NONE puts
    the lines under each other as before."""

    NONE = "none"
    LOCATION = "location"
    VALUE = "value"
    HEADER = "header"
    ICON = "icon"
    QR = "qr"
    GRID = "grid"
    DISTANCE = "distance"
    ZONES = "zones"
    #: a black bar with the category and the pictogram, the text below it
    BAR_CALM = "bar_calm"
    BAR_TRAY = "bar_tray"
    BAR_LOCATION = "bar_location"
    BAR_QR = "bar_qr"
    #: one of the user's own templates (see ``Label.custom_template``)
    CUSTOM = "custom"


#: (name, what it is for) per template, in the order of the chooser
TEMPLATE_INFO: dict[LabelTemplate, tuple[str, str]] = {
    LabelTemplate.NONE: (N_("Regels onder elkaar"),
        N_("De regels onder elkaar, met pictogram en code ernaast")),
    LabelTemplate.LOCATION: (N_("Grote lade-ID links"),
        N_("Lade-ID groot in een kader links, de tekst ernaast")),
    LabelTemplate.VALUE: (N_("Grote hoofdregel"),
        N_("Hoofdregel zo groot mogelijk; bovenregel en lade-ID klein in de hoeken")),
    LabelTemplate.DISTANCE: (N_("Hoofdregel extra groot"),
        N_("Alleen de hoofdregel, zo groot als past; bovenregel en lade-ID klein eronder")),
    LabelTemplate.ICON: (N_("Pictogram links"),
        N_("Pictogram over de volle hoogte links, een lijn, dan de tekst")),
    LabelTemplate.QR: (N_("QR-code links"),
        N_("QR-code links met de inhoud leesbaar eronder, de tekst ernaast")),
    LabelTemplate.GRID: (N_("Specificaties in vakjes"),
        N_("Bovenregel en hoofdregel als kop; de onderregel in vakjes, gescheiden door |")),
    LabelTemplate.HEADER: (N_("Zwarte balk met bovenregel"),
        N_("Bovenregel en lade-ID wit op een zwarte balk, de hoofdregel groot eronder")),
    LabelTemplate.BAR_CALM: (N_("Zwarte balk met categorie"),
        N_("Categorie en pictogram wit op een zwarte balk; lade-ID rechtsboven in het "
           "witte deel")),
    LabelTemplate.BAR_TRAY: (N_("Zwarte balk met categorie en lade-ID"),
        N_("Categorie, lade-ID en pictogram wit op een zwarte balk; eronder de drie regels")),
    LabelTemplate.BAR_LOCATION: (N_("Zwarte balk, grote lade-ID links"),
        N_("Categorie en pictogram wit op een zwarte balk; lade-ID groot in een kader "
           "links")),
    LabelTemplate.BAR_QR: (N_("Zwarte balk, QR-code rechts"),
        N_("Categorie en pictogram wit op een zwarte balk; QR-code met lade-ID rechts")),
    LabelTemplate.ZONES: (N_("Pictogram, tekst en QR-code (lang etiket)"),
        N_("Pictogram, tekst met zwarte balk en QR-code naast elkaar; voor etiketten van "
           "40 of 50 mm")),
}

#: the layout stored for each quick choice of 1, 2 or 3 lines
LINE_COUNT_PRESETS = {1: LayoutPreset.SINGLE, 2: LayoutPreset.MAIN_SPEC,
                      3: LayoutPreset.CATEGORY_MAIN_SPEC}

# -- reading stored values ------------------------------------------------------
#
# Library files are usually written by Etiknivo, but they can also be edited by
# hand or made by another program.  Values of the wrong type or outside the
# range the editor allows fall back to the default instead of breaking the
# whole library (see ``labels_from_document``).

_TRUE = {"true", "1", "yes", "ja", "on", "waar"}
_FALSE = {"false", "0", "no", "nee", "off", "onwaar", ""}

#: ranges the editor allows; values read from a file are clamped to them
FONT_SIZE_RANGE = (3.0, 60.0)
MARGIN_H_RANGE = (0.0, 10.0)
MARGIN_V_RANGE = (0.0, 5.0)
LINE_SPACING_RANGE = (-3.0, 5.0)


def as_dict(value: Any) -> dict[str, Any]:
    """*value* when it is a dict, else an empty one."""
    return value if isinstance(value, dict) else {}


def as_bool(value: Any, default: bool) -> bool:
    """A stored yes/no: real booleans, numbers and the usual words."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        word = value.strip().casefold()
        if word in _TRUE:
            return True
        if word in _FALSE:
            return False
    return default


def as_float(value: Any, default: float, lo: float | None = None,
             hi: float | None = None) -> float:
    """A stored number, clamped to *lo*..*hi*; *default* when it is no number."""
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    if lo is not None:
        number = max(lo, number)
    if hi is not None:
        number = min(hi, number)
    return number


def as_str(value: Any, default: str = "") -> str:
    """A stored text; numbers become text, anything else gives *default*."""
    if isinstance(value, str):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    return default


def as_enum[E: StrEnum](cls: type[E], value: Any, default: E) -> E:
    try:
        return cls(value)
    except (TypeError, ValueError):
        return default


def _looks(value: Any) -> list[dict[str, Any]]:
    """Stored line looks (see ``Label.looks_before_template``), checked."""
    if not isinstance(value, list) or len(value) != 3:
        return []
    out = []
    for item in value:
        item = as_dict(item)
        out.append({"font_size_pt": as_float(item.get("font_size_pt"), 8.0, *FONT_SIZE_RANGE),
                    "bold": as_bool(item.get("bold"), False),
                    "italic": as_bool(item.get("italic"), False),
                    "align": as_enum(HAlign, item.get("align"), HAlign.CENTER)})
    return out


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
    def from_dict(cls, data: Any) -> TextLine:
        data, d = as_dict(data), cls()
        return cls(
            text=as_str(data.get("text"), d.text),
            enabled=as_bool(data.get("enabled"), d.enabled),
            font_family=as_str(data.get("font_family"), d.font_family).strip() or d.font_family,
            font_size_pt=as_float(data.get("font_size_pt"), d.font_size_pt, *FONT_SIZE_RANGE),
            bold=as_bool(data.get("bold"), d.bold),
            italic=as_bool(data.get("italic"), d.italic),
            align=as_enum(HAlign, data.get("align"), d.align),
        )


@dataclass
class LabelFormat:
    """Physical label size, as stored by Etiknivo 0.1.  **Not used**: every
    label is laid out for the label roll chosen in the printer settings
    (``Settings.label_size_mm``).  Still read and written so files stay
    readable by older versions."""

    width_mm: float = 30.0
    height_mm: float = 14.0

    @classmethod
    def from_dict(cls, data: Any) -> LabelFormat:
        data = as_dict(data)
        return cls(as_float(data.get("width_mm"), 30.0), as_float(data.get("height_mm"), 14.0))


@dataclass
class LabelStyle:
    """Label-wide layout properties."""

    valign: VAlign = VAlign.CENTER
    line_spacing_mm: float = 0.5
    margin_h_mm: float = 0.0  # on top of the profile's safe end margin
    margin_v_mm: float = 0.0
    autofit: bool = True
    #: with auto-fit: every label in the category gets the same size per line
    #: (the smallest one any of them needs); off, each label is as large as it fits
    same_size_in_category: bool = True
    #: 0, 90, 180 or 270 degrees counter-clockwise (content rotation, independent of
    #: the print orientation); 90 and 270 turn the text a quarter for upright labels
    rotation: int = 0
    border: bool = False
    #: thin line between text lines
    separators: bool = False
    invert: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> LabelStyle:
        data, d = as_dict(data), cls()
        rot = int(as_float(data.get("rotation"), 0.0)) % 360
        return cls(
            valign=as_enum(VAlign, data.get("valign"), d.valign),
            line_spacing_mm=as_float(data.get("line_spacing_mm"), d.line_spacing_mm,
                                     *LINE_SPACING_RANGE),
            margin_h_mm=as_float(data.get("margin_h_mm"), d.margin_h_mm, *MARGIN_H_RANGE),
            margin_v_mm=as_float(data.get("margin_v_mm"), d.margin_v_mm, *MARGIN_V_RANGE),
            autofit=as_bool(data.get("autofit"), d.autofit),
            same_size_in_category=as_bool(data.get("same_size_in_category"),
                                          d.same_size_in_category),
            rotation=rot if rot in (0, 90, 180, 270) else 0,
            border=as_bool(data.get("border"), d.border),
            separators=as_bool(data.get("separators"), d.separators),
            invert=as_bool(data.get("invert"), d.invert),
        )


class CodeKind(StrEnum):
    NONE = "none"
    QR = "qr"
    CODE128 = "code128"


class CodeSize(StrEnum):
    """How big a QR code or pictogram beside the text may get."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass
class LabelCode:
    """An optional QR code beside the text, or a Code 128 barcode in place of
    the bottom line.  *text* may contain ``{Name}`` fields."""

    kind: CodeKind = CodeKind.NONE
    text: str = "{Lade}"
    side: HAlign = HAlign.LEFT  # QR code: LEFT or RIGHT of the text
    valign: VAlign = VAlign.CENTER  # QR code: top, middle or bottom of its side
    size: CodeSize = CodeSize.MEDIUM  # QR code only
    #: in a template: the content readable under the QR code
    caption: bool = True

    @classmethod
    def from_dict(cls, data: Any) -> LabelCode:
        data, c = as_dict(data), cls()
        c.kind = as_enum(CodeKind, data.get("kind"), CodeKind.NONE)
        c.text = as_str(data.get("text"), c.text)
        c.side = HAlign.RIGHT if data.get("side") == HAlign.RIGHT else HAlign.LEFT
        c.valign = _valign(data.get("valign"))
        c.size = _size(data.get("size"))
        c.caption = data.get("caption") is not False
        return c


def _valign(value: Any) -> VAlign:
    return as_enum(VAlign, value, VAlign.CENTER)


def _size(value: Any) -> CodeSize:
    return as_enum(CodeSize, value, CodeSize.MEDIUM)


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
    valign: VAlign = VAlign.CENTER
    size: CodeSize = CodeSize.MEDIUM

    @classmethod
    def from_dict(cls, data: Any) -> LabelPicture:
        data, p = as_dict(data), cls()
        p.kind = as_enum(PictureKind, data.get("kind"), PictureKind.NONE)
        p.symbol = as_str(data.get("symbol"), p.symbol)
        p.image_png = as_str(data.get("image_png"))
        p.side = HAlign.RIGHT if data.get("side") == HAlign.RIGHT else HAlign.LEFT
        p.valign = _valign(data.get("valign"))
        p.size = _size(data.get("size"))
        return p


class ElementKind(StrEnum):
    TEXT = "text"
    QR = "qr"
    BARCODE = "barcode"
    SYMBOL = "symbol"
    IMAGE = "image"
    LINE = "line"
    BOX = "box"
    INVERT = "invert"


ELEMENT_TITLES: dict[ElementKind, str] = {
    ElementKind.TEXT: N_("Tekst"),
    ElementKind.QR: N_("QR-code"),
    ElementKind.BARCODE: N_("Barcode"),
    ElementKind.SYMBOL: N_("Symbool"),
    ElementKind.IMAGE: N_("Afbeelding"),
    ElementKind.LINE: N_("Lijn"),
    ElementKind.BOX: N_("Kader"),
    ElementKind.INVERT: N_("Wit op zwart"),
}

#: Smallest element side: one printer dot.
ELEMENT_MIN_MM = 0.125


@dataclass
class LabelElement:
    """A loose element of a label in the free layout.

    The box is in millimetres from the top-left corner of the printable area,
    in design orientation.  Text shrinks to fit its box; codes, symbols and
    images are scaled to fit and centred; a line fills its box (a thin box is
    a line); a frame is a one-dot outline of its box; "white on black" turns
    everything in its box over, drawn after the other elements.
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
    def from_dict(cls, data: Any) -> LabelElement:
        data, d = as_dict(data), cls()
        el = cls(
            kind=as_enum(ElementKind, data.get("kind"), ElementKind.TEXT),
            x_mm=as_float(data.get("x_mm"), d.x_mm, -50.0, 150.0),
            y_mm=as_float(data.get("y_mm"), d.y_mm, -50.0, 50.0),
            w_mm=as_float(data.get("w_mm"), d.w_mm, ELEMENT_MIN_MM, 150.0),
            h_mm=as_float(data.get("h_mm"), d.h_mm, ELEMENT_MIN_MM, 50.0),
            text=as_str(data.get("text")),
            font_family=as_str(data.get("font_family"), d.font_family).strip() or d.font_family,
            font_size_pt=as_float(data.get("font_size_pt"), d.font_size_pt, *FONT_SIZE_RANGE),
            bold=as_bool(data.get("bold"), d.bold),
            italic=as_bool(data.get("italic"), d.italic),
            align=as_enum(HAlign, data.get("align"), HAlign.CENTER),
            symbol=as_str(data.get("symbol")),
            image_png=as_str(data.get("image_png")),
            id=as_str(data.get("id")) or d.id,
        )
        el.resize(el.w_mm, el.h_mm)
        return el


#: the line and cell fields, that a name in capitals shows in capitals
_CAPITAL_FIELDS = {alias for key, (_, aliases) in PART_FIELDS.items()
                   if key in ("top", "main", "bottom") or key.startswith("cell")
                   for alias in aliases}


@dataclass
class UserTemplate:
    """A template of the user's own: elements as in the free layout, drawn on
    a printable area of *width_mm* x *height_mm*.  Their texts use the part
    fields (``{Hoofdregel}``, ``{Lade}``, ``{Code}``…) and a symbol of
    :data:`PICTOGRAM_FIELD` shows the label's pictogram, so every label fills
    the template with its own content.  On another roll the elements scale
    along."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    width_mm: float = 26.0
    height_mm: float = 12.0
    elements: list[LabelElement] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> UserTemplate:
        data, d = as_dict(data), cls()
        raw = data.get("elements")
        return cls(id=as_str(data.get("id")) or d.id, name=as_str(data.get("name")),
                   width_mm=as_float(data.get("width_mm"), d.width_mm, 5.0, 150.0),
                   height_mm=as_float(data.get("height_mm"), d.height_mm, 3.0, 50.0),
                   elements=[LabelElement.from_dict(x) for x in
                             (raw if isinstance(raw, list) else []) if isinstance(x, dict)])

    def key(self) -> str:
        """Hash of everything that affects how labels with it look."""
        d = self.to_dict()
        d.pop("name")
        return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


#: the user's own templates by id; the library keeps this up to date
_USER_TEMPLATES: dict[str, UserTemplate] = {}


def set_user_templates(templates: list[UserTemplate]) -> None:
    _USER_TEMPLATES.clear()
    _USER_TEMPLATES.update({t.id: t for t in templates})


def user_templates() -> list[UserTemplate]:
    return list(_USER_TEMPLATES.values())


def find_user_template(template_id: str) -> UserTemplate | None:
    return _USER_TEMPLATES.get(template_id)


def custom_template_key(template_id: str) -> str:
    """What a label with this own template depends on ("" when it is gone)."""
    tpl = _USER_TEMPLATES.get(template_id)
    return f"{template_id}:{tpl.key()}" if tpl else ""


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
    #: not used, see :class:`LabelFormat`
    format: LabelFormat = field(default_factory=LabelFormat)
    code: LabelCode = field(default_factory=LabelCode)
    picture: LabelPicture = field(default_factory=LabelPicture)
    #: ready-made arrangement of the lines, used unless ``layout`` is FREE
    template: LabelTemplate = LabelTemplate.NONE
    #: what a template switched on by itself ("picture", "code"), so it can be
    #: switched off again when the label leaves that template
    template_added: list[str] = field(default_factory=list)
    #: the lines' look (size, bold, italic, alignment) before the first
    #: template, given back when the label returns to the lines under each other
    looks_before_template: list[dict[str, Any]] = field(default_factory=list)
    #: id of the user's own template, when ``template`` is CUSTOM
    custom_template: str = ""
    #: whether a template puts the tray ID on the label
    template_tray: bool = True
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
        own = {spec_name(k).casefold(): v for k, v in self.specs.items()}
        base = {**values, **own}
        values.update({alias: value for key, value in self._part_values(base).items()
                       for alias in PART_FIELDS[key][1]})
        values.update(own)
        return values

    def _part_values(self, base: dict[str, str]) -> dict[str, str]:
        """What the part fields show; their own fields filled in from *base*."""
        def fill(text: str) -> str:
            return FIELD_RE.sub(lambda m: base.get(m.group(1).strip().casefold(), m.group(0)),
                                text)

        lines = [fill(ln.text) if ln.enabled else "" for ln in self.lines]
        cells = [c.strip() for c in lines[SLOT_BOTTOM].split("|") if c.strip()]
        m = TRAY_RE.match(self.tray_id)
        out = {"top": lines[SLOT_TOP], "main": lines[SLOT_MAIN], "bottom": lines[SLOT_BOTTOM],
               "code": fill(self.code.text),
               "tray_row": m.group(1) if m else self.tray_id,
               "tray_number": m.group(2) if m else ""}
        out.update({f"cell{n}": cells[n - 1] if n <= len(cells) else "" for n in range(1, 7)})
        return out

    @property
    def is_free(self) -> bool:
        return self.layout == LayoutPreset.FREE

    @property
    def uses_template(self) -> bool:
        """Whether a template lays out the label (and the free layout does not)."""
        return not self.is_free and self.template != LabelTemplate.NONE

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
            name = m.group(1).strip()
            key = name.casefold()
            if key in values:
                if key in _CAPITAL_FIELDS and name.isupper():
                    return values[key].upper()
                return values[key]
            unknown.append(name)
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
        code = asdict(self.code)
        if code["caption"]:  # the default: keys made before it stay the same
            del code["caption"]
        d: dict[str, object] = {"lines": [asdict(x) for x in self.lines], "code": code,
             "picture": asdict(self.picture)}
        if self.template != LabelTemplate.NONE:
            d["template"] = str(self.template)
        if not self.template_tray:
            d["template_tray"] = False
        if self.template == LabelTemplate.CUSTOM:
            d["custom_template"] = custom_template_key(self.custom_template)
        return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()

    # -- (de)serialisation -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["layout"] = str(self.layout)
        d["template"] = str(self.template)
        return d

    @classmethod
    def from_dict(cls, data: Any) -> Label:
        """A label from its stored form.  Missing fields get their default;
        fields of the wrong type or out of range too (see :func:`as_float`)."""
        data = as_dict(data)
        raw_lines = data.get("lines")
        lines = [TextLine.from_dict(x) for x in (raw_lines if isinstance(raw_lines, list)
                                                  else [])][:3]
        while len(lines) < 3:
            lines.append(TextLine(enabled=False))
        raw_elements = data.get("elements")
        raw_specs = data.get("specs")
        lbl = cls(
            id=as_str(data.get("id")) or uuid.uuid4().hex,
            name=as_str(data.get("name")),
            tray_id=as_str(data.get("tray_id")),
            category=as_str(data.get("category")),
            layout=as_enum(LayoutPreset, data.get("layout"), LayoutPreset.CUSTOM),
            lines=lines,
            template=as_enum(LabelTemplate, data.get("template"), LabelTemplate.NONE),
            template_added=[x for x in (data.get("template_added") if isinstance(
                data.get("template_added"), list) else [])
                if x in ("picture", "code", "code_text", "code_barcode")],
            looks_before_template=_looks(data.get("looks_before_template")),
            template_tray=data.get("template_tray") is not False,
            custom_template=as_str(data.get("custom_template")),
            style=LabelStyle.from_dict(data.get("style")),
            format=LabelFormat.from_dict(data.get("format")),
            code=LabelCode.from_dict(data.get("code")),
            picture=LabelPicture.from_dict(data.get("picture")),
            elements=[LabelElement.from_dict(x)
                      for x in (raw_elements if isinstance(raw_elements, list) else [])
                      if isinstance(x, dict)],
            elements_from=as_str(data.get("elements_from")),
            specs={str(k): as_str(v) for k, v in as_dict(raw_specs).items()},
            notes=as_str(data.get("notes")),
        )
        if as_str(data.get("created")):
            lbl.created = as_str(data["created"])
        if as_str(data.get("modified")):
            lbl.modified = as_str(data["modified"])
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
             "code": asdict(self.code),
             "picture": asdict(self.picture), "layout": str(self.layout),
             "template": str(self.template), "template_tray": self.template_tray,
             "custom_template": custom_template_key(self.custom_template)
             if self.template == LabelTemplate.CUSTOM else "",
             "elements": [asdict(x) for x in self.elements] if self.is_free else [],
             "fields": self.field_values()}
        return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


#: Parts of a label's look that "Opmaak overnemen" can copy; the text stays.
FORMAT_PARTS = {
    "layout": N_("Layout, sjabloon en lettertypen"),
    "style": N_("Opmaak (uitlijning, marges, rand, rotatie)"),
    "code": N_("QR-code of barcode"),
    "picture": N_("Pictogram"),
}


def copy_format(src: Label, dst: Label, parts: set[str] | list[str]) -> None:
    """Give *dst* the look of *src* for the chosen *parts*; texts, names,
    specifications and notes stay as they are."""
    if "layout" in parts:
        dst.layout = src.layout
        dst.template = src.template
        dst.template_tray = src.template_tray
        dst.custom_template = src.custom_template
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
