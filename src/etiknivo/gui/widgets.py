"""Small widgets and helpers shared by the inspector panels."""

from __future__ import annotations

import functools
import io
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QToolButton,
    QWidget,
)

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


def combo(min_chars: int = 6) -> QComboBox:
    """A combo box that may get narrower than its longest entry (the text is
    cut off with an ellipsis), so a narrow side panel never has to scroll
    sideways."""
    c = QComboBox()
    c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(min_chars)
    return c


def style_row(*boxes: QCheckBox) -> QHBoxLayout:
    """Check boxes such as Vet and Cursief side by side on their own form row."""
    row = QHBoxLayout()
    row.setSpacing(14)
    for box in boxes:
        row.addWidget(box)
    row.addStretch(1)
    return row


def symbol_combo(none: str = "") -> QComboBox:
    """Picker for a label symbol: the symbols under a heading per category.
    With *none*, a first choice by that name stands for no symbol (data "")."""
    c = combo()
    c.setIconSize(QSize(28, 28))
    c.setMaxVisibleItems(16)
    if none:
        c.addItem(none, "")
    heading = QFont(c.font())
    heading.setWeight(QFont.Weight.DemiBold)
    for category, keys in symbols.SYMBOL_CATEGORIES:
        c.addItem(tr(category).upper())
        item = c.model().item(c.count() - 1)
        item.setEnabled(False)
        item.setFont(heading)
        for key in keys:
            c.addItem(symbol_icon(key), "  " + tr(symbols.SYMBOLS[key][0]), key)
    return c


def select_symbol(c: QComboBox, key: str) -> None:
    """Show *key* in a :func:`symbol_combo`; an unknown key shows the first symbol."""
    i = c.findData(key)
    c.setCurrentIndex(i if i >= 0 else c.findData(next(iter(symbols.SYMBOLS))))


def symbol_icon(key: str) -> QIcon:
    """A symbol in the current text colour, for the picker."""
    return _symbol_icon(key, theme.tokens().text)


@functools.cache
def _symbol_icon(key: str, colour: str) -> QIcon:
    img = symbols.draw_symbol(key, 56)
    mask = ImageOps.invert(img)
    rgba = Image.new("RGBA", img.size, colour)
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
        from etiknivo.model import field_help

        self._menu.clear()
        help_ = field_help()
        names = self.fields()
        own = [n for n in names if n not in help_]
        builtin = [n for n in names if n in help_]
        if own:
            self._menu.addSection(tr("Specificaties van dit label"))
            for name in own:
                self._menu.addAction(f"{{{name}}}", lambda n=name: self.insert_field(n))
        if builtin:
            self._menu.addSection(tr("Voor elk label"))
            for name in builtin:
                act = self._menu.addAction(f"{{{name}}}   –  {help_[name]}",
                                           lambda n=name: self.insert_field(n))
                act.setToolTip(help_[name])
        if not names:
            self._menu.addAction(tr("Nog geen velden")).setEnabled(False)

    def insert_field(self, name: str) -> None:
        self.edit.insert(f"{{{name}}}")
        self.edit.setFocus()
        self.inserted.emit()


def segmented(titles: list[str], exclusive: bool = True) -> tuple[QWidget, list[QToolButton]]:
    """Buttons side by side as one control, like a switch with several
    positions.  With *exclusive* one is always checked."""
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    buttons: list[QToolButton] = []
    for n, title in enumerate(titles):
        btn = QToolButton()
        btn.setObjectName("segment")
        btn.setProperty("pos", "first" if n == 0 else "last" if n == len(titles) - 1
                        else "middle")
        btn.setText(title)
        btn.setCheckable(True)
        btn.setAutoExclusive(exclusive)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(btn)
        buttons.append(btn)
    return box, buttons
