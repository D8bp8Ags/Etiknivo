"""Inspector part for the free layout: the label's elements and the selected one."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui.widgets import ALIGN_TEXT, FieldButton, combo, load_image, spin, style_row, symbol_icon
from etiknivo.i18n import tr
from etiknivo.model import ELEMENT_TITLES, ElementKind, HAlign, Label, LabelElement
from etiknivo.rendering import pictures, symbols

#: Size of a new element (mm) and, for text, its font size.
NEW_SIZE = {
    ElementKind.TEXT: (14.0, 4.0),
    ElementKind.QR: (9.0, 9.0),
    ElementKind.BARCODE: (20.0, 4.0),
    ElementKind.SYMBOL: (6.0, 6.0),
    ElementKind.IMAGE: (8.0, 8.0),
    ElementKind.LINE: (0.0, 0.125),  # full width
    ElementKind.BOX: (0.0, 0.0),  # the whole printable area
}


def new_element(kind: ElementKind, area_mm: tuple[float, float]) -> LabelElement:
    """A new element of *kind*, centred in a printable area of *area_mm*."""
    aw, ah = area_mm
    w, h = NEW_SIZE[kind]
    w, h = min(w or aw, aw), min(h or ah, ah)
    el = LabelElement(kind)
    if kind == ElementKind.TEXT:
        el.text, el.font_size_pt = tr("Tekst"), 10.0
    elif kind in (ElementKind.QR, ElementKind.BARCODE):
        el.text = "{Lade}"
    elif kind == ElementKind.SYMBOL:
        el.symbol = next(iter(symbols.SYMBOLS))
    el.resize(w, h)
    el.move_to((aw - el.w_mm) / 2, (ah - el.h_mm) / 2)
    return el


def element_text(el: LabelElement) -> str:
    """How an element is listed: its kind and, where it has one, its content."""
    if el.has_text and el.text.strip():
        return f"{el.title}: {el.text.strip()}"
    if el.kind == ElementKind.SYMBOL and el.symbol in symbols.SYMBOLS:
        return f"{el.title}: {tr(symbols.SYMBOLS[el.symbol][0])}"
    return el.title


class ElementPanel(QWidget):
    """List of elements plus an editor for the selected one."""

    changed = Signal()  # an element was added, removed, reordered or edited
    selected = Signal(str)  # element id, "" for none

    def __init__(self, area_mm: Callable[[], tuple[float, float]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.area_mm = area_mm
        self.label: Label | None = None
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        box = QGroupBox(tr("Elementen"))
        bl = QVBoxLayout(box)
        self.list = QListWidget()
        self.list.setFixedHeight(130)
        self.add_btn = QToolButton()
        self.add_btn.setText(tr("Toevoegen") + " ▾")
        self.add_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.add_btn)
        for kind, title in ELEMENT_TITLES.items():
            menu.addAction(tr(title), lambda k=kind: self.add(k))
        self.add_btn.setMenu(menu)
        self.del_btn = QToolButton()
        self.del_btn.setText(tr("Verwijderen"))
        self.up_btn = QToolButton()
        self.up_btn.setText("▲")
        self.up_btn.setToolTip(tr("Naar voren: boven de andere elementen tekenen"))
        self.down_btn = QToolButton()
        self.down_btn.setText("▼")
        self.down_btn.setToolTip(tr("Naar achteren: onder de andere elementen tekenen"))
        row = QHBoxLayout()
        row.setSpacing(4)
        for b in (self.add_btn, self.del_btn, self.up_btn, self.down_btn):
            row.addWidget(b)
        row.addStretch(1)
        hint = QLabel(tr("Sleep een element in het ontwerp om het te verplaatsen; sleep het "
                         "hoekje rechtsonder om het groter of kleiner te maken. Pijltjestoetsen "
                         "schuiven 1 dot (met Shift 1 mm)."))
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        bl.addWidget(self.list)
        bl.addLayout(row)
        bl.addWidget(hint)
        lay.addWidget(box)

        self.editor = QGroupBox(tr("Element"))
        f = QFormLayout(self.editor)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.x = spin(-50, 150, 0.25, " mm", 2)
        self.y = spin(-50, 50, 0.25, " mm", 2)
        self.w = spin(0.125, 150, 0.25, " mm", 2)
        self.h = spin(0.125, 50, 0.25, " mm", 2)
        pos = QHBoxLayout()
        pos.addWidget(self.x)
        pos.addWidget(self.y)
        size = QHBoxLayout()
        size.addWidget(self.w)
        size.addWidget(self.h)
        self.text = QLineEdit()
        self.text.setPlaceholderText(tr("Tekst of {veld}…"))
        self.field_btn = FieldButton(self.text,
                                     lambda: self.label.field_names() if self.label else [])
        text_row = QHBoxLayout()
        text_row.setSpacing(4)
        text_row.addWidget(self.text, 1)
        text_row.addWidget(self.field_btn)
        self.font = combo()
        self.font.setEditable(True)
        self.font.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.size = spin(3, 60, 0.5, " pt")
        self.bold = QCheckBox(tr("Vet"))
        self.italic = QCheckBox(tr("Cursief"))
        font_row = style_row(self.bold, self.italic)
        self.align = combo()
        for a, t in ALIGN_TEXT.items():
            self.align.addItem(tr(t), a)
        self.symbol = combo()
        self.symbol.setIconSize(QSize(28, 28))
        for key, (name, _p) in symbols.SYMBOLS.items():
            self.symbol.addItem(symbol_icon(key), tr(name), key)
        self.image_btn = QPushButton(tr("Afbeelding kiezen…"))
        self.image_btn.clicked.connect(self._choose_image)
        self.fitted = QLabel()
        self.fitted.setObjectName("hint")
        f.addRow(tr("Plaats (x, y)"), pos)
        f.addRow(tr("Grootte (b, h)"), size)
        f.addRow(tr("Inhoud"), text_row)
        f.addRow(tr("Lettertype"), self.font)
        f.addRow(tr("Grootte"), self.size)
        f.addRow(tr("Stijl"), font_row)
        f.addRow(tr("Uitlijning"), self.align)
        f.addRow(tr("Symbool"), self.symbol)
        f.addRow(tr("Afbeelding"), self.image_btn)
        f.addRow("", self.fitted)
        self._form = f
        self._text_row, self._font_row = text_row, font_row
        lay.addWidget(self.editor)

        self.list.currentRowChanged.connect(self._row_changed)
        self.del_btn.clicked.connect(self.delete_selected)
        self.up_btn.clicked.connect(lambda: self.move_selected(1))
        self.down_btn.clicked.connect(lambda: self.move_selected(-1))
        for w in (self.x, self.y, self.w, self.h, self.size):
            w.valueChanged.connect(self._apply)
        self.text.textEdited.connect(self._apply)
        self.field_btn.inserted.connect(self._apply)
        self.font.currentTextChanged.connect(self._apply)
        for w in (self.bold, self.italic):
            w.toggled.connect(self._apply)
        for w in (self.align, self.symbol):
            w.currentIndexChanged.connect(self._apply)
        self._update_widgets()

    # -- state --------------------------------------------------------------------------

    def set_families(self, families: list[str]) -> None:
        cur = self.font.currentText()
        self.font.blockSignals(True)
        self.font.clear()
        self.font.addItems(families)
        self.font.setCurrentText(cur)
        self.font.blockSignals(False)

    def current(self) -> LabelElement | None:
        row = self.list.currentRow()
        if self.label is None or not 0 <= row < len(self.label.elements):
            return None
        return self.label.elements[row]

    def set_label(self, label: Label | None) -> None:
        """Show *label*'s elements, keeping the selection when it still exists."""
        keep = self.current().id if self.current() is not None else ""
        self.label = label
        self._fill(keep)

    def _fill(self, select_id: str = "") -> None:
        self._loading = True
        try:
            self.list.clear()
            row = -1
            for n, el in enumerate(self.label.elements if self.label else []):
                self.list.addItem(QListWidgetItem(element_text(el)))
                if el.id == select_id:
                    row = n
            self.list.setCurrentRow(row)
        finally:
            self._loading = False
        self._load_editor()

    def select(self, element_id: str) -> None:
        """Select an element (from the design view) without echoing it back."""
        ids = [el.id for el in self.label.elements] if self.label else []
        self._loading = True
        self.list.setCurrentRow(ids.index(element_id) if element_id in ids else -1)
        self._loading = False
        self._load_editor()

    def refresh(self) -> None:
        """The selected element was moved or changed elsewhere (design view)."""
        cur = self.current()
        if self.label is not None and len(self.label.elements) != self.list.count():
            self._fill(cur.id if cur else "")
            return
        self._load_editor()

    def show_fitted(self, size_pt: float | None) -> None:
        el = self.current()
        if el is not None and size_pt is not None and size_pt < el.font_size_pt - 0.05:
            self.fitted.setText(tr("Automatisch verkleind tot {pt} pt", pt=f"{size_pt:.1f}"))
        else:
            self.fitted.setText("")

    def _load_editor(self) -> None:
        el = self.current()
        self._loading = True
        try:
            if el is not None:
                self.x.setValue(el.x_mm)
                self.y.setValue(el.y_mm)
                self.w.setValue(el.w_mm)
                self.h.setValue(el.h_mm)
                if self.text.text() != el.text:
                    self.text.setText(el.text)
                self.font.setCurrentText(el.font_family)
                self.size.setValue(el.font_size_pt)
                self.bold.setChecked(el.bold)
                self.italic.setChecked(el.italic)
                self.align.setCurrentIndex(self.align.findData(el.align))
                if el.kind == ElementKind.SYMBOL:
                    self.symbol.setCurrentIndex(max(0, self.symbol.findData(el.symbol)))
                self.list.currentItem().setText(element_text(el))
        finally:
            self._loading = False
        self._update_widgets()

    def _update_widgets(self) -> None:
        el = self.current()
        self.editor.setVisible(el is not None)
        self.editor.setTitle(el.title if el is not None else tr("Element"))
        for b in (self.del_btn, self.up_btn, self.down_btn):
            b.setEnabled(el is not None)
        if el is None:
            return
        kind = el.kind
        is_text = kind == ElementKind.TEXT
        rows = ((self._text_row, el.has_text), (self.font, is_text), (self.size, is_text),
                (self._font_row, is_text),
                (self.align, is_text), (self.symbol, kind == ElementKind.SYMBOL),
                (self.image_btn, kind == ElementKind.IMAGE), (self.fitted, is_text))
        for row, on in rows:
            self._form.setRowVisible(row, on)
        self.image_btn.setText(tr("Andere afbeelding…") if el.image_png
                               else tr("Afbeelding kiezen…"))

    # -- editing ------------------------------------------------------------------------

    def _row_changed(self, _row: int) -> None:
        if self._loading:
            return
        self._load_editor()
        el = self.current()
        self.selected.emit(el.id if el is not None else "")

    def _apply(self) -> None:
        el = self.current()
        if self._loading or el is None:
            return
        # the boxes show 2 decimals: only take a value the user actually changed
        def pick(box: QDoubleSpinBox, now: float) -> float:
            return box.value() if abs(box.value() - now) > 0.006 else now
        el.move_to(pick(self.x, el.x_mm), pick(self.y, el.y_mm))
        el.resize(pick(self.w, el.w_mm), pick(self.h, el.h_mm))
        el.text = self.text.text()
        if self.font.currentText().strip():
            el.font_family = self.font.currentText().strip()
        el.font_size_pt = self.size.value()
        el.bold = self.bold.isChecked()
        el.italic = self.italic.isChecked()
        el.align = HAlign(self.align.currentData())
        if el.kind == ElementKind.SYMBOL:
            el.symbol = self.symbol.currentData() or el.symbol
        self.list.currentItem().setText(element_text(el))
        self.changed.emit()

    def add(self, kind: ElementKind) -> LabelElement | None:
        if self.label is None:
            return None
        el = new_element(kind, self.area_mm())
        self.label.elements.append(el)
        self._fill(el.id)
        self.selected.emit(el.id)
        self.changed.emit()
        if kind == ElementKind.IMAGE:
            self._choose_image()
        return el

    def delete_selected(self) -> None:
        el = self.current()
        if el is None or self.label is None:
            return
        self.label.elements.remove(el)
        self._fill()
        self.selected.emit("")
        self.changed.emit()

    def move_selected(self, step: int) -> None:
        """Change the drawing order: +1 draws the element later (on top)."""
        el = self.current()
        if el is None or self.label is None:
            return
        els = self.label.elements
        i = els.index(el)
        j = max(0, min(len(els) - 1, i + step))
        if i == j:
            return
        els.insert(j, els.pop(i))
        self._fill(el.id)
        self.changed.emit()

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Afbeelding kiezen"), "",
            tr("Afbeeldingen") + " (*.png *.jpg *.jpeg *.gif *.bmp *.tif *.tiff *.svg)")
        if path:
            self.set_image_file(Path(path))

    def set_image_file(self, path: Path) -> bool:
        el = self.current()
        if el is None or el.kind != ElementKind.IMAGE:
            return False
        try:
            el.image_png = load_image(path)
        except pictures.ImageError:
            QMessageBox.warning(self, tr("Afbeelding"), tr(
                "'{name}' kon niet worden gelezen als afbeelding.", name=path.name))
            return False
        self._update_widgets()
        self.changed.emit()
        return True
