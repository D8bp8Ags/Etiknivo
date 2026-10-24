"""Library persistence, JSON/CSV import-export, backups and settings."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from etiknivo.model import Label, LayoutPreset, make_label
from etiknivo.rendering.export import ExportView, export_pdf, export_pngs, export_svg
from etiknivo.settings import Calibration, Settings, data_dir, load_settings, save_settings
from etiknivo.storage import io as lio
from etiknivo.storage.library import Library, LibraryError, open_library, seed_labels

EXPECTED_SEED = [
    ("A01", "Schuifpotmeters", "10 kΩ", "Mono · 75 / 88 mm"),
    ("A02", "Schuifpotmeters", "10 kΩ", "Stereo · 60 / 75 mm"),
    ("A03", "Rotary encoders", "EC11 / module", "Met knoppen"),
    ("A04", "Drukknoppen", "16 mm", "LED / zonder LED"),
    ("A05", "Audiojacks SMD", "3,5 mm", "Diverse typen"),
    ("A06", "Audiojacks", "3,5 mm", "Overige typen"),
    ("A07", "Lasklemmen", "WAGO", "3- en 5-voudig"),
    ("A08", "Dupont", "Connectoren", "Contacten + behuizingen"),
    ("A09", "Weerstand", "150 Ω", "¼ W"),
    ("A10", "Weerstanden", "Assortiment", "10 Ω – 1 MΩ"),
    ("A11", "Condensator", "100 nF", "Keramisch · 50 V"),
    ("A12", "IC · Logica", "74HC14", "DIP-14 · Schmitt"),
    ("A13", "LED", "3 mm", "Diverse kleuren"),
    ("A14", "Antennes", "2,4 GHz", "Wi-Fi · u.FL"),
    ("A15", "Audio", "Buzzers / speaker", "Passief / module"),
    ("A16", "ESP32-S3", "LilyGO T-QT Pro", "0,85″ IPS"),
    ("A17", "ESP32-S3", "LilyGO T-Display", "TFT / AMOLED"),
    ("A18", "ESP32-S3", "Heltec Tracker", "LoRa / GNSS"),
    ("A19", "Isolatie", "Krimpkous", "Diverse maten"),
    ("M01", "Dupont F-F", "10 cm", "Rood / zwart / mix"),
    ("M02", "Dupont", "20 cm", "F-F / M-F"),
    ("M03", "Dupont", "10 cm", "M-F / M-M"),
    ("L01", "Prototyping", "Breadboards", "Flatcable"),
]


def test_seed_library_has_the_23_raaco_labels() -> None:
    labels = seed_labels()
    assert [(lbl.tray_id, lbl.category, lbl.main.text, lbl.bottom.text) for lbl in labels] \
        == EXPECTED_SEED
    assert len({lbl.id for lbl in labels}) == 23
    for lbl in labels:
        # default style: bold main text, smaller category/spec, centred, auto-fit, no border
        assert lbl.layout == LayoutPreset.CATEGORY_MAIN_SPEC
        assert lbl.main.bold and not lbl.top.bold and not lbl.bottom.bold
        assert lbl.main.font_size_pt > lbl.top.font_size_pt
        assert lbl.main.font_size_pt > lbl.bottom.font_size_pt
        assert all(ln.align == "center" for ln in lbl.lines)
        assert lbl.style.autofit and not lbl.style.border and not lbl.style.invert
        # tray id is library metadata, never printed text
        assert all(lbl.tray_id not in ln.text for ln in lbl.lines)


def test_first_start_seeds_then_loads(tmp_path: Path) -> None:
    path = tmp_path / "lib.json"
    lib, seeded = open_library(path)
    assert seeded and len(lib) == 23 and path.exists()
    lib.get(lib.labels[0].id).name = "Gewijzigd"
    lib.save()
    lib2, seeded2 = open_library(path)
    assert not seeded2 and lib2.labels[0].name == "Gewijzigd"


def test_json_roundtrip_preserves_everything(tmp_path: Path) -> None:
    lbl = make_label("Z9", "Test", "4,7 µF", "25 °C · ¼ W", notes="notitie")
    lbl.specs = {"Spanning": "50 V"}
    lbl.main.italic = True
    lbl.style.margin_h_mm = 2.25
    lbl.style.rotation = 180
    lib = Library(tmp_path / "l.json")
    lib.add(lbl)
    lib.save()
    raw = json.loads((tmp_path / "l.json").read_text("utf-8"))
    assert raw["app"] == "Etiknivo" and raw["schema"] == 1
    assert "µ" in (tmp_path / "l.json").read_text("utf-8")  # human-readable, not escaped
    lib2 = Library(tmp_path / "l.json")
    lib2.load()
    assert lib2.labels[0].to_dict() == lbl.to_dict()


def test_save_keeps_backup_copy(tmp_path: Path) -> None:
    lib = Library(tmp_path / "l.json")
    lib.add(make_label("A", "", "eerste"))
    lib.save()
    lib.add(make_label("B", "", "tweede"))
    lib.save()
    bak = json.loads((tmp_path / "l.json.bak").read_text("utf-8"))
    assert len(bak["labels"]) == 1


def test_corrupt_library_raises(tmp_path: Path) -> None:
    p = tmp_path / "l.json"
    p.write_text("{niet: json", "utf-8")
    with pytest.raises(LibraryError):
        Library(p).load()
    p.write_text('{"labels": "nee"}', "utf-8")
    with pytest.raises(LibraryError):
        Library(p).load()


def test_library_operations() -> None:
    lib = Library(Path("unused.json"))
    a = lib.add(make_label("A1", "Cat", "Een"))
    b = lib.add(make_label("A2", "Dog", "Twee"))
    dup = lib.duplicate(a.id)
    assert dup is not None and dup.id != a.id and dup.main.text == "Een"
    assert [x.id for x in lib] == [a.id, dup.id, b.id]
    assert lib.categories() == ["Cat", "Dog"]
    assert lib.remove([a.id, b.id]) == 2
    assert len(lib) == 1
    again = lib.add(dup)  # same id twice → gets a fresh id
    assert again.id != dup.id


def test_layout_switch_keeps_text() -> None:
    lbl = make_label("A1", "Categorie", "Naam", "Spec")
    for preset in (LayoutPreset.SINGLE, LayoutPreset.MAIN_SPEC, LayoutPreset.CATEGORY_MAIN_SPEC):
        lbl.apply_layout(preset)
        assert [ln.text for ln in lbl.lines] == ["Categorie", "Naam", "Spec"]
    lbl.apply_layout(LayoutPreset.SINGLE)
    assert [i for i, _ in lbl.visible_lines()] == [1]
    lbl.apply_layout(LayoutPreset.MAIN_SPEC)
    assert [i for i, _ in lbl.visible_lines()] == [1, 2]


def test_json_export_import_and_merge(tmp_path: Path) -> None:
    labels = seed_labels()[:3]
    lio.export_json(labels, tmp_path / "x.json")
    back = lio.import_json(tmp_path / "x.json")
    assert [x.to_dict() for x in back] == [x.to_dict() for x in labels]
    lib = Library(tmp_path / "lib.json")
    lib.add(labels[0].clone(new_id=False))
    back[0].name = "bijgewerkt"
    added, updated = lib.merge(back)
    assert (added, updated) == (2, 1)
    assert lib.get(labels[0].id).name == "bijgewerkt"


def test_csv_import_aliases_semicolon_and_errors() -> None:
    text = ("Lade;Categorie;Hoofdtekst;Specificatie;Notities;Layout\n"
            "B01;Weerstand;1 kΩ;¼ W;in doos 2;\n"
            "B02;Condensator;;Keramisch;;\n"  # missing main text → error
            ";;Alleen naam;;;single\n"
            "B04;X;Y;Z;;onbekend\n")
    labels, errors = lio.parse_csv_labels(text)
    assert [lbl.main.text for lbl in labels] == ["1 kΩ", "Alleen naam", "Y"]
    assert labels[0].tray_id == "B01" and labels[0].notes == "in doos 2"
    assert labels[0].bottom.text == "¼ W"
    assert labels[1].layout == LayoutPreset.SINGLE
    assert len(errors) == 2
    assert "Regel 3" in errors[0] and "onbekende layout" in errors[1]


def test_csv_requires_main_column() -> None:
    labels, errors = lio.parse_csv_labels("a,b\n1,2\n")
    assert not labels and errors


def test_csv_export_import_roundtrip(tmp_path: Path) -> None:
    labels = seed_labels()
    labels[0].specs = {"Weerstand": "10 kΩ", "Type": "lineair"}
    lio.export_csv(labels, tmp_path / "x.csv")
    assert (tmp_path / "x.csv").read_bytes().startswith(b"\xef\xbb\xbf")  # BOM for Excel
    back, errors = lio.import_csv(tmp_path / "x.csv")
    assert not errors
    assert [(x.tray_id, x.category, x.main.text, x.bottom.text, x.name) for x in back] == \
        [(x.tray_id, x.category, x.main.text, x.bottom.text, x.name) for x in labels]
    assert back[0].specs == {"Weerstand": "10 kΩ", "Type": "lineair"}


def test_csv_import_cp1252(tmp_path: Path) -> None:
    p = tmp_path / "w.csv"
    p.write_bytes("main;spec\nCondensator;25 °C\n".encode("cp1252"))
    labels, errors = lio.import_csv(p)
    assert not errors and labels[0].bottom.text == "25 °C"


def test_backup_and_restore(tmp_path: Path) -> None:
    d = data_dir()
    lib, _ = open_library(d / "library.json")
    save_settings(Settings(density=2))
    archive = tmp_path / "backup.zip"
    assert lio.create_backup(d, archive) == ["library.json", "settings.json"]
    lib.replace_all([make_label("X", "", "weg")])
    lib.save()
    save_settings(Settings(density=0))
    assert sorted(lio.restore_backup(archive, d)) == ["library.json", "settings.json"]
    lib.load()
    assert len(lib) == 23
    assert load_settings().density == 2


def test_restore_rejects_bad_archives(tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(LibraryError):
        lio.restore_backup(bad, tmp_path)
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("x.txt", "x")
    with pytest.raises(LibraryError):
        lio.restore_backup(empty, tmp_path)
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(broken, "w") as zf:
        zf.writestr("library.json", "{kapot")
    (tmp_path / "library.json").write_text("origineel", "utf-8")
    with pytest.raises(LibraryError):
        lio.restore_backup(broken, tmp_path)
    assert (tmp_path / "library.json").read_text("utf-8") == "origineel"  # untouched


def test_settings_roundtrip_and_defaults(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    assert load_settings(p) == Settings()
    s = Settings(density=2, printer_address="AA", calibration=Calibration(offset_feed_px=3))
    save_settings(s, p)
    assert load_settings(p) == s
    p.write_text("kapot", "utf-8")
    assert load_settings(p) == Settings()  # corrupt → defaults, no crash


def test_label_from_dict_tolerates_missing_fields() -> None:
    lbl = Label.from_dict({"name": "oud", "lines": [{"text": "a"}]})
    assert len(lbl.lines) == 3 and lbl.lines[0].text == "a"
    assert not lbl.lines[2].enabled


def test_png_pdf_svg_export(tmp_path: Path, engine) -> None:  # noqa: ANN001
    from PIL import Image

    labels = seed_labels()[:3]
    paths = export_pngs(engine, labels, tmp_path / "png", ExportView.RASTER)
    assert len(paths) == 3 and paths[0].name.startswith("A01_")
    assert Image.open(paths[0]).size == (96, 240)
    paths = export_pngs(engine, labels, tmp_path / "png2", ExportView.DESIGN, scale=4)
    assert Image.open(paths[0]).size == (960, 448)
    export_pdf(engine, labels, tmp_path / "x.pdf")
    assert (tmp_path / "x.pdf").read_bytes().startswith(b"%PDF")
    export_svg(engine, labels[0], tmp_path / "x.svg")
    svg = (tmp_path / "x.svg").read_text("utf-8")
    assert 'width="30.0mm"' in svg and "data:image/png;base64," in svg


def test_history_undo_redo_and_merging() -> None:
    from etiknivo.model import make_label
    from etiknivo.storage.history import History, Snapshot

    now = [0.0]
    h = History(clock=lambda: now[0])
    a = make_label("", "Cat", "A", "")
    h.reset(Snapshot.take([a], [a.id]))
    for text in ("Ab", "Abc", "Abcd"):  # typing burst → one step
        a.main.text = text
        now[0] += 0.3
        h.record(Snapshot.take([a], [a.id]), merge_key=a.id)
    now[0] += 5
    b = make_label("", "Cat", "B", "")
    h.record(Snapshot.take([a, b], [b.id]))  # add a label
    s1 = h.undo()
    assert [lbl.main.text for lbl in s1.labels()] == ["Abcd"]
    s0 = h.undo()
    assert [lbl.main.text for lbl in s0.labels()] == ["A"]
    assert h.undo() is None and h.can_redo()
    assert [lbl.main.text for lbl in h.redo().labels()] == ["Abcd"]
    assert len(h.redo().labels()) == 2 and not h.can_redo()


def test_history_tracks_unsaved_draft() -> None:
    from etiknivo.storage.history import History, Snapshot

    a = make_label("A1", "Audio", "Origineel")
    h = History(clock=lambda: 0.0)
    h.reset(Snapshot.take([a], [a.id]))
    draft = a.clone(new_id=False)
    draft.main.text = "Concept"
    h.record(Snapshot.take([a], [a.id], draft))  # only the draft changed: still undoable
    assert h.can_undo()
    assert h.undo().draft() is None
    assert h.redo().draft().main.text == "Concept"


def test_library_update_replaces_by_id(tmp_path) -> None:  # noqa: ANN001

    lib = Library(tmp_path / "l.json")
    a = lib.add(make_label("A1", "Audio", "Oud"))
    new = a.clone(new_id=False)
    new.main.text = "Nieuw"
    assert lib.update(new) and lib.get(a.id).main.text == "Nieuw"
    assert not lib.update(make_label("B", "", "x"))
