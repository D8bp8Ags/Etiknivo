"""Privacy: no personal details in the repository, the log or what the app shows."""

from __future__ import annotations

import importlib.util
import logging
import sys
import zlib
from pathlib import Path

import pytest

from etiknivo import privacy
from etiknivo.logging_setup import MemoryLog
from etiknivo.privacy import RedactingFormatter, redact, short_address, short_path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "privacy_check.py"


@pytest.fixture(scope="module")
def check():
    spec = importlib.util.spec_from_file_location("privacy_check", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look their module up here
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_repository_contains_no_personal_details(check):
    found = check.check_files()
    assert not found, "Persoonlijke gegevens in de repository:\n" + "\n".join(map(str, found))


@pytest.mark.parametrize("line", [
    "data staat in /Users/jan/Library/Etiknivo",  # privacy: ok
    "log: /home/marieke/.local/state",  # privacy: ok
    r"C:\Users\Piet\AppData\Local",  # privacy: ok
    r'"C:\\Users\\Piet\\AppData"',  # privacy: ok
    "contact: jan.jansen@gmail.com",  # privacy: ok
    "printer AA:BB:CC:12:34:56",  # privacy: ok
    "token ghp_" + "a1B2" * 9,
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
])
def test_check_finds_personal_details(check, line):
    assert check.check_text("x", line)


@pytest.mark.parametrize("line", [
    "~/Library/Application Support/Etiknivo",
    "/Users/naam/Library of /home/<gebruiker>/.local",
    r"C:\Users\Public en %LOCALAPPDATA%\Etiknivo",
    "D8bp8Ags <83901401+D8bp8Ags@users.noreply.github.com>",
    "iemand@example.com",
    'MOCK_ADDRESS = "00:00:00:00:00:00"',
    "GATT 49535343-fe7d-4ae5-8fa9-9fafd205e455",
    "13:45:01  INFO  verbonden",
    "/Users/jan  # privacy: ok",
])
def test_check_leaves_ordinary_text_alone(check, line):
    assert check.check_text("x", line) == []


def _png(*chunks: tuple[bytes, bytes]) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return len(body).to_bytes(4, "big") + kind + body + zlib.crc32(kind + body).to_bytes(4, "big")
    ihdr = (1).to_bytes(4, "big") * 2 + bytes([8, 0, 0, 0, 0])
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + b"".join(chunk(k, b) for k, b in chunks) \
        + chunk(b"IEND", b"")


def test_check_finds_image_metadata(check):
    assert check.check_image("a.png", _png((b"IDAT", b"x"))) == []
    found = check.check_image("a.png", _png((b"tEXt", b"Author\0Jan"), (b"IDAT", b"x")))
    assert [f.text for f in found] == ["tEXt (Author)"]
    assert check.check_image("a.png", _png((b"eXIf", b"MM\0*")))
    assert check.check_image("a.jpg", b"\xff\xd8\xff\xe1\0\x10Exif\0\0MM")


def test_screenshots_have_no_metadata(check):
    images = [p for p in check.tracked_files() if Path(p).suffix.lower() in check.IMAGE_SUFFIXES]
    assert images, "geen afbeeldingen gevonden; klopt tracked_files() nog?"
    assert not [f for p in images for f in check.check_image(p, (check.ROOT / p).read_bytes())]


# -- what the app itself shows and logs -------------------------------------


def test_redact_hides_the_home_folder():
    home = str(Path.home())
    assert redact(f"kan {home}/Etiknivo/library.json niet lezen") == "kan ~/Etiknivo/library.json niet lezen"
    assert redact("/opt/etiknivo/app.log") == "/opt/etiknivo/app.log"


def test_redact_shortens_mac_addresses():
    assert redact("Verbonden met AA:BB:CC:12:34:56 (D11s)") == "Verbonden met …:34:56 (D11s)"  # privacy: ok
    assert redact("simulatie 00:00:00:00:00:00") == "simulatie 00:00:00:00:00:00"
    assert redact("tijd 13:45:01") == "tijd 13:45:01"


def test_short_address():
    assert short_address("AA:BB:CC:12:34:56") == "…:34:56"  # privacy: ok
    assert short_address("1A2B3C4D-0000-1111-2222-ABCDEF12A1F2") == "…A1F2"
    assert short_address("mock") == "mock"
    assert short_address(None) == ""


def test_short_path():
    assert short_path(Path.home() / "Library" / "Logs") == "~/Library/Logs"
    assert short_path("/opt/x") == str(Path("/opt/x"))


def test_log_window_and_log_files_hide_the_home_folder():
    home = str(Path.home())
    mem = MemoryLog()
    log = logging.getLogger("etiknivo.test_privacy")
    log.addHandler(mem)
    try:
        try:
            raise OSError(f"[Errno 13] Permission denied: '{home}/geheim.json'")
        except OSError:
            log.exception("Opslaan mislukt: %s", f"{home}/geheim.json")
    finally:
        log.removeHandler(mem)
    (entry,) = mem.snapshot()
    assert home not in entry.message and "~/geheim.json" in entry.message

    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "pad %s", (f"{home}/a",), None)
    assert RedactingFormatter("%(message)s").format(record) == "pad ~/a"


def test_a_root_home_does_not_swallow_every_path(monkeypatch):
    privacy._home_forms.cache_clear()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/")))
    try:
        assert redact("/opt/x") == "/opt/x"
    finally:
        monkeypatch.undo()
        privacy._home_forms.cache_clear()
