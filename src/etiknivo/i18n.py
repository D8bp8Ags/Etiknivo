"""Interface language (Dutch or English).

Texts in the code are written in Dutch and wrapped in :func:`tr`; the English
version lives in :mod:`etiknivo.locale.en`, keyed by the Dutch text.  Values
are filled in with ``str.format`` names, so a translation can move them::

    tr("{n} label(s) verwijderen?", n=3)

The language is chosen once at start-up (``Settings.language``); switching in
the menu takes effect after a restart.

Rules, so everything a user sees follows the chosen language, also in files
the app writes (overview PDF/PNG, PDF export, log, default file names):

* every user-visible text goes through :func:`tr` at the moment it is shown
  or written, never at import time; module constants are marked with
  :func:`N_` and translated where they are used;
* log messages too: ``log.info(tr("Verbonden met %s"), name)``;
* dates and times through :func:`format_date` / :func:`format_datetime`, so
  the notation is the same everywhere;
* data formats are not translated: JSON keys, CSV column names, layout
  names and backup member names stay the same in both languages, so a file
  made in one language can be read in the other.  The texts users typed
  themselves (label texts, categories) are never translated.

Tests check that every ``tr()`` text has an English translation with the same
placeholders and that every log call is translated.
"""

from __future__ import annotations

from datetime import date, datetime
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


#: Date notation per language: 26-10-2026 in Dutch, ISO 2026-10-26 in English.
DATE_FORMATS = {"nl": "%d-%m-%Y", "en": "%Y-%m-%d"}


def format_date(day: date) -> str:
    return day.strftime(DATE_FORMATS[_language])


def format_datetime(moment: datetime) -> str:
    return f"{format_date(moment)} {moment:%H:%M}"


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
