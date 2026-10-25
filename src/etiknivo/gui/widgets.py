"""Small widgets and helpers shared by the inspector panels."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QBuffer, QIODevice, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QDoubleSpinBox, QLineEdit, QMenu, QToolButton

from etiknivo.gui import theme
from etiknivo.gui.qt_util import pil_to_pixmap
from etiknivo.i18n import N_, tr
from etiknivo.model import HAlign
from etiknivo.rendering import pictures, symbols

ALIGN_TEXT = {HAlign.LEFT: N_("Links"), HAlign.CENTER: N_("Midden"), HAlign.RIGHT: N_("Rechts")}


def spin(lo: float, hi: float, step: float, suffix: str, decimals: int = 1) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def symbol_icon(key: str) -> QIcon:
    """A symbol in the current text colour, for the picker."""
    img = symbols.draw_symbol(key, 56)
    mask = ImageOps.invert(img)
    rgba = Image.new("RGBA", img.size, theme.tokens().text)
    rgba.putalpha(mask)
    return QIcon(pil_to_pixmap(rgba))


def load_image(path: Path) -> str:
    """An image file encoded for a label; SVG files are drawn with Qt first."""
    if path.suffix.lower() != ".svg":
        return pictures.load_file(path)
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        raise pictures.ImageError(path.name)
    size = renderer.defaultSize().scaled(pictures.MAX_SIDE, pictures.MAX_SIDE,
                                         Qt.AspectRatioMode.KeepAspectRatio)
    qimg = QImage(size, QImage.Format.Format_ARGB32)
    qimg.fill(Qt.GlobalColor.transparent)
    painter = QPainter(qimg)
    renderer.render(painter)
    painter.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    qimg.save(buf, "PNG")
    return pictures.encode(Image.open(io.BytesIO(bytes(buf.data()))))


class FieldButton(QToolButton):
    """'{ }' button whose menu inserts a {field} into *edit*."""

    inserted = Signal()

    def __init__(self, edit: QLineEdit, fields: Callable[[], list[str]]) -> None:
        super().__init__()
        self.edit = edit
        self.fields = fields
        self.setText("{ }")
        self.setToolTip(tr("Veld invoegen: toont de waarde van een specificatie, "
                           "de naam, lade of categorie op het etiket"))
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu = QMenu(self)
        self._menu.aboutToShow.connect(self._fill)
        self.setMenu(self._menu)

    def _fill(self) -> None:
        self._menu.clear()
        for name in self.fields():
            self._menu.addAction(f"{{{name}}}", lambda n=name: self.insert_field(n))
        if not self._menu.actions():
            self._menu.addAction(tr("Nog geen velden")).setEnabled(False)

    def insert_field(self, name: str) -> None:
        self.edit.insert(f"{{{name}}}")
        self.edit.setFocus()
        self.inserted.emit()
