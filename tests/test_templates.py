"""Templates: ready-made arrangements of a label's lines, code and pictogram."""

from __future__ import annotations

import pytest
from PIL import Image, ImageChops

from etiknivo.model import (
    ElementKind,
    Label,
    LabelElement,
    LabelTemplate,
    LayoutPreset,
    PictureKind,
    copy_format,
    make_label,
)
from etiknivo.rendering.engine import RenderEngine
from etiknivo.rendering.templates import apply_template, capitals
from tests.test_gui import window  # noqa: F401 - fixture

TEMPLATES = [t for t in LabelTemplate if t != LabelTemplate.NONE]


def led(tray: str = "A17", main: str = "Rood", category: str = "Halfgeleiders") -> Label:
    lbl = make_label(tray, category, main, "Ø 3 mm | THT | 20 mA")
    lbl.top.text, lbl.top.enabled = "LED", True
    lbl.picture.kind, lbl.picture.symbol = PictureKind.SYMBOL, "led"
    return lbl


def ink(img: Image.Image, box: tuple[int, int, int, int] | None = None) -> int:
    part = img.convert("L").crop(box) if box else img.convert("L")
    return sum(1 for v in part.get_flattened_data() if v == 0)


@pytest.mark.parametrize("template", TEMPLATES)
def test_every_template_renders_cleanly(engine: RenderEngine, template: LabelTemplate) -> None:
    if template == LabelTemplate.ZONES:  # made for long labels
        engine = RenderEngine(engine.profile.with_label(50.0, 14.0))
    lbl = led()
    plain = engine.render(lbl).mono
    lbl.template = template
    r = engine.render(lbl)
    assert r.warnings == []
    assert ink(r.mono) > 200
    assert ImageChops.difference(plain, r.mono).getbbox() is not None
    # every text stays inside the printable area
    px0, py0, px1, py1 = engine.printable_box
    for lb in r.lines:
        assert px0 - 0.5 <= lb.x0 and lb.x1 <= px1 + 0.5
        assert py0 - 0.5 <= lb.y0 and lb.y1 <= py1 + 0.5


@pytest.mark.parametrize("size", [(22.0, 14.0), (40.0, 12.0), (50.0, 14.0)])
def test_templates_scale_with_the_roll(size: tuple[float, float]) -> None:
    engine = RenderEngine(RenderEngine().profile.with_label(*size))
    for template in TEMPLATES:
        if template == LabelTemplate.ZONES and size[0] < 35:  # made for long labels
            continue
        lbl = led()
        lbl.bottom.text = "Ø 3 mm | THT"
        lbl.template = template
        r = engine.render(lbl)
        assert not r.has_overflow, template
        assert ink(r.mono) > 100


def test_header_bar_is_white_on_black(engine: RenderEngine) -> None:
    lbl = led()
    lbl.template = LabelTemplate.HEADER
    r = engine.render(lbl)
    px0, py0, px1, _ = engine.printable_box
    bar = (px0, py0, px1, py0 + 24)  # 3 mm
    area = (bar[2] - bar[0]) * (bar[3] - bar[1])
    assert ink(r.mono, bar) > 0.75 * area  # mostly black, with white letters in it
    assert ink(r.mono, bar) < area
    below = (px0, py0 + 26, px1, py0 + 40)
    assert ink(r.mono, below) < 0.5 * (below[2] - below[0]) * (below[3] - below[1])


def test_invert_element_turns_over_what_is_under_it(engine: RenderEngine) -> None:
    text = LabelElement(ElementKind.TEXT, 0, 0, 26, 4, text="ABC", font_size_pt=10)
    lbl = make_label("B1", "X", "x")
    lbl.layout = LayoutPreset.FREE
    lbl.elements = [text]
    normal = engine.render(lbl).mono
    lbl.elements = [LabelElement(ElementKind.INVERT, 0, 0, 26, 4), text]  # order does not matter
    turned = engine.render(lbl).mono
    px0, py0, px1, _ = engine.printable_box
    box = (px0, py0, px1, py0 + 32)
    area = (box[2] - box[0]) * (box[3] - box[1])
    assert ink(turned, box) == pytest.approx(area - ink(normal, box), rel=0.01)
    assert Label.from_dict(lbl.to_dict()).elements[0].kind == ElementKind.INVERT


def test_template_is_stored_and_copied() -> None:
    lbl = led()
    key = lbl.render_key()
    lines_key = lbl.lines_key()
    lbl.template = LabelTemplate.GRID
    assert lbl.render_key() != key and lbl.lines_key() != lines_key
    back = Label.from_dict(lbl.to_dict())
    assert back.template == LabelTemplate.GRID and back.uses_template
    assert Label.from_dict({**lbl.to_dict(), "template": "nonsense"}).template == \
        LabelTemplate.NONE
    assert Label.from_dict({"name": "old"}).template == LabelTemplate.NONE
    other = led("A18", "Groen")
    copy_format(lbl, other, {"layout"})
    assert other.template == LabelTemplate.GRID and other.main.text == "Groen"


