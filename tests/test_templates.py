"""Templates: ready-made arrangements of a label's lines, code and pictogram."""

from __future__ import annotations

import pytest
from PIL import Image, ImageChops

from etiknivo.model import (
    CodeKind,
    CodeSize,
    ElementKind,
    HAlign,
    Label,
    LabelElement,
    LabelTemplate,
    LayoutPreset,
    PictureKind,
    copy_format,
    make_label,
)
from etiknivo.rendering.engine import RenderEngine
from etiknivo.rendering.templates import (
    BAR_TEMPLATES,
    apply_template,
    capitals,
    differs_from_template,
    reset_to_template,
)
from tests.test_gui import window  # noqa: F401 - fixture

TEMPLATES = [t for t in LabelTemplate if t not in (LabelTemplate.NONE, LabelTemplate.CUSTOM)]


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
    apply_template(lbl, template)
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
    px0, py0, _px1, _ = engine.printable_box
    box = (px0, py0, px0 + 26 * 8, py0 + 32)  # the 26 × 4 mm inverted element
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
    assert box.count() == len(LabelTemplate) - 1  # no own templates yet
    assert props._label_form.isRowVisible(box)
    box.setCurrentIndex(box.findData(LabelTemplate.HEADER.value))
    box.activated.emit(box.currentIndex())
    assert window.current.template == LabelTemplate.HEADER
    # everything stays in view; what the template decides is greyed out, with why
    assert props._style_form.isRowVisible(props.valign) and not props.valign.isEnabled()
    assert "sjabloon" in props.valign.toolTip()
    assert props.margin_h.isEnabled() and props.lines[1].size.isEnabled()
    assert not props.template_reset.isEnabled()  # nothing changed yet
    props.lines[1].size.setValue(9.0)
    assert window.current.main.font_size_pt == 9.0 and props.template_reset.isEnabled()
    props.template_reset.click()
    assert window.current.main.font_size_pt == 15.0 and not props.template_reset.isEnabled()
    window.undo()
    window.undo()
    window.undo()
    assert window.current.template == LabelTemplate.NONE
    assert props.valign.isEnabled()


def test_leaving_a_template_undoes_what_it_switched_on() -> None:
    lbl = led()
    lbl.picture.kind = PictureKind.NONE
    lbl.code.text = ""
    apply_template(lbl, LabelTemplate.ICON)
    assert lbl.picture.kind == PictureKind.SYMBOL
    apply_template(lbl, LabelTemplate.ZONES)  # still uses it
    assert lbl.picture.kind == PictureKind.SYMBOL and lbl.code.text == "{Lade}"
    back = Label.from_dict(lbl.to_dict())  # remembered across saving
    apply_template(back, LabelTemplate.NONE)
    assert back.picture.kind == PictureKind.NONE and back.code.text == ""
    assert back.template_added == []
    # a pictogram the label already had stays
    mine = led()
    apply_template(mine, LabelTemplate.ICON)
    apply_template(mine, LabelTemplate.NONE)
    assert mine.picture.kind == PictureKind.SYMBOL and mine.picture.symbol == "led"


def test_a_pictogram_chosen_by_hand_stays(qtbot, window) -> None:  # noqa: ANN001, F811
    props = window.properties
    lbl = window.current
    lbl.picture.kind = PictureKind.NONE
    props.set_label(lbl)
    box = props.template
    for tpl in (LabelTemplate.ICON, LabelTemplate.NONE):
        box.setCurrentIndex(box.findData(tpl.value))
        box.activated.emit(box.currentIndex())
    assert window.current.picture.kind == PictureKind.NONE  # switched on and off again
    box.setCurrentIndex(box.findData(LabelTemplate.ICON.value))
    box.activated.emit(box.currentIndex())
    other = props.pic_symbol.findData("bolt")
    props.pic_symbol.setCurrentIndex(other)  # the user picks a symbol: it is theirs now
    box.setCurrentIndex(box.findData(LabelTemplate.NONE.value))
    box.activated.emit(box.currentIndex())
    assert window.current.picture.kind == PictureKind.SYMBOL
    assert window.current.picture.symbol == "bolt"


