"""Platform-neutral bits: shortcut texts and the packaging spec."""

from __future__ import annotations

import ast
from pathlib import Path

from PySide6.QtGui import QKeySequence

from etiknivo.gui.qt_util import with_shortcut

ROOT = Path(__file__).resolve().parents[1]


def test_shortcut_text_uses_the_native_notation(qtbot) -> None:  # noqa: ANN001, ARG001
    native = QKeySequence("Ctrl+S").toString(QKeySequence.SequenceFormat.NativeText)
    assert with_shortcut("Opslaan", "Ctrl+S") == f"Opslaan ({native})"


def test_no_mac_glyphs_in_code_texts() -> None:
    for path in (ROOT / "src" / "etiknivo" / "gui").glob("*.py"):
        if path.name == "qt_util.py":  # explains the notation in a docstring
            continue
        assert "⌘" not in path.read_text(encoding="utf-8"), path


def test_spec_is_valid_python_for_every_platform() -> None:
    src = (ROOT / "packaging" / "etiknivo.spec").read_text(encoding="utf-8")
    ast.parse(src)
    for needle in ("darwin", "win32", "etiknivo.ico", "etiknivo.icns", "bluezdbus", "winrt"):
        assert needle in src
