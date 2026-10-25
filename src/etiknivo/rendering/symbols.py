"""Etiknivo's own symbols for labels, grouped in categories.

Each symbol is a short list of drawing primitives on a 24 × 24 grid, drawn
with Pillow, so the same code serves the label renderer and the picker in the
GUI.  The shapes are the usual schematic conventions, drawn for Etiknivo with a
heavy stroke that stays legible at 203 dpi.  They fall under the app's MIT
licence.

Primitives (coordinates in grid units):

``("line", x0, y0, x1, y1, ...)``   polyline with round ends
``("rect", x0, y0, x1, y1)``        outline; ``("box", ...)`` is filled
``("circle", cx, cy, r)``           outline; ``("dot", cx, cy, r)`` is filled
``("poly", x0, y0, x1, y1, ...)``   closed outline; ``("fill", ...)`` is filled
``("arc", cx, cy, r, start, end)``  degrees, clockwise from 3 o'clock (Pillow)
"""

from __future__ import annotations

import functools
import math
import re

from PIL import Image, ImageDraw, ImageOps

from etiknivo.i18n import N_

GRID = 24.0
STROKE = 1.9  # grid units


def _hexagon(cx: float, cy: float, r: float) -> tuple[float, ...]:
    pts: list[float] = []
    for k in range(6):
        a = math.radians(60 * k)
        pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return tuple(pts)


def _turned(cx: float, cy: float, degrees: float, *xy: float) -> tuple[float, ...]:
    """Points *xy* turned clockwise around (cx, cy)."""
    a = math.radians(degrees)
    out: list[float] = []
    for x, y in zip(xy[::2], xy[1::2], strict=True):
        dx, dy = x - cx, y - cy
        out += [cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)]
    return tuple(out)


def _star(cx: float, cy: float, r_out: float, r_in: float) -> tuple[float, ...]:
    pts: list[float] = []
    for k in range(10):
        a = math.radians(-90 + 36 * k)
        r = r_out if k % 2 == 0 else r_in
        pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return tuple(pts)


_ARROW = (("line", 12.5, 7.5, 16.5, 3.5), ("fill", 17.5, 2.5, 13.8, 3.3, 16.7, 6.2),
          ("line", 16.0, 9.5, 20.0, 5.5), ("fill", 21.0, 4.5, 17.3, 5.3, 20.2, 8.2))

