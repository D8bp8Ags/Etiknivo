"""Regression tests for the code audit of 2026-11 (findings F-01 to F-20).

Each test names the finding it covers.  Physical printing and real Bluetooth
are not tested here; see ``test_printing.py`` for the simulated printer."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import threading
from pathlib import Path

import pytest
from PIL import Image

from etiknivo import logging_setup
from etiknivo.model import Label, LayoutPreset, PictureKind, make_label
from etiknivo.printing.manager import PrinterManager
from etiknivo.printing.mock import MockPrinterBackend
from etiknivo.rendering import fonts, pictures
from etiknivo.rendering.engine import RenderEngine
from etiknivo.rendering.export import png_paths, safe_filename
from etiknivo.settings import Settings, load_settings
from etiknivo.storage import io as lio
from etiknivo.storage.history import History, Snapshot
from etiknivo.storage.library import SCHEMA_VERSION, Library, LibraryError

from .test_printing import make_backend

# -- F-01, F-10, F-11: loading a library -----------------------------------------------------


def _write(path: Path, doc: object) -> Path:
    path.write_text(json.dumps(doc), "utf-8")
    return path


@pytest.mark.parametrize("bad", [
    {"labels": [{"main": None, "style": None, "lines": None}]},
    {"labels": [{"style": [], "code": "x", "picture": 5, "elements": {}, "specs": []}]},
    {"labels": [{"lines": [None, 3, {"text": None, "font_size_pt": "groot"}]}]},
    {"labels": [{"style": {"margin_h_mm": "breed", "rotation": "scheef", "valign": 7}}]},
    {"labels": [{"elements": [None, {"kind": "onzin", "x_mm": "a", "w_mm": -5}]}]},
    {"labels": [], "category_symbols": [1, 2]},
    {"labels": [], "category_symbols": {"Audio": None}},
])
def test_wrong_types_load_with_defaults(tmp_path: Path, bad: dict) -> None:
    """F-01/F-10: valid JSON with wrong types no longer raises AttributeError."""
    lib = Library(_write(tmp_path / "l.json", bad))
    lib.load()
    for lbl in lib.labels:
        assert len(lbl.lines) == 3
        RenderEngine().render(lbl)  # and it renders


def test_out_of_range_values_are_clamped() -> None:
    """F-10: sizes and margins outside what the editor allows are clamped."""
    lbl = Label.from_dict({"lines": [{"text": "a", "font_size_pt": 1e9},
                                     {"text": "b", "font_size_pt": float("nan")}],
                           "style": {"margin_h_mm": -40, "line_spacing_mm": 1e6}})
    assert 0 < lbl.lines[0].font_size_pt <= 60
    assert lbl.lines[1].font_size_pt == Label.from_dict({}).lines[1].font_size_pt
    assert lbl.style.margin_h_mm >= 0 and lbl.style.line_spacing_mm <= 5


def test_not_a_library_still_raises_library_error(tmp_path: Path) -> None:
    for doc in (None, [1, 2], {"labels": None}):
        with pytest.raises(LibraryError):
            Library(_write(tmp_path / "l.json", doc)).load()


def test_newer_schema_keeps_a_copy_before_saving(tmp_path: Path) -> None:
    """F-11: a library from a newer version is recognised and kept."""
    doc = {"app": "Etiknivo", "schema": SCHEMA_VERSION + 1, "toekomst": True,
           "labels": [make_label("A", "", "x").to_dict()]}
    path = _write(tmp_path / "library.json", doc)
    lib = Library(path)
    lib.load()
    assert lib.newer_schema == SCHEMA_VERSION + 1
    copy = lib.newer_copy_path()
    assert copy.name == f"library.schema-{SCHEMA_VERSION + 1}.json"
    lib.save()
    assert json.loads(copy.read_text("utf-8"))["toekomst"] is True
    assert json.loads(path.read_text("utf-8"))["schema"] == SCHEMA_VERSION


def test_current_schema_makes_no_copy(tmp_path: Path) -> None:
    lib = Library(tmp_path / "library.json")
    lib.add(make_label("A", "", "x"))
    lib.save()
    lib2 = Library(lib.path)
    lib2.load()
    lib2.save()
    assert not lib2.newer_schema
    assert not list(tmp_path.glob("*.schema-*"))


def test_label_format_is_not_part_of_the_render_key() -> None:
    """F-12: the unused ``format`` field no longer changes cache keys."""
    a = make_label("A", "", "x")
    b = a.clone(new_id=False)
    b.format.width_mm = 99
    assert a.render_key() == b.render_key()


# -- F-02: settings -------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    {"density": "hoog", "default_copies": None, "zoom": [], "label_size_mm": "groot"},
    {"calibration": [], "recent_files": 3},
    {"calibration": {"offset_feed_px": "x", "threshold": 9999, "supersample": 0}},
    {"label_size_mm": [30, -1], "use_mock_printer": "ja"},
])
def test_settings_with_wrong_types_fall_back(tmp_path: Path, bad: dict) -> None:
    p = _write(tmp_path / "s.json", bad)
    s = load_settings(p)
    assert isinstance(s, Settings)
    assert 0 <= s.density <= 2 and 1 <= s.default_copies <= 99
    assert 1 <= s.calibration.threshold <= 255
    assert 1 <= s.calibration.supersample <= 8
    assert s.label_size_mm in ([], [30.0, 14.0]) or all(v > 0 for v in s.label_size_mm)


def test_settings_that_are_not_an_object(tmp_path: Path) -> None:
    for doc in ([], None, 5):
        assert load_settings(_write(tmp_path / "s.json", doc)) == Settings()


# -- F-03: a late disconnect report of an old client ---------------------------------------


async def test_late_disconnect_of_old_client_keeps_new_link() -> None:
    be, h = make_backend()
    lost: list[bool] = []
    be.on_disconnect = lambda: lost.append(True)
    await be.connect("AA")
    old = h["ble"]
    await be.connect("AA")  # reconnect: the old client is closed
    new = h["ble"]
    assert new is not old and be.connected
    old.on_disconnect(old)  # the stack reports the old disconnect late
    assert be.connected and not lost
    new.drop()  # the current client still counts
    assert lost and not be.connected


async def test_disconnect_waits_for_the_current_label(engine: RenderEngine) -> None:
    """F-17: disconnect takes the job lock, so it never cuts a label in half."""
    be, h = make_backend()
    await be.connect("AA")
    order: list[str] = []
    async with be._job_lock:
        task = asyncio.ensure_future(be.disconnect())
        await asyncio.sleep(0.01)
        assert be.connected
        order.append("job done")
    await task
    assert not be.connected and order == ["job done"]
    assert h["ble"].is_connected is False


# -- F-17: status poll survives an unexpected error ----------------------------------------


def test_status_poll_survives_an_unexpected_error(caplog) -> None:  # noqa: ANN001
    backend = MockPrinterBackend()
    calls = {"n": 0, "armed": False}
    orig = backend.get_status

    async def flaky():  # noqa: ANN202
        if calls["armed"]:  # only the polls, not the connect
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("vreemd")
        return await orig()

    backend.get_status = flaky
    m = PrinterManager(backend, on_state=lambda s: None, on_queue=lambda s: None,
                       poll_interval=0.02)
    try:
        m.connect(None).result(5)
        calls["armed"] = True
        deadline = threading.Event()
        for _ in range(200):
            if calls["n"] >= 3:
                break
            deadline.wait(0.02)
        assert calls["n"] >= 3  # polling went on after the error
    finally:
        m.shutdown()


# -- F-06: uncaught exceptions are logged ---------------------------------------------------


def test_uncaught_exceptions_are_logged(caplog, monkeypatch) -> None:  # noqa: ANN001
    import sys

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    seen: list[str] = []
    monkeypatch.setattr(logging_setup, "error_listener", seen.append)
    logging_setup.install_exception_hooks()
    with caplog.at_level(logging.CRITICAL, logger="etiknivo"):
        try:
            raise ValueError("in een slot")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        t = threading.Thread(target=lambda: 1 / 0, name="werker")
        t.start()
        t.join()
    text = caplog.text
    assert "in een slot" in text and "ZeroDivisionError" in text
    assert any("ValueError" in s for s in seen) and any("ZeroDivisionError" in s for s in seen)


# -- F-07: undo ----------------------------------------------------------------------------


def test_undo_restores_category_symbols() -> None:
    a = make_label("A1", "Audio", "x")
    h = History(clock=lambda: 0.0)
    h.reset(Snapshot.take([a], [a.id], None, {"Audio": "speaker"}))
    h.record(Snapshot.take([a], [a.id], None, {"Audio": ""}))
    assert h.undo().category_symbols() == {"Audio": "speaker"}
    assert h.redo().category_symbols() == {"Audio": ""}


def test_snapshots_share_unchanged_labels() -> None:
    labels = [make_label(f"A{i}", "Cat", f"T{i}") for i in range(50)]
    s1 = Snapshot.take(labels, [])
    labels[0].main.text = "anders"
    s2 = Snapshot.take(labels, [])
    shared = sum(a is b for a, b in zip(s1.label_texts, s2.label_texts))
    assert shared == 49  # only the changed label is stored again
    assert [lbl.main.text for lbl in s1.labels()][0] == "T0"


# -- F-08: CSV -----------------------------------------------------------------------------


def test_csv_keeps_specs_with_separators_and_lines(tmp_path: Path) -> None:
    lbl = make_label("A1", "IC", "74HC14")
    lbl.specs = {"Pinnen": "1;2;3", "a=b": "x\\y", "Leeg": ""}
    lbl.lines[0].enabled = False
    lbl.layout = LayoutPreset.CUSTOM
    p = tmp_path / "x.csv"
    lio.export_csv([lbl], p)
    (back,), errors = lio.import_csv(p)
    assert not errors
    assert back.specs == lbl.specs
    assert [line.enabled for line in back.lines] == [line.enabled for line in lbl.lines]


def test_csv_lines_column_is_checked() -> None:
    text = "main,lines\nA,011\nB,2x\n"
    labels, errors = lio.parse_csv_labels(text)
    assert [line.enabled for line in labels[0].lines] == [False, True, True]
    assert len(labels) == 2 and len(errors) == 1 and "'lines'" in errors[0]


def test_csv_specs_without_escapes_still_read() -> None:
    labels, _ = lio.parse_csv_labels('main;specs\nA;"Spanning=50 V; Tolerantie=10%"\n')
    assert labels[0].specs == {"Spanning": "50 V", "Tolerantie": "10%"}


# -- F-09: overflow frames at 180° ---------------------------------------------------------


def test_boxes_turn_along_at_180_degrees(engine: RenderEngine) -> None:
    lbl = make_label("A1", "Weerstand", "150 Ω", "¼ W")
    upright = engine.render(lbl)
    lbl.style.rotation = 180
    turned = engine.render(lbl)
    # half a turn about the centre of the printable area (its margins differ)
    px0, py0, px1, py1 = engine.printable_box
    w, h = px0 + px1, py0 + py1
    for a, b in zip(upright.lines, turned.lines):
        assert b.x0 == pytest.approx(w - a.x1, abs=1.5)
        assert b.y0 == pytest.approx(h - a.y1, abs=1.5)


# -- F-13: PNG export names ----------------------------------------------------------------


def test_png_names_ignore_case_and_avoid_reserved(tmp_path: Path) -> None:
    a = make_label("", "", "x")
    a.name = "LED"
    b = make_label("", "", "y")
    b.name = "led"
    c = make_label("", "", "z")
    c.name = "CON"
    names = [p.name for p in png_paths([a, b, c], tmp_path)]
    assert len({n.lower() for n in names}) == 3
    assert not safe_filename(c).upper().startswith("CON.") and safe_filename(c).upper() != "CON"


def test_png_paths_keep_existing_files(tmp_path: Path) -> None:
    a = make_label("", "", "x")
    a.name = "Doos"
    (tmp_path / "doos.png").write_bytes(b"")
    first = png_paths([a], tmp_path)[0]
    assert first.name.lower() == "doos.png"  # overwrite: same name
    kept = png_paths([a], tmp_path, keep_existing=True)[0]
    assert kept.name.lower() != "doos.png"


# -- F-14: huge pictures -------------------------------------------------------------------


def test_huge_embedded_picture_is_refused(engine: RenderEngine) -> None:
    buf = io.BytesIO()
    Image.new("1", (pictures.MAX_DECODE_SIDE + 1, 2)).save(buf, "PNG")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    assert pictures.decode(data) is None
    lbl = make_label("A1", "", "x")
    lbl.picture.kind = PictureKind.IMAGE
    lbl.picture.image = data
    engine.render(lbl)  # no exception


# -- F-16: font scan does not block --------------------------------------------------------


def test_resolve_does_not_wait_for_a_running_scan() -> None:
    reg = fonts.FontRegistry(scan_system=False)
    reg._scanning = True
    face = reg.resolve("Een Systeemfont")
    assert face.family == reg.fallback(False, False).family
    assert reg.missed_during_scan


def test_scan_in_background_reports_families() -> None:
    reg = fonts.FontRegistry(scan_system=False)
    got: list[list[str]] = []
    done = threading.Event()
    reg.scan_in_background(lambda fams: (got.append(fams), done.set()))
    assert done.wait(10)
    assert "DejaVu Sans" in got[0] and not reg._scanning


# -- F-20: right-to-left text --------------------------------------------------------------


def test_right_to_left_text_warns(engine: RenderEngine) -> None:
    r = engine.render(make_label("", "", "עברית"))
    assert any("rechts naar links" in w for w in r.warnings)
    r = engine.render(make_label("", "", "10 kΩ"))
    assert not any("rechts naar links" in w for w in r.warnings)
