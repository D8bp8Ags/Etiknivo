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
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from etiknivo.i18n import N_, tr

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


class HAlign(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class VAlign(StrEnum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class LayoutPreset(StrEnum):
    """The three standard layouts plus a free 'custom' mode."""

    SINGLE = "single"
    MAIN_SPEC = "main_spec"
    CATEGORY_MAIN_SPEC = "category_main_spec"
    CUSTOM = "custom"


LAYOUT_TITLES: dict[LayoutPreset, str] = {
    LayoutPreset.SINGLE: N_("1 · Alleen grote naam"),
    LayoutPreset.MAIN_SPEC: N_("2 · Naam + specificatie"),
    LayoutPreset.CATEGORY_MAIN_SPEC: N_("3 · Categorie + naam + specificatie"),
    LayoutPreset.CUSTOM: N_("Aangepast"),
}


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


def default_lines() -> list[TextLine]:
    return [TextLine(), TextLine(), TextLine()]


@dataclass
class Label:
    """A single label in the library."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "Nieuw label"
    tray_id: str = ""
    category: str = ""
    layout: LayoutPreset = LayoutPreset.CATEGORY_MAIN_SPEC
    lines: list[TextLine] = field(default_factory=default_lines)
    style: LabelStyle = field(default_factory=LabelStyle)
    format: LabelFormat = field(default_factory=LabelFormat)
    code: LabelCode = field(default_factory=LabelCode)
    picture: LabelPicture = field(default_factory=LabelPicture)
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
        """Slots that will actually be rendered (enabled and non-empty).  A
        barcode takes the place of the bottom line."""
        return [(i, ln) for i, ln in enumerate(self.lines)
                if ln.enabled and self.resolve(ln.text)[0].strip()
                and not (i == SLOT_BOTTOM and self.code.kind == CodeKind.CODE128)]

    # -- fields ----------------------------------------------------------------

    def field_names(self) -> list[str]:
        """Names usable as ``{Name}``: the specifications, then the built-ins."""
        own = [k for k in self.specs if k]
        taken = {k.casefold() for k in own}
        return own + [tr(shown) for shown, _ in BUILTIN_FIELDS.values()
                      if tr(shown).casefold() not in taken]

    def field_values(self) -> dict[str, str]:
        values = {alias: getattr(self, attr) for attr, (_, aliases) in BUILTIN_FIELDS.items()
                  for alias in aliases}
        values.update({k.strip().casefold(): v for k, v in self.specs.items()})
        return values

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
        default styling change."""
        self.layout = LayoutPreset(preset)
        if preset == LayoutPreset.CUSTOM:
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
             "picture": asdict(self.picture),
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
    lbl.name = name or (f"{main} – {spec}" if spec else main) or "Nieuw label"
    return lbl
