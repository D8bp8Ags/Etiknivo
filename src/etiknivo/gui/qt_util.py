"""Small Qt helpers."""

from __future__ import annotations

from PIL import Image
from PySide6.QtGui import QImage, QKeySequence, QPixmap


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