#: key -> (name to show, primitives)
SYMBOLS: dict[str, tuple[str, tuple[tuple, ...]]] = {
    "resistor": (N_("Weerstand"), (
        ("line", 1, 12, 6, 12), ("rect", 6, 8.5, 18, 15.5), ("line", 18, 12, 23, 12))),
    "potentiometer": (N_("Potmeter"), (
        ("line", 1, 12, 6, 12), ("rect", 6, 8.5, 18, 15.5), ("line", 18, 12, 23, 12),
        ("line", 6, 20, 17, 5.5), ("fill", 18.5, 3.5, 14.2, 5.2, 17.6, 7.8))),
    "capacitor": (N_("Condensator"), (
        ("line", 1, 12, 10, 12), ("line", 10, 5, 10, 19), ("line", 14, 5, 14, 19),
        ("line", 14, 12, 23, 12))),
    "electrolytic": (N_("Elco"), (
        ("line", 1, 12, 9.5, 12), ("line", 9.5, 5, 9.5, 19), ("box", 13, 5, 15.5, 19),
        ("line", 15.5, 12, 23, 12), ("line", 3, 6, 7, 6), ("line", 5, 4, 5, 8))),
    "diode": (N_("Diode"), (
        ("line", 1, 12, 8, 12), ("poly", 8, 6.5, 8, 17.5, 16, 12), ("line", 16, 6, 16, 18),
        ("line", 16, 12, 23, 12))),
    "led": (N_("LED"), (
        ("line", 1, 14, 6, 14), ("poly", 6, 9, 6, 19, 13, 14), ("line", 13, 8.5, 13, 19.5),
        ("line", 13, 14, 23, 14)) + _ARROW),
    "transistor": (N_("Transistor"), (
        ("circle", 13, 12, 9.5), ("line", 9, 7, 9, 17), ("line", 1.5, 12, 9, 12),
        ("line", 9, 10, 15, 6, 15, 1.5), ("line", 9, 14, 15, 18, 15, 22.5),
        ("fill", 15.5, 18.4, 11.2, 18.2, 13.6, 14.6))),
    "ic": (N_("IC"), (
        ("rect", 7, 3, 17, 21), ("arc", 12, 3, 2.2, 0, 180),
        ("line", 2.5, 7, 7, 7), ("line", 2.5, 12, 7, 12), ("line", 2.5, 17, 7, 17),
        ("line", 17, 7, 21.5, 7), ("line", 17, 12, 21.5, 12), ("line", 17, 17, 21.5, 17))),
    "fuse": (N_("Zekering"), (
        ("rect", 5, 8.5, 19, 15.5), ("line", 1, 12, 23, 12))),
    "switch": (N_("Schakelaar"), (
        ("line", 1, 15, 6, 15), ("dot", 7, 15, 1.4), ("line", 7.5, 14.5, 17.5, 7),
        ("dot", 17, 15, 1.4), ("line", 18, 15, 23, 15))),
    "connector": (N_("Connector"), (
        ("rect", 3, 6.5, 21, 17.5), ("dot", 8, 12, 1.8), ("dot", 12, 12, 1.8),
        ("dot", 16, 12, 1.8), ("line", 7, 17.5, 7, 21), ("line", 17, 17.5, 17, 21))),
    "battery": (N_("Batterij"), (
        ("line", 1, 12, 9, 12), ("line", 9, 4.5, 9, 19.5), ("box", 12.5, 8, 15, 16),
        ("line", 15, 12, 23, 12), ("line", 3, 5.5, 7, 5.5), ("line", 5, 3.5, 5, 7.5))),
    "inductor": (N_("Spoel"), (
        ("line", 1, 14, 3, 14), ("arc", 5.25, 14, 2.25, 180, 360),
        ("arc", 9.75, 14, 2.25, 180, 360), ("arc", 14.25, 14, 2.25, 180, 360),
        ("arc", 18.75, 14, 2.25, 180, 360), ("line", 21, 14, 23, 14))),
    "crystal": (N_("Kristal"), (
        ("line", 1, 12, 6.5, 12), ("line", 6.5, 6.5, 6.5, 17.5), ("rect", 9.5, 5.5, 14.5, 18.5),
        ("line", 17.5, 6.5, 17.5, 17.5), ("line", 17.5, 12, 23, 12))),
    "ground": (N_("Aarde"), (
        ("line", 12, 2, 12, 11), ("line", 4, 11, 20, 11), ("line", 7, 15, 17, 15),
        ("line", 10, 19, 14, 19))),
    "screw": (N_("Schroef"), (
        ("rect", 5.5, 2.5, 18.5, 7), ("line", 9, 7, 9, 19, 12, 22.5, 15, 19, 15, 7),
        ("line", 9, 10, 15, 12), ("line", 9, 13.5, 15, 15.5), ("line", 9, 17, 15, 19))),
    "nut": (N_("Moer"), (
        ("poly",) + _hexagon(12, 12, 9.5), ("circle", 12, 12, 4))),
    "cable": (N_("Kabel"), (
        ("line", 2, 17, 7, 17, 10, 14, 10, 10, 13, 7, 17, 7), ("box", 17, 4.5, 21.5, 9.5),
        ("line", 21.5, 6, 23, 6), ("line", 21.5, 8, 23, 8), ("box", 1, 14.5, 5, 19.5))),
    # -- electronics, more ------------------------------------------------------------
    "speaker": (N_("Luidspreker"), (
        ("rect", 3, 8.5, 7, 15.5), ("poly", 7, 8.5, 12.5, 4, 12.5, 20, 7, 15.5),
        ("arc", 13, 12, 4.5, 305, 415), ("arc", 13, 12, 8.5, 305, 415))),
    "antenna": (N_("Antenne"), (
        ("line", 12, 22, 12, 10), ("poly", 4.5, 3, 19.5, 3, 12, 10))),
    # -- power and cables -------------------------------------------------------------
    "cell": (N_("Batterijcel"), (
        ("rect", 3, 8, 18.5, 16), ("box", 18.5, 10, 21.5, 14), ("line", 6.5, 12, 9.5, 12),
        ("line", 13, 12, 16, 12), ("line", 14.5, 10.5, 14.5, 13.5))),
    "lightning": (N_("Spanning"), (
        ("fill", 14, 1.5, 5, 13.5, 11, 13.5, 9.5, 22.5, 19, 9.5, 13, 9.5, 16, 1.5),)),
    "bulb": (N_("Lamp"), (
        ("circle", 12, 9, 6.5), ("line", 9.5, 15.5, 9.5, 18, 14.5, 18, 14.5, 15.5),
        ("line", 10, 21, 14, 21))),
    "socket": (N_("Stopcontact"), (
        ("circle", 12, 12, 9.5), ("dot", 8.3, 12, 1.9), ("dot", 15.7, 12, 1.9))),
    "power_plug": (N_("Stekker"), (
        ("rect", 6, 9, 18, 17.5), ("line", 9.5, 3, 9.5, 9), ("line", 14.5, 3, 14.5, 9),
        ("line", 12, 17.5, 12, 22.5))),
    "usb": (N_("USB"), (
        ("line", 12, 5, 12, 19.5), ("fill", 12, 1.5, 9.3, 6, 14.7, 6), ("dot", 12, 20.5, 2.2),
        ("line", 12, 16, 6.5, 12, 6.5, 9), ("dot", 6.5, 8, 1.9),
        ("line", 12, 13.5, 17.5, 10, 17.5, 7.5), ("box", 15.8, 4.5, 19.2, 7.8))),
    # -- fasteners --------------------------------------------------------------------
    "bolt": (N_("Bout"), (
        ("rect", 5.5, 2.5, 18.5, 7), ("line", 9.5, 7, 9.5, 21.5, 14.5, 21.5, 14.5, 7),
        ("line", 9.5, 11, 14.5, 11), ("line", 9.5, 14.5, 14.5, 14.5),
        ("line", 9.5, 18, 14.5, 18))),
    "washer": (N_("Ring"), (("circle", 12, 12, 9.5), ("circle", 12, 12, 4))),
    "nail": (N_("Spijker"), (
        ("line", 6, 3.5, 18, 3.5), ("line", 12, 3.5, 12, 18), ("fill", 10.6, 17.5, 13.4, 17.5,
                                                               12, 22.5))),
    "wall_plug": (N_("Plug"), (
        ("poly", 8, 2.5, 16, 2.5, 15, 19.5, 12, 22, 9, 19.5), ("line", 8.4, 8, 15.6, 8),
        ("line", 8.8, 13.5, 15.2, 13.5))),
    "hook": (N_("Haak"), (
        ("line", 16, 2.5, 16, 15), ("arc", 12, 15, 4, 0, 180), ("line", 8, 15, 8, 12))),
    "spring": (N_("Veer"), (
        ("line", 12, 1.5, 12, 4, 6, 6.5, 18, 9.5, 6, 12.5, 18, 15.5, 6, 18.5, 12, 20.5, 12,
         22.5),)),
    # -- tools ------------------------------------------------------------------------
    "hammer": (N_("Hamer"), (
        ("box", 3.5, 2.5, 15.5, 7.5), ("fill", 15.5, 3.5, 21, 2, 21, 4, 15.5, 6.5),
        ("box", 8.5, 7.5, 11.5, 22))),
    "screwdriver": (N_("Schroevendraaier"), (
        ("box", 9, 2, 15, 10), ("line", 12, 10, 12, 19),
        ("fill", 10.6, 19, 13.4, 19, 12.8, 22, 11.2, 22))),
    "wrench": (N_("Steeksleutel"), (
        ("fill", *_turned(12, 12, 45, 9, 2, 10.5, 2, 10.5, 6, 13.5, 6, 13.5, 2, 15, 2, 17,
                          4.5, 17, 8, 14, 10.5, 14, 23, 10, 23, 10, 10.5, 7, 8, 7, 4.5)),)),
    "saw": (N_("Zaag"), (
        ("line", 2, 10, 15, 10), ("line", 2, 10, 2, 14, 3.5, 15.5, 5, 14, 6.5, 15.5, 8, 14,
                                  9.5, 15.5, 11, 14, 12.5, 15.5, 14, 14, 15, 14, 15, 10),
        ("rect", 15, 7.5, 21.5, 16.5))),
    "ruler": (N_("Liniaal"), (
        ("rect", 2, 8, 22, 16), ("line", 6, 8, 6, 12), ("line", 10, 8, 10, 11),
        ("line", 14, 8, 14, 12), ("line", 18, 8, 18, 11))),
    "drill": (N_("Boor"), (
        ("box", 10.3, 1.5, 13.7, 7.5), ("line", 10.5, 7.5, 10.5, 17.5, 12, 22, 13.5, 17.5,
                                          13.5, 7.5),
        ("line", 10.5, 9.5, 13.5, 12), ("line", 10.5, 13, 13.5, 15.5))),
    # -- home and kitchen -------------------------------------------------------------
    "house": (N_("Huis"), (
        ("line", 2.5, 11.5, 12, 3, 21.5, 11.5), ("line", 5.5, 9, 5.5, 21, 18.5, 21, 18.5, 9),
        ("line", 10, 21, 10, 15, 14, 15, 14, 21))),
    "jar": (N_("Pot"), (
        ("rect", 5.5, 3, 18.5, 6.5), ("rect", 6.5, 9, 17.5, 21.5), ("line", 9, 14, 15, 14))),
    "bottle": (N_("Fles"), (
        ("poly", 10, 2.5, 14, 2.5, 14, 7, 17, 10, 17, 21.5, 7, 21.5, 7, 10, 10, 7),
        ("line", 7, 13, 17, 13))),
    "mug": (N_("Mok"), (
        ("poly", 4.5, 6, 15.5, 6, 15.5, 20.5, 4.5, 20.5), ("arc", 15.5, 13, 3.5, 270, 450))),
    "cutlery": (N_("Bestek"), (
        ("line", 4.5, 2.5, 4.5, 7, 7, 9.5, 9.5, 7, 9.5, 2.5), ("line", 7, 2.5, 7, 21.5),
        ("fill", 15, 2, 18.5, 3.5, 18.5, 11.5, 15, 11.5), ("line", 16.5, 11, 16.5, 21.5))),
    "snowflake": (N_("Vriezer"), (
        ("line", 12, 2, 12, 22), ("line", 3.3, 7, 20.7, 17), ("line", 3.3, 17, 20.7, 7),
        ("line", 9.5, 3.5, 12, 6, 14.5, 3.5), ("line", 9.5, 20.5, 12, 18, 14.5, 20.5))),
    "flame": (N_("Vlam"), (
        ("poly", 12, 2, 16.5, 7.5, 18.5, 12.5, 18, 17.5, 15, 21, 12, 22, 9, 21, 6, 17.5,
         5.5, 13, 8, 9, 10, 12, 10.5, 7),)),
    "drop": (N_("Water"), (
        ("poly", 12, 2, 16.5, 9, 18.5, 14, 17, 19, 12, 22, 7, 19, 5.5, 14, 7.5, 9),)),
    "leaf": (N_("Plant"), (
        ("poly", 3.5, 20.5, 4.5, 13, 8.5, 7, 14.5, 4, 20.5, 3.5, 20, 9.5, 17, 15.5, 11.5,
         19.5),
        ("line", 3.5, 20.5, 15, 9))),
    # -- office and storage -----------------------------------------------------------
    "box": (N_("Doos"), (
        ("rect", 3, 8.5, 21, 21), ("line", 3, 8.5, 6, 3.5, 18, 3.5, 21, 8.5),
        ("line", 9, 12.5, 15, 12.5))),
    "folder": (N_("Map"), (
        ("poly", 2.5, 4.5, 9, 4.5, 11, 7.5, 21.5, 7.5, 21.5, 20, 2.5, 20),)),
    "document": (N_("Document"), (
        ("poly", 5, 2.5, 14, 2.5, 19, 7.5, 19, 21.5, 5, 21.5), ("line", 14, 2.5, 14, 7.5, 19,
                                                                7.5),
        ("line", 8, 12, 16, 12), ("line", 8, 15.5, 16, 15.5), ("line", 8, 19, 13, 19))),
    "envelope": (N_("Envelop"), (("rect", 2.5, 5.5, 21.5, 18.5), ("line", 2.5, 5.5, 12, 13,
                                                                 21.5, 5.5))),
    "pencil": (N_("Potlood"), (
        ("poly", 3.5, 20.5, 5, 15, 16, 4, 20, 8, 9, 19), ("line", 13.5, 6.5, 17.5, 10.5),
        ("line", 5, 15, 9, 19))),
    "scissors": (N_("Schaar"), (
        ("circle", 6.5, 18, 3.2), ("circle", 17.5, 18, 3.2), ("line", 8.5, 15.5, 18, 2.5),
        ("line", 15.5, 15.5, 6, 2.5))),
    "book": (N_("Boek"), (
        ("poly", 2.5, 4, 8.5, 4, 12, 6.5, 12, 21, 8.5, 19, 2.5, 19),
        ("poly", 21.5, 4, 15.5, 4, 12, 6.5, 12, 21, 15.5, 19, 21.5, 19))),
    "tag": (N_("Label"), (
        ("poly", 3, 3, 12, 3, 21, 12, 12, 21, 3, 12), ("dot", 7.5, 7.5, 1.8))),
    "key": (N_("Sleutel"), (
        ("circle", 7, 12, 4.5), ("line", 11.5, 12, 21.5, 12), ("line", 17.5, 12, 17.5, 16),
        ("line", 21, 12, 21, 15))),
    # -- signs ------------------------------------------------------------------------
    "warning": (N_("Let op"), (
        ("poly", 12, 2.5, 22, 20.5, 2, 20.5), ("line", 12, 9, 12, 14), ("dot", 12, 17.2, 1.4))),
    "prohibited": (N_("Verboden"), (("circle", 12, 12, 9.5), ("line", 5.3, 5.3, 18.7, 18.7))),
    "info": (N_("Informatie"), (
        ("circle", 12, 12, 9.5), ("line", 12, 10.5, 12, 17), ("dot", 12, 7, 1.5))),
    "check": (N_("Vinkje"), (("line", 3.5, 12.5, 9.5, 18.5, 20.5, 5.5),)),
    "cross": (N_("Kruis"), (("line", 5, 5, 19, 19), ("line", 19, 5, 5, 19))),
    "this_way_up": (N_("Deze kant boven"), (
        ("line", 7.5, 20, 7.5, 7), ("fill", 7.5, 2, 3.8, 7.5, 11.2, 7.5),
        ("line", 16.5, 20, 16.5, 7), ("fill", 16.5, 2, 12.8, 7.5, 20.2, 7.5),
        ("line", 3, 22, 21, 22))),
    "fragile": (N_("Breekbaar"), (
        ("poly", 6, 2.5, 18, 2.5, 17, 9.5, 14, 13, 10, 13, 7, 9.5), ("line", 12, 13, 12, 20),
        ("line", 8, 21, 16, 21), ("line", 11, 2.5, 12.5, 5.5, 10.5, 8))),
    "star": (N_("Ster"), (("poly",) + _star(12, 12.5, 10, 4.2),)),
    "heart": (N_("Hart"), (
        ("arc", 8, 9, 4.5, 135, 360), ("arc", 16, 9, 4.5, 180, 405),
        ("line", 4.8, 12.2, 12, 19.5, 19.2, 12.2))),
}


