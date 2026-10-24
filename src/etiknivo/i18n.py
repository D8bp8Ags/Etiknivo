"""Interface language (Dutch or English).

Texts in the code are written in Dutch and wrapped in :func:`tr`; the English
version lives in :mod:`etiknivo.locale.en`, keyed by the Dutch text.  Values
are filled in with ``str.format`` names, so a translation can move them::

    tr("{n} label(s) verwijderen?", n=3)

The language is chosen once at start-up (``Settings.language``); switching in
the menu takes effect after a restart.  A test checks that every ``tr()`` text
has an English translation.
"""

from __future__ import annotations

from typing import Any

#: Menu entries; the language names stay in their own language.
LANGUAGES = {"system": "Systeem", "nl": "Nederlands", "en": "English"}

_catalog: dict[str, str] = {}
_language = "nl"


def system_language() -> str:
    """'nl' when the operating system prefers Dutch, otherwise 'en'."""
    from PySide6.QtCore import QLocale

    for name in QLocale.system().uiLanguages():
        lang = name.replace("_", "-").split("-")[0].lower()
        if lang in ("nl", "en"):
            return lang
    return "en"


def resolve(choice: str) -> str:
    return choice if choice in ("nl", "en") else system_language()


def set_language(choice: str) -> str:
    """Activate 'nl', 'en' or 'system'.  Returns the language in use."""
    global _catalog, _language
    _language = resolve(choice)
    if _language == "en":
        from etiknivo.locale.en import EN

        _catalog = EN
    else:
        _catalog = {}
    return _language


def language() -> str:
    return _language


def tr(text: str, /, **values: Any) -> str:
    out = _catalog.get(text, text)
    return out.format(**values) if values else out


def N_(text: str) -> str:  # noqa: N802 - gettext convention
    """Marks a text for translation where it is defined (module constants);
    :func:`tr` translates it where it is shown."""
    return text


def install_qt_translations(app: Any) -> None:
    """Qt's own texts (Cancel, Save, file dialogs) in the active language."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for name in ("qtbase",):
        t = QTranslator(app)
        if t.load(QLocale(_language), name, "_", path):
            app.installTranslator(t)
