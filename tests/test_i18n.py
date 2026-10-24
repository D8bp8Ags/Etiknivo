"""Every interface text has an English translation with the same placeholders."""

from __future__ import annotations

import importlib.util
import string
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
