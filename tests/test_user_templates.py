"""The user's own templates: made from a ready-made one or from scratch,
filled from every label's own parts, stored in the library."""

from __future__ import annotations

import json

import pytest
from PIL import ImageChops
from PySide6.QtCore import Qt

from etiknivo.model import (
    PICTOGRAM_FIELD,
    CodeKind,
    ElementKind,
    Label,
    LabelElement,
    LabelTemplate,
    PictureKind,
    UserTemplate,
    find_user_template,
    set_user_templates,
)
from etiknivo.rendering.engine import RenderEngine
from etiknivo.rendering.templates import (
    apply_template,
    differs_from_template,
    reset_to_template,
    template_from_builtin,
    uses_code,
    uses_picture,
)
from etiknivo.storage import io as lio
from etiknivo.storage.library import Library
from tests.test_gui import window  # noqa: F401 - fixture
from tests.test_templates import led

BUILTIN = [t for t in LabelTemplate if t not in (LabelTemplate.NONE, LabelTemplate.CUSTOM)]


@pytest.mark.parametrize("template", BUILTIN)
def test_copy_of_a_ready_made_template_looks_the_same(engine: RenderEngine,
                                                      template: LabelTemplate) -> None:
    if template == LabelTemplate.ZONES:
        engine = RenderEngine(engine.profile.with_label(50.0, 14.0))
    own = template_from_builtin(template, engine.area_mm)
    set_user_templates([own])
    a, b = led(), led()
    apply_template(a, template)
    apply_template(b, LabelTemplate.CUSTOM, own.id)
    ra, rb = engine.render(a), engine.render(b)
    assert rb.warnings == []
    assert ImageChops.difference(ra.mono.convert("L"), rb.mono.convert("L")).getbbox() is None


def test_part_fields_fill_any_text() -> None:
    lbl = led()
    assert lbl.resolve("{Bovenregel}|{HOOFDREGEL}|{cel 2}|{Laderij}{Ladenummer}|{main line}") \
        == ("LED|ROOD|THT|A17|Rood", [])
    lbl.specs["Code"] = "own"  # a specification of that name wins
    assert lbl.resolve("{Code}")[0] == "own"


def own_template() -> UserTemplate:
    return UserTemplate(name="Mijn sjabloon", width_mm=26.0, height_mm=12.0, elements=[
        LabelElement(ElementKind.SYMBOL, 0, 0, 8, 12, symbol=PICTOGRAM_FIELD),
        LabelElement(ElementKind.TEXT, 9, 0, 12, 7, text="{Hoofdregel}", font_size_pt=20),
        LabelElement(ElementKind.TEXT, 21, 0, 5, 4, text="{Lade}", font_size_pt=7, bold=True),
        LabelElement(ElementKind.TEXT, 9, 7, 17, 5, text="{Onderregel}", font_size_pt=6),
    ])


def test_own_template_renders_every_label_with_its_own_parts(engine: RenderEngine) -> None:
    tpl = own_template()
    set_user_templates([tpl])
    lbl = led()
    apply_template(lbl, LabelTemplate.CUSTOM, tpl.id)
    assert lbl.main.font_size_pt == 20  # the template's look as the starting point
    assert uses_picture(lbl) and not uses_code(lbl)
    r = engine.render(lbl)
    assert r.warnings == []
    assert {lb.text for lb in r.lines} >= {"Rood", "A17"}
    other = led(tray="B3", main="Groen")
    apply_template(other, LabelTemplate.CUSTOM, tpl.id)
    assert {"Groen", "B3"} <= {lb.text for lb in engine.render(other).lines}
    # the user builds on it per label, and can go back
    lbl.main.font_size_pt = 12.0
    assert differs_from_template(lbl)
    reset_to_template(lbl)
    assert lbl.main.font_size_pt == 20 and not differs_from_template(lbl)
    # switching parts off works as in the ready-made templates
    lbl.template_tray = False
    lbl.picture.kind = PictureKind.NONE
    r = engine.render(lbl)
    assert "A17" not in {lb.text for lb in r.lines} and r.warnings == []
    # it scales with the roll
    wide = RenderEngine(engine.profile.with_label(50.0, 14.0))
    lbl.picture.kind = PictureKind.SYMBOL
    assert wide.render(lbl).warnings == []


