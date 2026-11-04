"""Same font size within a category: labels share the smallest size per line,
an outlier shrinks on its own, and the choice can be switched off."""

from __future__ import annotations

from etiknivo.model import Label, PictureKind, make_label
from etiknivo.rendering.engine import RenderEngine
from etiknivo.storage.library import Library


def caps_label(category: str, main: str, spec: str = "1/4 W 1%", *, symbol: str = "") -> Label:
    lbl = make_label("A1", category, main, spec)
    if symbol:
        lbl.picture.kind = PictureKind.SYMBOL
        lbl.picture.symbol = symbol
    return lbl


def sizes(engine: RenderEngine, lbl: Label) -> dict[int, float]:
    return {lb.slot: lb.size_pt for lb in engine.render(lbl).lines}


def with_peers(engine: RenderEngine, labels: list[Label]) -> RenderEngine:
    engine.peers = lambda: labels
    return engine


def test_without_peers_every_label_sizes_on_its_own(engine: RenderEngine) -> None:
    a = caps_label("Condensatoren", "100 nF", symbol="capacitor")
    b = caps_label("Condensatoren", "1 nF", symbol="capacitor")
    assert sizes(engine, a)[1] < sizes(engine, b)[1]


def test_category_shares_the_smallest_size_per_line(engine: RenderEngine) -> None:
    a = caps_label("Condensatoren", "100 nF", symbol="capacitor")
    b = caps_label("Condensatoren", "1 nF", symbol="capacitor")
    c = caps_label("Condensatoren", "10 µF")
    own = {lbl.id: sizes(engine, lbl) for lbl in (a, b, c)}
    with_peers(engine, [a, b, c])
    mains = {sizes(engine, lbl)[1] for lbl in (a, b, c)}
    assert mains == {min(o[1] for o in own.values())}
    r = engine.render(b)
    assert r.lines[1].shared == "shared" and not r.has_overflow


def test_other_categories_are_not_pulled_down(engine: RenderEngine) -> None:
    a = caps_label("Condensatoren", "100 nF", symbol="capacitor")
    b = caps_label("Weerstanden", "1 MΩ")
    own_b = sizes(engine, b)
    with_peers(engine, [a, b])
    assert sizes(engine, b) == own_b


def test_switched_off_keeps_the_own_size(engine: RenderEngine) -> None:
    a = caps_label("Condensatoren", "100 nF", symbol="capacitor")
    b = caps_label("Condensatoren", "1 nF", symbol="capacitor")
    own_b = sizes(engine, b)
    b.style.same_size_in_category = False
    with_peers(engine, [a, b])
    assert sizes(engine, b) == own_b
    a_alone = sizes(RenderEngine(), a)
    assert sizes(engine, a) == a_alone  # b no longer counts for a either


def test_outlier_shrinks_alone(engine: RenderEngine) -> None:
    short = [caps_label("Weerstanden", t) for t in ("1 kΩ", "2 kΩ", "4 kΩ")]
    long = caps_label("Weerstanden", "Precisie 1,234 kΩ")
    own_short = sizes(engine, short[0])[1]
    own_long = sizes(engine, long)[1]
    assert own_long < own_short - 1.0
    with_peers(engine, [*short, long])
    assert sizes(engine, short[0])[1] == own_short
    r = engine.render(long)
    assert r.lines[1].size_pt == own_long and r.lines[1].shared == "own"


def test_lines_with_a_different_chosen_size_are_not_compared(engine: RenderEngine) -> None:
    a = caps_label("Weerstanden", "10 kΩ")
    b = caps_label("Weerstanden", "1 MΩ")
    b.main.font_size_pt = 9.0
    own_a = sizes(engine, a)[1]
    with_peers(engine, [a, b])
    assert sizes(engine, a)[1] == own_a


def test_old_libraries_get_the_shared_size(tmp_path) -> None:  # noqa: ANN001
    lbl = caps_label("X", "y")
    data = lbl.to_dict()
    del data["style"]["same_size_in_category"]
    assert Label.from_dict(data).style.same_size_in_category
    lib = Library(tmp_path / "lib.json")
    lib.add(lbl)
    assert Label.from_dict(lib.get(lbl.id).to_dict()).style.same_size_in_category
