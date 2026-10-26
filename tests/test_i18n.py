"""Every interface text has an English translation with the same placeholders,
and everything the app shows or writes follows the chosen language."""

from __future__ import annotations

import ast
import importlib.util
import re
import string
from datetime import date, datetime
from pathlib import Path

import pytest

from etiknivo import i18n
from etiknivo.locale.en import EN

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "i18n_strings.py"


def _source_texts(**kw: bool) -> dict[str, list[str]]:
    spec = importlib.util.spec_from_file_location("i18n_strings", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.texts(**kw)


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.fixture
def english():  # noqa: ANN201
    yield i18n.set_language("en")
    i18n.set_language("nl")


def test_every_text_is_translated() -> None:
    missing = [f"{t!r} ({w[0]})" for t, w in _source_texts().items() if t not in EN]
    assert not missing, "geen Engelse vertaling:\n" + "\n".join(missing)


def test_placeholders_match() -> None:
    wrong = [k for k in _source_texts(formatted=True) if _fields(k) != _fields(EN[k])]
    assert not wrong


def test_log_placeholders_match() -> None:
    """%-placeholders (log messages) in the same order in both languages."""
    def pct(text: str) -> list[str]:
        return re.findall(r"%[-0-9.]*[sdrf]", text)

    wrong = [k for k in EN if pct(k) != pct(EN[k])]
    assert not wrong


def test_every_log_message_is_translated() -> None:
    """The log window shows the log, so its messages follow the language too."""
    src = SCRIPT.parents[1] / "src" / "etiknivo"
    levels = {"debug", "info", "warning", "error", "exception", "critical"}
    bare = []
    for path in sorted(src.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in levels and isinstance(node.func.value, ast.Name)
                    and node.func.value.id.endswith("log") and node.args
                    and isinstance(node.args[0], ast.Constant)):
                bare.append(f"{path.relative_to(src)}:{node.lineno}")
    assert not bare, "log zonder tr(): " + ", ".join(bare)


def test_no_unused_translations() -> None:
    unused = set(EN) - set(_source_texts())
    assert not unused


def test_tr_fills_values_in_both_languages(english) -> None:  # noqa: ANN001
    assert english == "en"
    text = "{n} label(s) verwijderen?"
    if text in EN:
        assert i18n.tr(text, n=3) == EN[text].format(n=3)
    i18n.set_language("nl")
    assert i18n.tr("Onbekende tekst {x}", x=1) == "Onbekende tekst 1"


def test_window_in_english(qtbot, english) -> None:  # noqa: ANN001
    from etiknivo.gui import main_window as mw
    from etiknivo.settings import Settings, data_dir
    from etiknivo.storage.library import open_library

    lib, _ = open_library(data_dir() / "library.json")
    win = mw.MainWindow(lib, Settings(use_mock_printer=True), poll_interval=3600)
    qtbot.addWidget(win)
    menus = [a.text().replace("&", "") for a in win.menuBar().actions()]
    assert menus[0] == EN["&Bestand"].replace("&", "") == "File"


def test_dates_follow_the_language(english) -> None:  # noqa: ANN001
    from etiknivo.model import today_text

    day = date(2026, 10, 26)
    assert i18n.format_date(day) == today_text(day) == "2026-10-26"
    assert i18n.format_datetime(datetime(2026, 10, 26, 9, 5)) == "2026-10-26 09:05"
    i18n.set_language("nl")
    assert i18n.format_date(day) == today_text(day) == "26-10-2026"


def test_defaults_follow_the_language(english) -> None:  # noqa: ANN001
    from etiknivo.model import Label, make_label
    from etiknivo.printing.profiles import FICHERO_5836
    from etiknivo.rendering.patterns import test_label

    assert Label().name == make_label("", "", "", "").name == "New label"
    assert FICHERO_5836.density_names() == ("Light", "Normal", "Dark")
    assert test_label().name == "Test label"
    i18n.set_language("nl")
    assert Label().name == "Nieuw label"
    assert FICHERO_5836.density_names() == ("Licht", "Normaal", "Donker")


def test_sample_library_in_english(english) -> None:  # noqa: ANN001
    from etiknivo.storage.library import seed_labels

    en = seed_labels()
    i18n.set_language("nl")
    nl = seed_labels()
    assert [lbl.tray_id for lbl in en] == [lbl.tray_id for lbl in nl]
    assert [lbl.picture.symbol for lbl in en] == [lbl.picture.symbol for lbl in nl]
    assert en[0].category == "Slide potentiometers" and nl[0].category == "Schuifpotmeters"


def test_overview_in_english(english, monkeypatch) -> None:  # noqa: ANN001
    """The overview sheet (PDF/PNG) is written in the chosen language."""
    from etiknivo.model import make_label
    from etiknivo.rendering import overview
    from etiknivo.rendering.engine import RenderEngine

    written: list[str] = []
    real = overview._Sheet.text
    monkeypatch.setattr(overview._Sheet, "text",
                        lambda self, x, y, text, *a, **k: (written.append(text),
                                                           real(self, x, y, text, *a, **k)))
    overview.overview_pages(RenderEngine(), [make_label("A1", "", "x", "")],
                            today=date(2026, 10, 26))
    assert written[:2] == ["Label overview", "1 labels · 2026-10-26"]
    assert "(no category)" in written and written[-1] == "Etiknivo · page 1 of 1"
