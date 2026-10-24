"""The interface icons are Etiknivo's own drawings, all renderable."""

from __future__ import annotations

from importlib import resources

from etiknivo.gui import theme


def test_icons_are_own_and_render(qtbot) -> None:  # noqa: ANN001
    files = [f for f in resources.files("etiknivo.gui.icons").iterdir() if f.name.endswith(".svg")]
    assert len(files) >= 30
    for f in files:
        text = f.read_text("utf-8")
        assert text.startswith("<!-- Etiknivo icon") and "currentColor" in text, f.name
        assert not theme.icon(f.name[:-4]).pixmap(18, 18).isNull(), f.name
    names = {f.name for f in resources.files("etiknivo.gui.icons").iterdir()}
    assert not any("lucide" in n.lower() for n in names)
