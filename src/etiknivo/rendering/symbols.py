"""Etiknivo's own electronics symbols for labels.

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

import math

from PIL import Image, ImageDraw

from etiknivo.i18n import N_

GRID = 24.0
STROKE = 1.9  # grid units


def _hexagon(cx: float, cy: float, r: float) -> tuple[float, ...]:
    pts: list[float] = []
    for k in range(6):
        a = math.radians(60 * k)
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
}


def symbol_names() -> list[str]:
    return list(SYMBOLS)


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
