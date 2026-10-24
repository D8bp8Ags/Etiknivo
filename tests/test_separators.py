"""Separator lines between text lines."""

from __future__ import annotations

from etiknivo.model import Label, LabelStyle, make_label
from etiknivo.rendering.engine import RenderEngine


def black_rows(engine: RenderEngine, lbl: Label) -> list[int]:
    """Rows of the design image that are black across most of the text width."""
    r = engine.render(lbl)
    img = r.mono.convert("L")
    x0, _, x1, _ = (round(v) for v in r.content_box)
    return [y for y in range(img.height)
            if sum(img.getpixel((x, y)) == 0 for x in range(x0, x1)) > 0.9 * (x1 - x0)]


def test_separator_between_each_pair_of_lines(engine: RenderEngine) -> None:
    lbl = make_label("A1", "Weerstanden", "10 kΩ", "¼ W")
    assert black_rows(engine, lbl) == []
    lbl.style.separators = True
    rows = black_rows(engine, lbl)
    assert len(rows) == 2
    boxes = engine.render(lbl).lines
    for row, (above, below) in zip(rows, zip(boxes, boxes[1:])):
        assert above.y1 <= row < below.y0


def test_single_line_has_no_separator(engine: RenderEngine) -> None:
    lbl = make_label("", "", "Alleen dit")
    lbl.style.separators = True
    assert black_rows(engine, lbl) == []


def test_separators_survive_saving() -> None:
    style = LabelStyle(separators=True)
    assert LabelStyle.from_dict({"separators": True}) == style
    assert LabelStyle.from_dict({}).separators is False
