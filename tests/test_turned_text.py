"""Text turned a quarter (90° / 270°) for upright labels."""

from __future__ import annotations

import pytest

from etiknivo.model import Label, make_label
from etiknivo.rendering.engine import RenderEngine


def _ink_box(img):  # noqa: ANN001, ANN202
    return img.convert("L").point(lambda v: 255 - v).getbbox()


@pytest.mark.parametrize("rotation", [90, 270])
def test_turned_label_is_tall_ink(rotation: int) -> None:
    eng = RenderEngine()
    lbl = make_label("A1", "", "Weerstanden", "")
    flat = eng.render(lbl)
    lbl.style.rotation = rotation
    r = eng.render(lbl)
    assert r.raster.size == flat.raster.size
    x0, y0, x1, y1 = _ink_box(r.mono)
    fx0, fy0, fx1, fy1 = _ink_box(flat.mono)
    assert (y1 - y0) > (x1 - x0)  # the word runs across the label now
    assert (fx1 - fx0) > (fy1 - fy0)
    px0, py0, px1, py1 = eng.printable_box
    assert px0 <= x0 and x1 <= px1 and py0 <= y0 and y1 <= py1
    assert not r.warnings and not r.has_overflow
    lb = r.lines[0]
    assert px0 <= lb.x0 < lb.x1 <= px1 and py0 <= lb.y0 < lb.y1 <= py1


def test_90_and_270_are_mirrored_turns() -> None:
    eng = RenderEngine()
    lbl = make_label("A1", "", "AB", "")
    lbl.style.rotation = 90
    a = eng.render(lbl).mono
    lbl.style.rotation = 270
    b = eng.render(lbl).mono
    assert a.tobytes() != b.tobytes()
    assert _ink_box(a.rotate(180)) is not None


def test_turned_with_border_and_invert() -> None:
    lbl = make_label("A1", "", "X", "")
    lbl.style.rotation = 90
    lbl.style.border = True
    lbl.style.invert = True
    r = RenderEngine().render(lbl)
    px0, py0, px1, py1 = RenderEngine().printable_box
    # inverted band: mostly black inside the printable box
    band = r.mono.crop((px0, py0, px1, py1)).convert("L")
    assert band.histogram()[0] > band.width * band.height * 0.8


def test_rotation_values_are_checked() -> None:
    assert Label.from_dict({"style": {"rotation": 90}}).style.rotation == 90
    assert Label.from_dict({"style": {"rotation": 45}}).style.rotation == 0
    assert Label.from_dict({"style": {"rotation": -90}}).style.rotation == 270