def test_chooser_keeps_one_height(qtbot, window) -> None:  # noqa: ANN001, F811
    """The picture of every template shows whole: the chooser never changes height."""
    props = window.properties
    box = props.template
    heights = set()
    for tpl in LabelTemplate:
        box.setCurrentIndex(box.findData(tpl.value))
        box.activated.emit(box.currentIndex())
        qtbot.wait(10)
        heights.add(box.height())
    assert len(heights) == 1 and heights.pop() >= box.iconSize().height() + 8


def test_template_is_a_starting_point(engine: RenderEngine) -> None:
    lbl = led()
    lbl.main.font_size_pt, lbl.main.bold = 11.0, False
    apply_template(lbl, LabelTemplate.LOCATION)
    assert (lbl.main.font_size_pt, lbl.main.bold) == (16.0, True)  # the template's start
    size = {lb.slot: lb.size_pt for lb in engine.render(lbl).lines}[1]
    lbl.main.font_size_pt = 10.0  # the user builds on it: a smaller main line
    assert {lb.slot: lb.size_pt for lb in engine.render(lbl).lines}[1] == 10.0 < size
    lbl.main.align = HAlign.RIGHT
    r = engine.render(lbl)
    main = next(lb for lb in r.lines if lb.slot == 1)
    assert main.x1 == pytest.approx(engine.printable_box[2], abs=1.5)
    apply_template(lbl, LabelTemplate.NONE)  # back: the look from before the template
    assert (lbl.main.font_size_pt, lbl.main.bold) == (11.0, False)
    assert lbl.looks_before_template == []
    back = Label.from_dict({**lbl.to_dict(), "looks_before_template": [{"bold": "ja"}] * 3})
    assert back.looks_before_template[0]["bold"] is True


def test_margins_and_sizes_work_on_a_template(engine: RenderEngine) -> None:
    lbl = led()
    apply_template(lbl, LabelTemplate.ICON)
    before = engine.render(lbl)
    lbl.style.margin_h_mm = 2.0
    inset = engine.render(lbl)
    left = min(lb.x0 for lb in inset.lines)
    assert left > min(lb.x0 for lb in before.lines)
    lbl.style.margin_h_mm = 0.0
    lbl.picture.size = CodeSize.LARGE
    wide = engine.render(lbl)
    main = lambda r: next(lb for lb in r.lines if lb.slot == 1)  # noqa: E731
    assert main(wide).x0 > main(before).x0  # a wider pictogram column
    reset_to_template(lbl)
    assert lbl.picture.size == CodeSize.MEDIUM and not differs_from_template(lbl)


def test_code_template_switches_a_qr_code_on_and_off() -> None:
    lbl = led()
    lbl.code.kind = CodeKind.CODE128
    apply_template(lbl, LabelTemplate.QR)
    assert lbl.code.kind == CodeKind.QR
    apply_template(lbl, LabelTemplate.VALUE)
    assert lbl.code.kind == CodeKind.CODE128  # the barcode it had comes back


def test_code_of_a_template_can_be_switched_off(engine: RenderEngine) -> None:
    engine = RenderEngine(engine.profile.with_label(50.0, 14.0))
    lbl = led()
    apply_template(lbl, LabelTemplate.ZONES)
    main = lambda r: next(lb for lb in r.lines if lb.slot == 1)  # noqa: E731
    with_qr = engine.render(lbl)
    assert any(lb.text == "A17" for lb in with_qr.lines)  # the QR code's caption
    lbl.code.caption = False  # no caption: the QR code grows, the text stays
    bare = engine.render(lbl)
    assert not any(lb.text == "A17" for lb in bare.lines)
    lbl.code.kind = CodeKind.NONE  # no code at all: the text gets the room
    none = engine.render(lbl)
    assert none.warnings == []
    right = (none.mono.width * 3 // 4, none.mono.height // 3, none.mono.width,
             none.mono.height)  # below the bar, that grows with it
    assert ink(none.mono, right) < ink(bare.mono, right) / 4  # the QR code is gone
    back = Label.from_dict(lbl.to_dict())
    assert back.code.caption is False and back.code.kind == CodeKind.NONE
    for tpl in (LabelTemplate.QR,):
        lbl = led()
        apply_template(lbl, tpl)
        qr = engine.render(lbl)
        lbl.code.kind = CodeKind.NONE
        assert main(engine.render(lbl)).x0 < main(qr).x0  # the text moves to the left