def test_changing_the_template_changes_the_labels(engine: RenderEngine) -> None:
    tpl = own_template()
    set_user_templates([tpl])
    lbl = led()
    apply_template(lbl, LabelTemplate.CUSTOM, tpl.id)
    before, key = engine.render(lbl).mono, lbl.render_key()
    tpl.elements[1].x_mm = 12.0
    set_user_templates([tpl])
    assert lbl.render_key() != key
    assert ImageChops.difference(before, engine.render(lbl).mono).getbbox() is not None
    set_user_templates([])  # gone: a clear warning instead of an empty label
    assert any("bestaat niet meer" in w for w in engine.render(lbl).warnings)


def test_templates_are_stored_in_the_library_and_exports(tmp_path) -> None:  # noqa: ANN001
    tpl = own_template()
    lib = Library(tmp_path / "library.json")
    lbl = led()
    lib.add(lbl)
    lib.set_templates([tpl])
    apply_template(lbl, LabelTemplate.CUSTOM, tpl.id)
    lib.save()
    set_user_templates([])
    again = Library(tmp_path / "library.json")
    again.load()
    assert [t.name for t in again.templates] == ["Mijn sjabloon"]
    assert find_user_template(tpl.id) is not None
    assert again.labels[0].custom_template == tpl.id
    out = tmp_path / "export.json"
    lio.export_json(again.labels, out)
    assert json.loads(out.read_text("utf-8"))["templates"][0]["id"] == tpl.id
    lio.export_json([led()], out)  # without own templates: none in the file
    assert "templates" not in json.loads(out.read_text("utf-8"))
    lio.export_json(again.labels, out)
    fresh = Library(tmp_path / "other.json")
    assert fresh.merge_templates(lio.import_json_templates(out)) == 1
    assert Label.from_dict(again.labels[0].to_dict()).template == LabelTemplate.CUSTOM


def _own_names(dlg) -> list[str]:  # noqa: ANN001
    """The names under "your own templates" in the editor's list."""
    out = []
    for r in range(dlg.list.count()):
        key = dlg.list.item(r).data(Qt.ItemDataRole.UserRole)
        if key and not key.startswith("builtin:"):
            out.append(dlg.list.item(r).text())
    return out