#: The symbols per category, in the order of the picker.
SYMBOL_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (N_("Elektronica"), ("resistor", "potentiometer", "capacitor", "electrolytic", "inductor",
                         "diode", "led", "transistor", "ic", "crystal", "fuse", "switch",
                         "ground", "speaker", "antenna")),
    (N_("Stroom en kabels"), ("battery", "cell", "lightning", "bulb", "socket", "power_plug",
                              "usb", "connector", "cable")),
    (N_("Bevestiging"), ("screw", "bolt", "nut", "washer", "nail", "wall_plug", "hook",
                         "spring")),
    (N_("Gereedschap"), ("hammer", "screwdriver", "wrench", "saw", "ruler", "drill")),
    (N_("Huis en keuken"), ("house", "jar", "bottle", "mug", "cutlery", "snowflake", "flame",
                            "drop", "leaf")),
    (N_("Kantoor en opslag"), ("box", "folder", "document", "envelope", "pencil", "scissors",
                               "book", "tag", "key")),
    (N_("Aanduidingen"), ("warning", "prohibited", "info", "check", "cross", "this_way_up",
                          "fragile", "star", "heart")),
)


def symbol_names() -> list[str]:
    return list(SYMBOLS)


@functools.cache
def ink_box(key: str) -> tuple[float, float, float, float]:
    """The part of the square that symbol *key* inks, as fractions (0 to 1)
    of its size: (left, top, right, bottom)."""
    size = 480
    box = ImageOps.invert(draw_symbol(key, size)).getbbox() or (0, 0, size, size)
    return tuple(v / size for v in box)  # type: ignore[return-value]