def test_free_layout_wins_over_the_template(engine: RenderEngine) -> None:
    lbl = led()
    lbl.template = LabelTemplate.VALUE
    lbl.elements = engine.to_elements(lbl)
    lbl.apply_layout(LayoutPreset.FREE)
    assert lbl.is_free and not lbl.uses_template


@pytest.mark.parametrize("template", TEMPLATES)
def test_switching_to_free_keeps_the_look(engine: RenderEngine,
                                          template: LabelTemplate) -> None:
    if template == LabelTemplate.ZONES:
        engine = RenderEngine(engine.profile.with_label(50.0, 14.0))
    lbl = led()
    lbl.template = template
    before = engine.render(lbl).mono
    lbl.elements = engine.to_elements(lbl)
    lbl.apply_layout(LayoutPreset.FREE)
    after = engine.render(lbl)
    assert after.warnings == []
    diff = ImageChops.difference(before.convert("L"), after.mono.convert("L"))
    # the same picture, give or take a dot of rounding at a letter's edge
    assert ink(ImageChops.invert(diff)) < 0.02 * ink(before)


def test_category_shares_the_size_per_part(engine: RenderEngine) -> None:
    short, long_ = led("A17", "Rood"), led("A18", "Ultraviolet")
    for lbl in (short, long_):
        lbl.template = LabelTemplate.LOCATION
    alone = engine.render(short)
    engine.peers = lambda: [short, long_]
    together = engine.render(short)
    main = {lb.slot: lb.size_pt for lb in together.lines}[1]
    assert main < {lb.slot: lb.size_pt for lb in alone.lines}[1]
    assert main == pytest.approx({lb.slot: lb.size_pt for lb in engine.render(long_).lines}[1])
    # another template or category does not count
    long_.template = LabelTemplate.VALUE
    assert {lb.slot: lb.size_pt for lb in engine.render(short).lines}[1] == \
        pytest.approx({lb.slot: lb.size_pt for lb in alone.lines}[1])


def test_lines_of_one_size_share_a_baseline(engine: RenderEngine) -> None:
    """'ROOD' (no descender) and 'Jup' (descenders) in the same box stand
    on the same baseline."""
    tops = []
    for main in ("ROOD", "Jup"):
        lbl = led(main=main)
        lbl.template = LabelTemplate.HEADER
        r = engine.render(lbl)
        lb = next(b for b in r.lines if b.slot == 1)
        tops.append((lb.y0, lb.size_pt))
    assert tops[0][1] == tops[1][1]
    assert abs(tops[0][0] - tops[1][0]) <= 1  # cap tops level, the y hangs below


def test_icon_template_starts_with_a_fitting_symbol() -> None:
    lbl = make_label("A9", "Passieve componenten", "10 kΩ")
    lbl.name = "Weerstanden"
    apply_template(lbl, LabelTemplate.ICON)
    assert lbl.picture.kind == PictureKind.SYMBOL and lbl.picture.symbol == "resistor"
    lbl.code.text = ""
    apply_template(lbl, LabelTemplate.QR)
    assert lbl.code.text == "{Lade}"


def test_missing_pictogram_is_reported(engine: RenderEngine) -> None:
    lbl = led()
    lbl.picture.kind = PictureKind.NONE
    lbl.template = LabelTemplate.ICON
    assert "Kies een pictogram voor dit sjabloon" in engine.render(lbl).warnings


def test_grid_puts_the_bottom_line_in_cells(engine: RenderEngine) -> None:
    lbl = led()
    lbl.template = LabelTemplate.GRID
    cells = [lb.text for lb in engine.render(lbl).lines if lb.slot == 2]
    assert cells == ["Ø 3 mm", "THT", "20 mA"]


def test_capitals_leave_fields_alone() -> None:
    assert capitals("led {Lade} rood") == "LED {Lade} ROOD"


def test_chooser_applies_a_template(qtbot, window) -> None:  # noqa: ANN001, F811
    props = window.properties
    box = props.template
    assert box.count() == len(LabelTemplate)
    assert props._label_form.isRowVisible(box)
    box.setCurrentIndex(box.findData(LabelTemplate.HEADER.value))
    box.activated.emit(box.currentIndex())
    assert window.current.template == LabelTemplate.HEADER
    assert not props._style_form.isRowVisible(props.valign)  # the template places the lines
    window.undo()
    assert window.current.template == LabelTemplate.NONE
    assert props._style_form.isRowVisible(props.valign)