def test_editor_makes_changes_and_deletes(qtbot, window) -> None:  # noqa: ANN001, F811
    from etiknivo.gui.template_editor import TemplateEditor

    lib = window.library
    dlg = TemplateEditor(lib, window.engine, ["DejaVu Sans"], window)
    qtbot.addWidget(dlg)
    dlg.templatesChanged.connect(window._templates_changed)
    # no own ones yet: the first ready-made one is shown, to look at only
    assert _own_names(dlg) == [] and dlg.builtin is not None
    assert not dlg.name.isEnabled() and not dlg.del_btn.isEnabled()
    assert dlg.dup_btn.isEnabled() and not dlg.save_btn.isEnabled()
    # looking through the ready-made ones makes nothing and asks nothing
    dlg.ask_unsaved = lambda _name: pytest.fail("asked about an unchanged template")
    for tpl in (LabelTemplate.ICON, LabelTemplate.HEADER, LabelTemplate.QR):
        dlg._select_in_list(f"builtin:{tpl.value}")
        dlg._open(f"builtin:{tpl.value}")
        assert dlg.builtin == tpl and lib.templates == []
    # Nieuw…: cancelled leaves nothing behind
    dlg.ask_new = lambda _name, _start: None
    dlg.new_template()
    assert lib.templates == [] and _own_names(dlg) == []
    # Nieuw… with a name and a start: kept at once, in the list
    asked = []
    dlg.ask_new = lambda name, start: asked.append((name, start)) or (
        "Bakje", f"builtin:{LabelTemplate.ICON.value}")
    dlg.new_template()
    assert asked == [("Nieuw sjabloon", f"builtin:{LabelTemplate.QR.value}")]
    assert [t.name for t in lib.templates] == ["Bakje"] and _own_names(dlg) == ["Bakje"]
    assert dlg.builtin is None and dlg.name.isEnabled() and not dlg.dirty
    assert any(el.symbol == PICTOGRAM_FIELD for el in dlg.work.elements)
    dlg.confirm = lambda _text: True
    n = len(dlg.work.elements)
    dlg.add_part(4)  # a QR code of the label's code
    assert len(dlg.work.elements) == n + 1
    assert dlg.work.elements[-1].kind == ElementKind.QR
    assert dlg.dirty and dlg.save_btn.isEnabled()
    assert dlg.save()
    # the chooser offers it, with the ready-made ones
    box = window.properties.template
    value = f"custom:{lib.templates[0].id}"
    assert box.findData(value) >= 0
    box.setCurrentIndex(box.findData(value))
    box.activated.emit(box.currentIndex())
    cur = window.current
    assert cur.template == LabelTemplate.CUSTOM and cur.code.kind == CodeKind.QR
    window.save_current()
    # Dupliceren asks a name too; the copy is its own template
    dlg.ask_new = lambda name, start: (name, start)
    dlg.duplicate()
    assert dlg.work.name == "Bakje (kopie)" and not dlg.dirty
    assert sorted(t.name for t in lib.templates) == ["Bakje", "Bakje (kopie)"]
    assert len(dlg.work.elements) == n + 1
    dlg.delete()  # the copy
    dlg._select_in_list(lib.templates[0].id)
    dlg._open(lib.templates[0].id)
    assert dlg.work.name == "Bakje"
    dlg.delete()
    assert lib.templates == [] and dlg.builtin is not None
    assert window.current.template == LabelTemplate.NONE
    assert all(lbl.template != LabelTemplate.CUSTOM for lbl in lib.labels)
    assert box.findData(value) < 0
    # a ready-made one duplicated becomes an own one
    dlg._open(f"builtin:{LabelTemplate.GRID.value}")
    dlg.duplicate()
    assert [t.name for t in lib.templates] == ["Specificaties in vakjes (kopie)"]


def test_new_template_dialog_shows_the_start(qtbot, window) -> None:  # noqa: ANN001, F811
    from etiknivo.gui.template_editor import NewTemplateDialog

    own = template_from_builtin(LabelTemplate.HEADER, window.engine.area_mm, "Mijn kop")
    window.library.set_templates([own])
    dlg = NewTemplateDialog(window.library, "Nieuw sjabloon", own.id)
    qtbot.addWidget(dlg)
    assert dlg.result_start() == own.id and dlg.preview.pixmap() is not None
    assert not dlg.preview.pixmap().isNull()
    dlg.name.setText("  ")
    assert not dlg.ok_btn.isEnabled()
    dlg.name.setText("Ander")
    dlg._select("")
    assert dlg.result_name() == "Ander" and dlg.result_start() == ""
    dlg._select(f"builtin:{LabelTemplate.QR.value}")
    assert dlg.result_start() == f"builtin:{LabelTemplate.QR.value}"


def test_save_label_as_template(window, engine: RenderEngine) -> None:  # noqa: ANN001, F811
    lbl = window.current
    lbl.picture.kind, lbl.picture.symbol = PictureKind.SYMBOL, "led"
    before = window.engine.render(lbl).mono
    window.save_as_template("Van label")
    tpl = next(t for t in window.library.templates if t.name == "Van label")
    texts = {el.text for el in tpl.elements if el.kind == ElementKind.TEXT}
    assert "{Hoofdregel}" in texts or "{Main line}" in texts
    assert any(el.symbol == PICTOGRAM_FIELD for el in tpl.elements)
    # the label in its own new template looks as it did
    copy = lbl.clone()
    apply_template(copy, LabelTemplate.CUSTOM, tpl.id)
    after = window.engine.render(copy)
    assert after.warnings == []

    def ink(img) -> int:  # noqa: ANN001
        return sum(1 for v in img.convert("L").get_flattened_data() if v == 0)

    # the same parts in the same places (text may land a dot apart)
    assert abs(ink(after.mono) - ink(before)) < 0.05 * ink(before)
    b0 = ImageChops.invert(before.convert("L")).getbbox()
    b1 = ImageChops.invert(after.mono.convert("L")).getbbox()
    assert all(abs(p - q) <= 2 for p, q in zip(b0, b1))
    # also from a label with a ready-made template
    apply_template(lbl, LabelTemplate.BAR_CALM)
    window.save_as_template("Balk")
    tpl = next(t for t in window.library.templates if t.name == "Balk")
    assert any(el.text == "{Categorie}" for el in tpl.elements)