def draw_symbol(key: str, size_px: int) -> Image.Image:
    """Symbol *key* as a grey image (white background, black lines) of
    *size_px* × *size_px*.  Unknown keys give an empty image."""
    img = Image.new("L", (size_px, size_px), 255)
    if key not in SYMBOLS:
        return img
    d = ImageDraw.Draw(img)
    s = size_px / GRID
    w = max(1, round(STROKE * s))
    r = w / 2

    def pts(values: tuple) -> list[tuple[float, float]]:
        return [(values[i] * s, values[i + 1] * s) for i in range(0, len(values), 2)]

    def cap(x: float, y: float) -> None:
        d.ellipse((x - r, y - r, x + r, y + r), fill=0)

    for prim in SYMBOLS[key][1]:
        kind, args = prim[0], prim[1:]
        if kind == "line":
            p = pts(args)
            d.line(p, fill=0, width=w, joint="curve")
            for x, y in p:
                cap(x, y)
        elif kind in ("rect", "box"):
            x0, y0, x1, y1 = (v * s for v in args)
            if kind == "box":
                d.rectangle((x0, y0, x1, y1), fill=0)
            else:
                d.rectangle((x0 - r, y0 - r, x1 + r, y1 + r), outline=0, width=w)
        elif kind in ("circle", "dot"):
            cx, cy, rad = (v * s for v in args)
            if kind == "dot":
                d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=0)
            else:
                d.ellipse((cx - rad - r, cy - rad - r, cx + rad + r, cy + rad + r),
                          outline=0, width=w)
        elif kind in ("poly", "fill"):
            p = pts(args)
            if kind == "fill":
                d.polygon(p, fill=0)
            else:
                d.line(p + [p[0]], fill=0, width=w, joint="curve")
                for x, y in p:
                    cap(x, y)
        elif kind == "arc":
            cx, cy, rad = (v * s for v in args[:3])
            start, end = args[3:]
            d.arc((cx - rad - r, cy - rad - r, cx + rad + r, cy + rad + r), start, end,
                  fill=0, width=w)
            for a in (start, end):
                cap(cx + rad * math.cos(math.radians(a)), cy + rad * math.sin(math.radians(a)))
        else:
            raise ValueError(kind)
    return img


