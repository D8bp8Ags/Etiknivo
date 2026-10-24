"""Import and export of the label library (JSON, CSV, backup archives)."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from etiknivo.i18n import tr
from etiknivo.model import Label, LayoutPreset, make_label
from etiknivo.storage.atomic import atomic_write_bytes, atomic_write_text
from etiknivo.storage.library import LibraryError, labels_from_document, labels_to_document

#: Column names accepted by the CSV importer (case-insensitive, with aliases).
CSV_COLUMNS = ("tray_id", "category", "main", "spec", "top", "name", "layout", "notes", "specs")
_ALIASES = {
    "id": "tray_id", "lade": "tray_id", "lade-id": "tray_id", "lade_id": "tray_id", "tray": "tray_id",
    "categorie": "category",
    "hoofdtekst": "main", "naam_op_label": "main", "tekst": "main",
    "specificatie": "spec", "specificaties": "spec", "specification": "spec",
    "bovenregel": "top", "naam": "name", "notities": "notes", "opmerkingen": "notes",
    "technische_specificaties": "specs",
}


# -- JSON -----------------------------------------------------------------------


def export_json(labels: Iterable[Label], path: Path) -> None:
    atomic_write_text(path, json.dumps(labels_to_document(labels), indent=2, ensure_ascii=False))


def import_json(path: Path) -> list[Label]:
    try:
        doc = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise LibraryError(f"JSON kon niet worden gelezen: {exc}") from exc
    return labels_from_document(doc)


# -- CSV ------------------------------------------------------------------------


def _norm(col: str) -> str:
    c = col.strip().lower().replace(" ", "_")
    return _ALIASES.get(c, c)


def _parse_specs(value: str) -> dict[str, str]:
    """Parse ``"Spanning=50 V; Tolerantie=10%"`` into a dict."""
    out: dict[str, str] = {}
    for part in value.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip():
                out[k.strip()] = v.strip()
    return out


def parse_csv_labels(text: str) -> tuple[list[Label], list[str]]:
    """Parse CSV text into labels.  Returns ``(labels, errors)``; rows with
    errors are skipped and reported, valid rows are still imported.

    The delimiter (``,`` or ``;``) is detected automatically.  Required column:
    ``main`` (alias ``hoofdtekst``).
    """
    text = text.lstrip("﻿")
    if not text.strip():
        return [], ["CSV-bestand is leeg"]
    try:
        dialect = csv.Sniffer().sniff(text.split("\n", 1)[0], delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        return [], ["CSV-bestand bevat geen kopregel"]
    colmap = {name: _norm(name) for name in reader.fieldnames}
    if "main" not in colmap.values():
        return [], [tr("Kolom 'main' (of 'hoofdtekst') ontbreekt in de kopregel")]

    labels: list[Label] = []
    errors: list[str] = []
    for lineno, raw in enumerate(reader, start=2):
        row = {colmap[k]: (v or "").strip() for k, v in raw.items() if k is not None}
        if not any(row.values()):
            continue
        if not row.get("main"):
            errors.append(tr("Regel {n}: hoofdtekst ontbreekt", n=lineno))
            continue
        layout = None
        if row.get("layout"):
            try:
                layout = LayoutPreset(row["layout"])
            except ValueError:
                errors.append(tr("Regel {n}: onbekende layout '{layout}', standaard gebruikt",
                                 n=lineno, layout=row["layout"]))
        lbl = make_label(
            row.get("tray_id", ""),
            row.get("category", ""),
            row["main"],
            row.get("spec", ""),
            name=row.get("name") or None,
            notes=row.get("notes", ""),
            layout=layout,
        )
        if row.get("top"):
            lbl.top.text = row["top"]
        if row.get("specs"):
            lbl.specs = _parse_specs(row["specs"])
        labels.append(lbl)
    return labels, errors


def import_csv(path: Path) -> tuple[list[Label], list[str]]:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return parse_csv_labels(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    return [], ["CSV-bestand kon niet worden gedecodeerd"]  # pragma: no cover


def labels_to_csv(labels: Iterable[Label]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["tray_id", "category", "top", "main", "spec", "name", "layout", "notes", "specs"])
    for lbl in labels:
        specs = "; ".join(f"{k}={v}" for k, v in lbl.specs.items())
        w.writerow([lbl.tray_id, lbl.category, lbl.top.text, lbl.main.text, lbl.bottom.text,
                    lbl.name, str(lbl.layout), lbl.notes, specs])
    return buf.getvalue()


def export_csv(labels: Iterable[Label], path: Path) -> None:
    # UTF-8 with BOM so Excel on macOS opens special characters (Ω, µ) correctly.
    atomic_write_bytes(path, ("﻿" + labels_to_csv(labels)).encode("utf-8"))


# -- Backup / restore -----------------------------------------------------------

BACKUP_MEMBERS = ("library.json", "settings.json")


def default_backup_name() -> str:
    return f"etiknivo-backup-{datetime.now():%Y%m%d-%H%M%S}.zip"


def create_backup(data_dir: Path, target: Path) -> list[str]:
    """Zip the library and settings into *target*.  Returns included names."""
    included: list[str] = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in BACKUP_MEMBERS:
            p = Path(data_dir) / name
            if p.exists():
                zf.write(p, name)
                included.append(name)
        zf.writestr("etiknivo-backup.json", json.dumps(
            {"app": "Etiknivo", "created": datetime.now().isoformat(timespec="seconds"), "files": included}))
    atomic_write_bytes(target, buf.getvalue())
    return included


def restore_backup(archive: Path, data_dir: Path) -> list[str]:
    """Restore library/settings from a backup archive.  The archive is fully
    validated before anything is overwritten."""
    try:
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
            if "library.json" not in names:
                raise LibraryError(tr("Back-up bevat geen library.json"))
            contents = {n: zf.read(n) for n in BACKUP_MEMBERS if n in names}
    except zipfile.BadZipFile as exc:
        raise LibraryError(tr("Geen geldig back-upbestand: {error}", error=exc)) from exc
    try:
        labels_from_document(json.loads(contents["library.json"].decode("utf-8")))
        if "settings.json" in contents:
            json.loads(contents["settings.json"].decode("utf-8"))
    except ValueError as exc:
        raise LibraryError(tr("Back-up is beschadigd: {error}", error=exc)) from exc
    for name, data in contents.items():
        atomic_write_bytes(Path(data_dir) / name, data)
    return sorted(contents)