def test_bulk_edit_gives_labels_a_template(window, monkeypatch) -> None:  # noqa: ANN001, F811
    from PySide6.QtWidgets import QDialog

    from etiknivo.gui.bulk_edit import TEMPLATE_COLUMN, BulkEditDialog

    tpl = own_template()
    window.library.set_templates([tpl])
    first, second = window.library.labels[:2]

    def accept(dlg: BulkEditDialog) -> int:
        dlg.table.clearSelection()
        dlg.set_cell(0, TEMPLATE_COLUMN, "Zwarte balk met bovenregel")
        dlg.table.clearSelection()
        dlg.set_cell(1, TEMPLATE_COLUMN, "Mijn sjabloon")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(BulkEditDialog, "exec", accept)
    window.edit_labels()
    a, b = window.library.get(first.id), window.library.get(second.id)
    assert a.template == LabelTemplate.HEADER and a.top.bold  # with the template's look
    assert (b.template, b.custom_template) == (LabelTemplate.CUSTOM, tpl.id)
    assert b.main.font_size_pt == 20


def test_editor_undo_and_redo(qtbot, window, monkeypatch) -> None:  # noqa: ANN001, F811
    from PySide6.QtCore import Qt as QtCore_Qt

    import etiknivo.gui.template_editor as te
    from etiknivo.gui.template_editor import TemplateEditor

    clock = [100.0]
    monkeypatch.setattr(te.time, "monotonic", lambda: clock[0])
    dlg = TemplateEditor(window.library, window.engine, ["DejaVu Sans"], window)
    qtbot.addWidget(dlg)
    dlg.new_from(LabelTemplate.ICON)
    assert not dlg.dirty and not dlg.undo_btn.isEnabled()
    n = len(dlg.work.elements)
    clock[0] += 5
    dlg.add_part(4)  # a step of its own
    clock[0] += 0.1
    dlg.add_part(6)  # also its own step, however quick
    assert len(dlg.work.elements) == n + 2 and dlg.dirty
    # dragging: many small moves in a row are one step
    el = dlg.work.elements[0]
    x0 = el.x_mm
    for _ in range(5):
        clock[0] += 0.1
        el.move_to(el.x_mm + 0.5, el.y_mm)
        dlg.view.elementChanged.emit()
    dlg.undo()
    assert dlg.work.elements[0].x_mm == x0 and len(dlg.work.elements) == n + 2
    dlg.undo()
    assert len(dlg.work.elements) == n + 1
    dlg.undo()
    assert len(dlg.work.elements) == n and not dlg.dirty  # back at what is saved
    assert not dlg.undo_btn.isEnabled() and dlg.redo_btn.isEnabled()
    dlg.redo()
    dlg.redo()
    assert len(dlg.work.elements) == n + 2 and dlg.dirty
    # Ctrl+Z in a text field goes to the template, not to the field
    clock[0] += 5
    dlg.name.setFocus()
    qtbot.keyClicks(dlg.name, "x")
    assert dlg.work.name.endswith("x")
    dlg.activateWindow()
    qtbot.keyClick(dlg.name, QtCore_Qt.Key.Key_Z, QtCore_Qt.KeyboardModifier.ControlModifier)
    assert not dlg.name.text().endswith("x") and len(dlg.work.elements) == n + 2
    dlg.ask_unsaved = lambda _name: "discard"
    dlg.close()