#: (word at the start of a word in the category or name, symbol); the first
#: match wins, so specific words come before general ones
SUGGESTIONS: tuple[tuple[str, str], ...] = (
    ("audiojack", "connector"), ("jack", "connector"), ("dupont", "connector"),
    ("lasklem", "connector"), ("wago", "connector"), ("connector", "connector"),
    ("breadboard", "connector"), ("krimpkous", "cable"), ("isolatie", "cable"),
    ("header", "connector"), ("klem", "connector"),
    ("schuifpot", "potentiometer"), ("potmeter", "potentiometer"),
    ("potentiometer", "potentiometer"), ("encoder", "potentiometer"),
    ("weerstand", "resistor"), ("resistor", "resistor"),
    ("elco", "electrolytic"), ("condensator", "capacitor"), ("capacitor", "capacitor"),
    ("led", "led"), ("diode", "diode"), ("transistor", "transistor"), ("mosfet", "transistor"),
    ("ic", "ic"), ("esp32", "ic"), ("esp8266", "ic"), ("arduino", "ic"), ("logica", "ic"),
    ("microcontroller", "ic"), ("chip", "ic"),
    ("zekering", "fuse"), ("fuse", "fuse"),
    ("drukknop", "switch"), ("schakelaar", "switch"), ("knop", "switch"), ("switch", "switch"),
    ("button", "switch"),
    ("spoel", "inductor"), ("inductor", "inductor"), ("kristal", "crystal"),
    ("crystal", "crystal"), ("oscillator", "crystal"),
    ("antenne", "antenna"), ("antenna", "antenna"),
    ("buzzer", "speaker"), ("speaker", "speaker"), ("luidspreker", "speaker"),
    ("audio", "speaker"),
    ("usb", "usb"), ("batterij", "battery"), ("battery", "battery"), ("accu", "battery"),
    ("voeding", "power_plug"), ("adapter", "power_plug"), ("stekker", "power_plug"),
    ("stopcontact", "socket"), ("lamp", "bulb"),
    ("kabel", "cable"), ("draad", "cable"), ("cable", "cable"), ("wire", "cable"),
    ("schroef", "screw"), ("screw", "screw"), ("moer", "nut"), ("bout", "bolt"),
    ("ring", "washer"), ("spijker", "nail"), ("plug", "wall_plug"), ("haak", "hook"),
    ("veer", "spring"), ("hamer", "hammer"), ("schroevendraaier", "screwdriver"),
    ("sleutel", "key"), ("zaag", "saw"), ("boor", "drill"), ("lijm", "bottle"),
    ("tape", "tag"), ("label", "tag"), ("papier", "document"), ("pennen", "pencil"),
    ("pen", "pencil"),
)


def suggest_symbol(*texts: str) -> str | None:
    """A fitting symbol for a label with these texts (category first, then
    name), or None when nothing fits."""
    for text in texts:
        low = text.casefold()
        for word, key in SUGGESTIONS:
            # short words must be whole (plurals allowed): "ring" is not "ringkern"
            end = r"(?:en|pen|s|n|e)?(?![a-z0-9])" if len(word) <= 5 else ""
            if re.search(rf"(?<![a-z0-9]){re.escape(word)}{end}", low):
                return key
    return None
