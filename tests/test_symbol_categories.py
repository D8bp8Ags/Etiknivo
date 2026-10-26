"""Every symbol sits in exactly one category of the symbol picker."""

from __future__ import annotations

import pytest

from etiknivo.gui.widgets import select_symbol, symbol_combo
from etiknivo.rendering.symbols import SYMBOL_CATEGORIES, SYMBOLS, suggest_symbol


def test_every_symbol_is_in_exactly_one_category() -> None:
    keys = [key for _, keys in SYMBOL_CATEGORIES for key in keys]
    assert sorted(keys) == sorted(SYMBOLS)
    assert len(keys) == len(set(keys))


def test_picker_shows_headings_that_cannot_be_chosen(qtbot) -> None:  # noqa: ANN001
    c = symbol_combo()
    qtbot.addWidget(c)
    headings = [i for i in range(c.count()) if c.itemData(i) is None]
    assert len(headings) == len(SYMBOL_CATEGORIES)
    assert all(not c.model().item(i).isEnabled() for i in headings)
    select_symbol(c, "hammer")
    assert c.currentData() == "hammer"
    select_symbol(c, "unknown")
    assert c.currentData() == next(iter(SYMBOLS))


@pytest.mark.parametrize(("category", "key"), [
    ("Bedieningscomponenten", "knob"),
    ("Connectoren", "connector"),
    ("Passieve componenten", "resistor"),
    ("Halfgeleiders", "transistor"),
    ("RF & antennes", "antenna"),
    ("Audio", "speaker"),
    ("Ontwikkelboards", "dev_board"),
    ("Isolatiemateriaal", "heat_shrink"),
    ("Kabels & bedrading", "cable"),
    ("Prototyping", "breadboard"),
    ("Drukknoppen", "push_button"),
    ("Rotary encoders", "knob"),
    ("Development boards", "dev_board"),
    ("Semiconductors", "transistor"),
    ("Insulation", "heat_shrink"),
])
def test_categories_get_a_fitting_symbol(category: str, key: str) -> None:
    assert suggest_symbol(category) == key