def test_editor_fields_stay_whole_in_a_small_window(qtbot, window) -> None:  # noqa: ANN001, F811
    from etiknivo.gui.template_editor import TemplateEditor

    dlg = TemplateEditor(window.library, window.engine, ["DejaVu Sans"], window)
    qtbot.addWidget(dlg)
    dlg.new_from(LabelTemplate.HEADER)
    dlg.elements.select(dlg.work.elements[0].id)
    dlg.show()
    dlg.resize(400, 500)  # smaller than it can go
    qtbot.wait(20)
    scroll = dlg.elements.parentWidget().parentWidget()
    assert dlg.elements.width() >= dlg.elements.minimumSizeHint().width()
    assert scroll.viewport().width() >= dlg.elements.minimumSizeHint().width()
    assert dlg.view.width() >= dlg.view.minimumSizeHint().width()
    for btn in (dlg.new_btn, dlg.dup_btn, dlg.del_btn):  # their text stays whole
        assert btn.width() >= btn.sizeHint().width(), btn.text()


def test_element_arrows_move_as_they_point(qtbot, window) -> None:  # noqa: ANN001, F811
    from etiknivo.gui.template_editor import TemplateEditor

    dlg = TemplateEditor(window.library, window.engine, ["DejaVu Sans"], window)
    qtbot.addWidget(dlg)
    dlg.new_from(LabelTemplate.HEADER)
    els = dlg.work.elements
    second = els[1]
    dlg.elements.select(second.id)
    dlg.elements.up_btn.click()
    assert dlg.work.elements[0].id == second.id and dlg.elements.list.currentRow() == 0
    dlg.elements.down_btn.click()
    dlg.elements.down_btn.click()
    assert dlg.work.elements[2].id == second.id and dlg.elements.list.currentRow() == 2
    dlg.undo()
    assert dlg.work.elements[1].id == second.id


def test_dragging_lines_up_with_other_elements(qtbot, window) -> None:  # noqa: ANN001, F811
    from PySide6.QtCore import QPoint

    from etiknivo.gui.preview import snap
    from etiknivo.gui.template_editor import TemplateEditor

    assert snap([10.0, 12.0], [12.3, 30.0], 0.5) == (pytest.approx(0.3), 12.3)
    assert snap([10.0], [11.0], 0.5) == (0.0, None)
    dlg = TemplateEditor(window.library, window.engine, ["DejaVu Sans"], window)
    qtbot.addWidget(dlg)
    dlg.new_empty()
    dlg.add_part(0)  # top line
    dlg.add_part(3)  # tray ID
    top, tray = dlg.work.elements
    top.move_to(2.0, 1.0)
    tray.move_to(15.0, 6.0)
    dlg.show()
    view = dlg.view
    view.update()
    qtbot.wait(10)
    dpm = window.engine.profile.dots_per_mm
    s = view._scale()
    start = view.element_rect(tray).center().toPoint()
    # drag the tray ID so its left edge comes 2 screen px right of the top line's
    target_dx = (2.0 - 15.0) * dpm * s + 2
    qtbot.mousePress(view, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(view, start + QPoint(round(target_dx), 0))
    assert tray.x_mm == pytest.approx(2.0)  # snapped onto the top line's left edge
    assert ("v", pytest.approx(2.0)) in view.guides
    qtbot.mouseRelease(view, Qt.MouseButton.LeftButton, pos=start + QPoint(round(target_dx), 0))
    assert view.guides == []
    dlg.ask_unsaved = lambda _name: "discard"


def test_unchanged_copies_are_cleaned_up(window) -> None:  # noqa: ANN001, F811
    lib = window.library
    a = template_from_builtin(LabelTemplate.HEADER, window.engine.area_mm, "Kop")
    b = template_from_builtin(LabelTemplate.HEADER, window.engine.area_mm, "Kop")
    c = template_from_builtin(LabelTemplate.HEADER, window.engine.area_mm, "Kop")
    c.elements[0].x_mm += 1  # changed: stays
    other = template_from_builtin(LabelTemplate.HEADER, window.engine.area_mm, "Andere")
    lib.set_templates([a, b, c, other])
    lbl = lib.labels[0]
    lbl.template, lbl.custom_template = LabelTemplate.CUSTOM, b.id  # in use: stays
    assert lib.drop_duplicate_templates() == 1
    assert {t.id for t in lib.templates} == {b.id, c.id, other.id}
    assert lib.drop_duplicate_templates() == 0
