"""Looking for a newer version (no network: fetch_latest is replaced)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from etiknivo import updates
from etiknivo.updates import Release, UpdateError, is_newer, parse_version, release_from_json
from tests.test_gui import window  # noqa: F401 - fixture


def test_versions() -> None:
    assert parse_version("v1.2") == (1, 2, 0)
    assert parse_version("0.10.1-beta") == (0, 10, 1)
    assert is_newer("0.2.0", "0.1.9") and is_newer("v1.0", "0.9.9")
    assert not is_newer("0.1.0", "0.1.0") and not is_newer("onzin", "0.1.0")
    with pytest.raises(ValueError):
        parse_version("latest")


def test_release_from_github_json() -> None:
    r = release_from_json({"tag_name": "v0.3.0", "html_url": "https://x/r", "body": "Nieuw"})
    assert r == Release("0.3.0", "https://x/r", "Nieuw")
    with pytest.raises(UpdateError):
        release_from_json({"tag_name": "nightly"})


@pytest.mark.parametrize(("result", "expected"), [
    (Release("99.0.0", "https://x"), "box"),
    (Release("0.0.1", "https://x"), "info"),
    (None, "info"),
    (UpdateError("weg"), "warning"),
])
def test_manual_check_reports(qtbot, window, monkeypatch, result, expected) -> None:  # noqa: ANN001, F811
    shown: list[str] = []

    def fake_fetch() -> Release | None:
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(updates, "fetch_latest", fake_fetch)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a: shown.append("info")))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: shown.append("warning")))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append("box"))
    window.check_updates(manual=True)
    qtbot.waitUntil(lambda: bool(shown), timeout=3000)
    assert shown == [expected]
    assert bool(window.settings.last_update_check) == (expected != "warning")


def test_automatic_check_is_silent_without_news(qtbot, window, monkeypatch) -> None:  # noqa: ANN001, F811
    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a: shown.append("info")))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: shown.append("warning")))
    for result in (None, Release("0.0.1", "u"), UpdateError("weg")):
        err = result if isinstance(result, Exception) else None
        window.on_update_checked(None if err else result, err, False)
    assert shown == []
    assert not window.settings.check_updates  # off unless the user turns it on
    window.act_auto_update.trigger()
    assert window.settings.check_updates
