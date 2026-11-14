"""Export rendered labels to PNG, PDF and SVG."""

from __future__ import annotations

import base64
import io
import re
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path

from PIL import Image

from etiknivo import APP_NAME
from etiknivo.i18n import tr
from etiknivo.model import Label
from etiknivo.rendering.engine import RenderEngine
from etiknivo.storage.atomic import atomic_write_bytes


class ExportView(StrEnum):
    DESIGN = "design"  # landscape, full 30 × 14 mm label, 1-bit as printed
    RASTER = "raster"  # native printer orientation (96 × 240), calibration applied


#: names Windows does not allow for a file, whatever the extension
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(label: Label) -> str:
    base = f"{label.tray_id}_{label.name}" if label.tray_id else label.name
    base = re.sub(r"[^\w\-.,() ]+", "_", base, flags=re.UNICODE).strip(" ._") or label.id[:8]
    base = base[:80].rstrip(" .")
    if base.split(".")[0].upper() in _RESERVED:
        base = f"_{base}"
    return base


def png_paths(labels: Iterable[Label], directory: Path, keep_existing: bool = False
              ) -> list[Path]:
    """The file each label gets when exported to *directory*.  Names are
    compared without case, because macOS and Windows do not tell "LED.png"
    and "led.png" apart; with *keep_existing* files that are already there
    are not reused either (the new file gets a number)."""
    directory = Path(directory)
    taken: set[str] = set()
    if keep_existing and directory.is_dir():
        taken = {p.name.casefold() for p in directory.iterdir()}
    out: list[Path] = []
    for lbl in labels:
        name = safe_filename(lbl)
        candidate, n = name, 2
        while f"{candidate}.png".casefold() in taken:
            candidate, n = f"{name}_{n}", n + 1
        taken.add(f"{candidate}.png".casefold())
        out.append(directory / f"{candidate}.png")
    return out


def export_image(engine: RenderEngine, label: Label, view: ExportView = ExportView.DESIGN,
                 scale: int = 1) -> Image.Image:
    r = engine.render(label)
    img = r.mono if view == ExportView.DESIGN else r.raster
    img = img.convert("L")
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST)
    return img


def export_png(engine: RenderEngine, label: Label, path: Path,
               view: ExportView = ExportView.DESIGN, scale: int = 1) -> None:
    img = export_image(engine, label, view, scale)
    buf = io.BytesIO()
    dpi = engine.profile.dpi * scale
    img.save(buf, "PNG", dpi=(dpi, dpi))
    atomic_write_bytes(path, buf.getvalue())


def export_pngs(engine: RenderEngine, labels: Iterable[Label], directory: Path,
                view: ExportView = ExportView.DESIGN, scale: int = 1,
                keep_existing: bool = False) -> list[Path]:
    """One PNG per label (see :func:`png_paths` for the names)."""
    labels = list(labels)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    out = png_paths(labels, directory, keep_existing)
    for lbl, p in zip(labels, out):
        export_png(engine, lbl, p, view, scale)
    return out


def export_pdf(engine: RenderEngine, labels: list[Label], path: Path) -> None:
    """One page per label at true physical size (the label roll in the profile)."""
    if not labels:
        raise ValueError(tr("Geen labels om te exporteren"))
    pages = [engine.render(lbl).mono.convert("L") for lbl in labels]
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", resolution=float(engine.profile.dpi), save_all=True,
                  append_images=pages[1:], title=tr("{app}-labels", app=APP_NAME))
    atomic_write_bytes(path, buf.getvalue())


def export_svg(engine: RenderEngine, label: Label, path: Path) -> None:
    """SVG with physical mm dimensions, embedding the exact 1-bit bitmap."""
    img = engine.render(label).mono.convert("L")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    wmm, hmm = engine.profile.label_width_mm, engine.profile.label_height_mm
    title = (label.name or "").replace("&", "&amp;").replace("<", "&lt;")
    svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{wmm}mm" height="{hmm}mm" '
           f'viewBox="0 0 {img.width} {img.height}">\n'
           f'  <title>{title}</title>\n'
           f'  <image width="{img.width}" height="{img.height}" style="image-rendering:pixelated" '
           f'href="data:image/png;base64,{b64}"/>\n</svg>\n')
    atomic_write_bytes(path, svg.encode("utf-8"))
