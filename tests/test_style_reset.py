"""Restoring the default style of a label from the Style section."""

from __future__ import annotations

from etiknivo.model import LabelStyle
from tests.test_gui import window  # noqa: F401 - fixture


def test_restore_default_style_is_one_undo_step(qtbot, window) -> None:  # noqa: ANN001, F811
    props = window.properties
    window.current.style = LabelStyle()
    props.set_label(window.current)
    assert not props.style_reset.isEnabled()  # nothing to restore
    main_before = window.current.main.text
    props.spacing.setValue(-1.9)
    props.margin_v.setValue(0.0)
    props.invert.setChecked(True)
    assert props.style_reset.isEnabled()
    props.style_reset.click()
    assert window.current.style == LabelStyle()
    assert props.spacing.value() == LabelStyle().line_spacing_mm
    assert not props.invert.isChecked() and not props.style_reset.isEnabled()
    assert window.current.main.text == main_before  # the text is left alone
    window.undo()  # one step back: the edited style, not the original one
    s = window.current.style
    assert s.line_spacing_mm == -1.9 and s.margin_v_mm == 0.0 and s.invert
    assert props.spacing.value() == -1.9 and props.style_reset.isEnabled()
    window.redo()
    assert window.current.style == LabelStyle()
