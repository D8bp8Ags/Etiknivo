"""Small Qt helpers."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import QDialog, QHeaderView


def pil_to_qimage(img: Image.Image) -> QImage:
    """Convert a PIL image (mode 1/L/RGB/RGBA) to a QImage (deep copy)."""
    if img.mode in ("1", "L"):
        g = img.convert("L")
        q = QImage(g.tobytes(), g.width, g.height, g.width, QImage.Format.Format_Grayscale8)
    elif img.mode == "RGBA":
        q = QImage(img.tobytes(), img.width, img.height, img.width * 4,
                   QImage.Format.Format_RGBA8888)
    else:
        rgb = img.convert("RGB")
        q = QImage(rgb.tobytes(), rgb.width, rgb.height, rgb.width * 3,
                   QImage.Format.Format_RGB888)
    return q.copy()


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    return QPixmap.fromImage(pil_to_qimage(img))


def with_shortcut(text: str, key: str | QKeySequence.StandardKey) -> str:
    """'Opslaan (⌘S)' on macOS, 'Opslaan (Ctrl+S)' on Windows and Linux."""
    seq = QKeySequence(key)
    return f"{text} ({seq.toString(QKeySequence.SequenceFormat.NativeText)})"


def ui_state() -> QSettings:
    """Where window sizes, panel widths and open sections are remembered."""
    from etiknivo.settings import data_dir

    return QSettings(str(data_dir() / "window.ini"), QSettings.Format.IniFormat)


def remember_size(window: QDialog, key: str, header: QHeaderView | None = None) -> None:
    """Open *window* at the size (and column widths) it had last time, and keep
    remembering them whenever it closes."""
    qs = ui_state()
    geo = qs.value(f"{key}/geometry")
    if geo is not None:
        window.restoreGeometry(geo)
    cols = qs.value(f"{key}/columns") if header is not None else None
    if cols is not None:
        header.restoreState(cols)

    def save() -> None:
        qs = ui_state()
        qs.setValue(f"{key}/geometry", window.saveGeometry())
        if header is not None:
            qs.setValue(f"{key}/columns", header.saveState())

    window.finished.connect(save)