@pytest.mark.parametrize("template", [LabelTemplate.ICON, LabelTemplate.VALUE,
                                      LabelTemplate.LOCATION, LabelTemplate.GRID])
def test_tray_of_a_template_can_be_switched_off(engine: RenderEngine,
                                                template: LabelTemplate) -> None:
    lbl = led()
    apply_template(lbl, template)
    shown = engine.render(lbl)
    texts = lambda r: " ".join(lb.text for lb in r.lines)  # noqa: E731
    assert "A17" in texts(shown) or "17" in texts(shown)
    key = lbl.render_key()
    lbl.template_tray = False
    assert lbl.render_key() != key
    hidden = engine.render(lbl)
    assert "17" not in texts(hidden) and hidden.warnings == []
    assert lbl.tray_id == "A17"  # kept, only not on the label
    assert Label.from_dict(lbl.to_dict()).template_tray is False
    assert Label.from_dict({}).template_tray is True


def test_old_labels_keep_their_lines_key() -> None:
    lbl = led()
    d = lbl.to_dict()
    del d["code"]["caption"], d["template_tray"]
    assert Label.from_dict(d).lines_key() == lbl.lines_key()


def test_panel_switches_code_and_tray_off(qtbot, window) -> None:  # noqa: ANN001, F811
    props = window.properties
    box = props.template
    box.setCurrentIndex(box.findData(LabelTemplate.QR.value))
    box.activated.emit(box.currentIndex())
    lbl = window.current
    assert lbl.code.kind == CodeKind.QR
    assert props.code_kind.isEnabled()
    barcode = props.code_kind.model().item(props._code_index(CodeKind.CODE128))
    assert not barcode.isEnabled()
    assert props._code_form.isRowVisible(props.code_caption)
    assert not props.tray_show.isVisibleTo(props)  # the QR template shows no tray ID
    props.code_caption.setChecked(False)
    assert lbl.code.caption is False
    props.code_kind.setCurrentIndex(props._code_index(CodeKind.NONE))
    assert lbl.code.kind == CodeKind.NONE and "code" not in lbl.template_added
    box.setCurrentIndex(box.findData(LabelTemplate.ICON.value))
    box.activated.emit(box.currentIndex())
    assert props.tray_show.isVisibleTo(props) and props.tray_show.isChecked()
    props.tray_show.setChecked(False)
    assert window.current.template_tray is False
    box.setCurrentIndex(box.findData(LabelTemplate.NONE.value))
    box.activated.emit(box.currentIndex())
    assert not props.tray_show.isVisibleTo(props) and barcode.isEnabled()


@pytest.mark.parametrize("template", BAR_TEMPLATES)
def test_bar_templates_show_category_and_pictogram_white_on_black(
        engine: RenderEngine, template: LabelTemplate) -> None:
    lbl = led()
    lbl.picture.kind = PictureKind.NONE
    apply_template(lbl, template)
    assert lbl.picture.kind == PictureKind.SYMBOL  # the template picks one
    items, _ = engine.template_items(lbl)
    texts = {p.role: p.element.text for p in items if p.element.kind == ElementKind.TEXT}
    assert texts["category"] == "{Categorie}"
    kinds = [p.element.kind for p in items]
    assert ElementKind.INVERT in kinds and ElementKind.SYMBOL in kinds
    r = engine.render(lbl)
    px0, py0, px1, _ = engine.printable_box
    bar = (px0, py0, px1, py0 + 27)  # 3.4 mm
    area = (bar[2] - bar[0]) * (bar[3] - bar[1])
    assert 0.6 * area < ink(r.mono, bar) < area
    assert (ElementKind.QR in kinds) == (template == LabelTemplate.BAR_QR)


def test_tray_goes_out_of_the_bar_on_a_narrow_roll() -> None:
    def tray_in_bar(engine: RenderEngine) -> bool:
        lbl = led()
        apply_template(lbl, LabelTemplate.BAR_TRAY)
        items, _ = engine.template_items(lbl)
        bar = next(p.element for p in items if p.element.kind == ElementKind.INVERT)
        tray = next(p.element for p in items if p.role == "tray")
        return tray.y_mm < bar.h_mm
    assert tray_in_bar(RenderEngine())
    assert not tray_in_bar(RenderEngine(RenderEngine().profile.with_label(22.0, 14.0)))
