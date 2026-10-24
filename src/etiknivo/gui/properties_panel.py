"""Right panel: label properties."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
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
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui import theme
from etiknivo.gui.qt_util import pil_to_pixmap
from etiknivo.i18n import N_, tr
from etiknivo.model import (
    LAYOUT_TITLES,
    SLOT_BOTTOM,
    SLOT_NAMES,
    CodeKind,
    HAlign,
    Label,
    LayoutPreset,
    PictureKind,
    VAlign,
)
from etiknivo.rendering import pictures, symbols

ALIGN_TEXT = {HAlign.LEFT: N_("Links"), HAlign.CENTER: N_("Midden"), HAlign.RIGHT: N_("Rechts")}
VALIGN_TEXT = {VAlign.TOP: N_("Boven"), VAlign.CENTER: N_("Midden"), VAlign.BOTTOM: N_("Onder")}
PICTURE_KINDS = ((PictureKind.NONE, N_("Geen")), (PictureKind.SYMBOL, N_("Symbool")),
                 (PictureKind.IMAGE, N_("Eigen afbeelding")))
SIDES = ((HAlign.LEFT, N_("Links")), (HAlign.RIGHT, N_("Rechts")))
#: Choices for the code: (kind, QR side, text)
CODE_CHOICES = (
    (CodeKind.NONE, HAlign.LEFT, N_("Geen")),
    (CodeKind.QR, HAlign.LEFT, N_("QR-code links")),
    (CodeKind.QR, HAlign.RIGHT, N_("QR-code rechts")),
    (CodeKind.CODE128, HAlign.LEFT, N_("Barcode (Code 128) i.p.v. onderregel")),
)


def _spin(lo: float, hi: float, step: float, suffix: str, decimals: int = 1) -> QDoubleSpinBox:
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


class LineEditor(QGroupBox):
    """Editor for one text slot."""

    changed = Signal()

    def __init__(self, slot: int, parent: QWidget | None = None) -> None:
        super().__init__(tr(SLOT_NAMES[slot]), parent)
        self.slot = slot
        self.setCheckable(True)
        self.text = QLineEdit()
        self.text.setPlaceholderText(tr("Tekst of {veld}…"))
        # inserts a {field} that shows a specification's value on the label
        self.fields: Callable[[], list[str]] = list
        self.field_btn = FieldButton(self.text, lambda: self.fields())
        self.field_btn.inserted.connect(self.changed)
        self.font = QComboBox()
        self.font.setEditable(True)
        self.font.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.size = _spin(3, 60, 0.5, " pt")
        self.bold = QCheckBox(tr("Vet"))
        self.italic = QCheckBox(tr("Cursief"))
        self.align = QComboBox()
        for a, t in ALIGN_TEXT.items():
            self.align.addItem(tr(t), a)
        self.fitted = QLabel()
        self.fitted.setObjectName("hint")

        form = QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        text_row = QHBoxLayout()
        text_row.setSpacing(4)
        text_row.addWidget(self.text, 1)
        text_row.addWidget(self.field_btn)
        form.addRow(tr("Tekst"), text_row)
        form.addRow(tr("Lettertype"), self.font)
        row = QHBoxLayout()
        row.addWidget(self.size)
        row.addWidget(self.bold)
        row.addWidget(self.italic)
        form.addRow(tr("Grootte"), row)
        form.addRow(tr("Uitlijning"), self.align)
        form.addRow("", self.fitted)

        self.toggled.connect(self.changed)
        self.text.textEdited.connect(self.changed)
        self.font.currentTextChanged.connect(self.changed)
        self.size.valueChanged.connect(self.changed)
        self.bold.toggled.connect(self.changed)
        self.italic.toggled.connect(self.changed)
        self.align.currentIndexChanged.connect(self.changed)

    def insert_field(self, name: str) -> None:
        self.field_btn.insert_field(name)

    def set_families(self, families: list[str]) -> None:
        cur = self.font.currentText()
        self.font.blockSignals(True)
        self.font.clear()
        self.font.addItems(families)
        self.font.setCurrentText(cur)
        self.font.blockSignals(False)


class PropertiesPanel(QScrollArea):
    """Edits the current label in place and emits :attr:`changed`."""

    changed = Signal(bool)  # True when the library list needs a rebuild (name/category)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setObjectName("inspectorScroll")
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.label: Label | None = None
        self._loading = False
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(14, 0, 14, 14)
        lay.setSpacing(2)

        gen = QGroupBox(tr("Label"))
        f = QFormLayout(gen)
        self.name = QLineEdit()
        self.tray = QLineEdit()
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.layout_combo = QComboBox()
        for preset, title in LAYOUT_TITLES.items():
            self.layout_combo.addItem(tr(title), preset)
        f.addRow(tr("Naam"), self.name)
        f.addRow(tr("Lade-ID"), self.tray)
        f.addRow(tr("Categorie"), self.category)
        f.addRow(tr("Layout"), self.layout_combo)
        hint = QLabel(tr("De lade-ID wordt niet op het etiket afgedrukt. Wisselen van layout "
                         "bewaart de tekst van alle regels."))
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        f.addRow(hint)
        lay.addWidget(gen)

        self.lines = [LineEditor(i) for i in range(3)]
        for le in self.lines:
            le.fields = lambda: self.label.field_names() if self.label else []
        for le in self.lines:
            lay.addWidget(le)
            le.changed.connect(lambda le=le: self._line_changed(le))

        code = QGroupBox(tr("QR-code of barcode"))
        fc = QFormLayout(code)
        fc.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.code_kind = QComboBox()
        for _kind, _side, text in CODE_CHOICES:
            self.code_kind.addItem(tr(text))
        self.code_text = QLineEdit()
        self.code_text.setPlaceholderText(tr("Tekst of {veld}, bv. {Lade} of een link"))
        self.code_field_btn = FieldButton(
            self.code_text, lambda: self.label.field_names() if self.label else [])
        self.code_field_btn.inserted.connect(lambda: self._apply(False))
        code_row = QHBoxLayout()
        code_row.setSpacing(4)
        code_row.addWidget(self.code_text, 1)
        code_row.addWidget(self.code_field_btn)
        self.code_hint = QLabel()
        self.code_hint.setWordWrap(True)
        self.code_hint.setObjectName("hint")
        fc.addRow(tr("Soort"), self.code_kind)
        fc.addRow(tr("Inhoud"), code_row)
        fc.addRow(self.code_hint)
        lay.addWidget(code)

        pic = QGroupBox(tr("Pictogram"))
        fp = QFormLayout(pic)
        fp.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.pic_kind = QComboBox()
        for _k, text in PICTURE_KINDS:
            self.pic_kind.addItem(tr(text))
        self.pic_side = QComboBox()
        for _s, text in SIDES:
            self.pic_side.addItem(tr(text))
        self.pic_symbol = QComboBox()
        self.pic_symbol.setIconSize(QSize(28, 28))
        for key, (name, _p) in symbols.SYMBOLS.items():
            self.pic_symbol.addItem(symbol_icon(key), tr(name), key)
        self.pic_image_btn = QPushButton(tr("Afbeelding kiezen…"))
        self.pic_image_btn.setToolTip(tr("PNG, JPG of SVG, bv. een logo. Wordt zwart-wit "
                                         "afgedrukt en in het label bewaard."))
        self.pic_image_btn.clicked.connect(self._choose_image)
        fp.addRow(tr("Soort"), self.pic_kind)
        fp.addRow(tr("Plaats"), self.pic_side)
        fp.addRow(tr("Symbool"), self.pic_symbol)
        fp.addRow(tr("Afbeelding"), self.pic_image_btn)
        lay.addWidget(pic)

        st = QGroupBox(tr("Opmaak"))
        f2 = QFormLayout(st)
        self.valign = QComboBox()
        for a, t in VALIGN_TEXT.items():
            self.valign.addItem(tr(t), a)
        self.spacing = _spin(-3, 5, 0.1, " mm")
        self.margin_h = _spin(0, 10, 0.25, " mm", 2)
        self.margin_v = _spin(0, 5, 0.25, " mm", 2)
        self.autofit = QCheckBox(tr("Tekst automatisch passend maken"))
        self.rotation = QComboBox()
        self.rotation.addItem("0°", 0)
        self.rotation.addItem(tr("90° (van onder naar boven lezen)"), 90)
        self.rotation.addItem(tr("180° (ondersteboven)"), 180)
        self.rotation.addItem(tr("270° (van boven naar onder lezen)"), 270)
        self.border = QCheckBox(tr("Rand rond printbaar gebied"))
        self.invert = QCheckBox(tr("Wit op zwart"))
        f2.addRow(tr("Verticaal"), self.valign)
        f2.addRow(tr("Regelafstand"), self.spacing)
        f2.addRow(tr("Marge horizontaal"), self.margin_h)
        f2.addRow(tr("Marge verticaal"), self.margin_v)
        f2.addRow(tr("Rotatie"), self.rotation)
        f2.addRow(self.autofit)
        f2.addRow(self.border)
        f2.addRow(self.invert)
        lay.addWidget(st)

        meta = QGroupBox(tr("Specificaties en notities"))
        f3 = QFormLayout(meta)
        self.specs = QPlainTextEdit()
        self.specs.setPlaceholderText(tr("Eén per regel, bv.\nSpanning: 50 V\nTolerantie: 10%"))
        self.specs.setFixedHeight(80)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(tr("Alleen voor jezelf, bv. waar besteld"))
        self.notes.setFixedHeight(60)
        spec_hint = QLabel(tr("Typ {Spanning} in een tekstregel (of gebruik de knop { }) om de "
                              "waarde op het etiket te tonen. Pas je de specificatie aan, dan "
                              "verandert het etiket mee. Notities komen niet op het etiket."))
        spec_hint.setWordWrap(True)
        spec_hint.setObjectName("hint")
        f3.addRow(tr("Specificaties"), self.specs)
        f3.addRow(tr("Notities"), self.notes)
        f3.addRow(spec_hint)
        lay.addWidget(meta)
        lay.addStretch(1)
        self.setWidget(body)

        self.name.textEdited.connect(lambda: self._apply(True))
        self.tray.textEdited.connect(lambda: self._apply(True))
        # The category is committed when editing is finished (Enter, leaving the
        # field or picking from the list), not on every keystroke: a half-typed
        # name must not create a category or move the label.
        self.category.lineEdit().editingFinished.connect(self._commit_category)
        self.category.activated.connect(self._commit_category)
        self.layout_combo.activated.connect(self._layout_chosen)
        for w in (self.valign, self.rotation):
            w.currentIndexChanged.connect(lambda: self._apply(False))
        for w in (self.spacing, self.margin_h, self.margin_v):
            w.valueChanged.connect(lambda: self._apply(False))
        for w in (self.autofit, self.border, self.invert):
            w.toggled.connect(lambda: self._apply(False))
        self.code_kind.currentIndexChanged.connect(lambda: self._apply(False))
        for w in (self.pic_kind, self.pic_side, self.pic_symbol):
            w.currentIndexChanged.connect(lambda: self._apply(False))
        self.code_text.textEdited.connect(lambda: self._apply(False))
        self.specs.textChanged.connect(lambda: self._apply(False))
        self.notes.textChanged.connect(lambda: self._apply(False))
        self.setEnabled(False)

    # -- loading ----------------------------------------------------------------------

    def set_families(self, families: list[str]) -> None:
        self._loading = True
        for le in self.lines:
            le.set_families(families)
        self._loading = False

    def set_categories(self, cats: list[str]) -> None:
        self._loading = True
        cur = self.category.currentText()
        self.category.clear()
        self.category.addItems(cats)
        self.category.setCurrentText(cur)
        self._loading = False

    def set_label(self, label: Label | None) -> None:
        self.label = label
        self.setEnabled(label is not None)
        if label is None:
            return
        self._loading = True
        try:
            self.name.setText(label.name)
            self.tray.setText(label.tray_id)
            self.category.setCurrentText(label.category)
            self.layout_combo.setCurrentIndex(self.layout_combo.findData(label.layout))
            for le, ln in zip(self.lines, label.lines):
                le.setChecked(ln.enabled)
                if le.text.text() != ln.text:
                    le.text.setText(ln.text)
                le.font.setCurrentText(ln.font_family)
                le.size.setValue(ln.font_size_pt)
                le.bold.setChecked(ln.bold)
                le.italic.setChecked(ln.italic)
                le.align.setCurrentIndex(le.align.findData(ln.align))
            s = label.style
            self.valign.setCurrentIndex(self.valign.findData(s.valign))
            self.spacing.setValue(s.line_spacing_mm)
            self.margin_h.setValue(s.margin_h_mm)
            self.margin_v.setValue(s.margin_v_mm)
            self.autofit.setChecked(s.autofit)
            self.rotation.setCurrentIndex(max(0, self.rotation.findData(s.rotation)))
            self.border.setChecked(s.border)
            self.invert.setChecked(s.invert)
            c = label.code
            self.code_kind.setCurrentIndex(self._code_index(c.kind, c.side))
            if self.code_text.text() != c.text:
                self.code_text.setText(c.text)
            self._update_code_hint()
            p = label.picture
            self.pic_kind.setCurrentIndex([k for k, _ in PICTURE_KINDS].index(p.kind))
            self.pic_side.setCurrentIndex(1 if p.side == HAlign.RIGHT else 0)
            self.pic_symbol.setCurrentIndex(max(0, self.pic_symbol.findData(p.symbol)))
            self._update_picture_widgets()
            specs = "\n".join(f"{k}: {v}" for k, v in label.specs.items())
            if self.specs.toPlainText() != specs:
                self.specs.setPlainText(specs)
            if self.notes.toPlainText() != label.notes:
                self.notes.setPlainText(label.notes)
        finally:
            self._loading = False

    def show_fitted_sizes(self, sizes: dict[int, tuple[float, float]]) -> None:
        """Show the auto-fit result per slot: {slot: (fitted_pt, requested_pt)}."""
        for le in self.lines:
            fitted = sizes.get(le.slot)
            if fitted and fitted[0] < fitted[1] - 0.05:
                le.fitted.setText(tr("Automatisch verkleind tot {pt} pt", pt=f"{fitted[0]:.1f}"))
            else:
                le.fitted.setText("")

    # -- applying -----------------------------------------------------------------------

    def _layout_chosen(self) -> None:
        if self._loading or self.label is None:
            return
        self.label.apply_layout(LayoutPreset(self.layout_combo.currentData()))
        self.set_label(self.label)
        self._emit(False)

    def _line_changed(self, le: LineEditor) -> None:
        if self._loading or self.label is None:
            return
        ln = self.label.lines[le.slot]
        if ln.enabled != le.isChecked():
            self.label.layout = LayoutPreset.CUSTOM
            self._loading = True
            self.layout_combo.setCurrentIndex(self.layout_combo.findData(LayoutPreset.CUSTOM))
            self._loading = False
        ln.enabled = le.isChecked()
        ln.text = le.text.text()
        if le.font.currentText().strip():
            ln.font_family = le.font.currentText().strip()
        ln.font_size_pt = le.size.value()
        ln.bold = le.bold.isChecked()
        ln.italic = le.italic.isChecked()
        ln.align = HAlign(le.align.currentData())
        self._emit(True)

    def _apply(self, structural: bool) -> None:
        if self._loading or self.label is None:
            return
        lbl = self.label
        lbl.name = self.name.text()
        lbl.tray_id = self.tray.text().strip()
        s = lbl.style
        s.valign = VAlign(self.valign.currentData())
        s.line_spacing_mm = self.spacing.value()
        s.margin_h_mm = self.margin_h.value()
        s.margin_v_mm = self.margin_v.value()
        s.autofit = self.autofit.isChecked()
        s.rotation = int(self.rotation.currentData() or 0)
        s.border = self.border.isChecked()
        s.invert = self.invert.isChecked()
        kind, side, _ = CODE_CHOICES[max(0, self.code_kind.currentIndex())]
        lbl.code.kind, lbl.code.side = kind, side
        lbl.code.text = self.code_text.text()
        self._update_code_hint()
        lbl.picture.kind = PICTURE_KINDS[max(0, self.pic_kind.currentIndex())][0]
        lbl.picture.side = SIDES[max(0, self.pic_side.currentIndex())][0]
        lbl.picture.symbol = self.pic_symbol.currentData() or lbl.picture.symbol
        self._update_picture_widgets()
        specs: dict[str, str] = {}
        for line in self.specs.toPlainText().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip():
                    specs[k.strip()] = v.strip()
            elif line.strip():
                specs[line.strip()] = ""
        lbl.specs = specs
        lbl.notes = self.notes.toPlainText()
        self._emit(structural)

    def _update_picture_widgets(self) -> None:
        kind = PICTURE_KINDS[max(0, self.pic_kind.currentIndex())][0]
        self.pic_side.setEnabled(kind != PictureKind.NONE)
        self.pic_symbol.setEnabled(kind == PictureKind.SYMBOL)
        self.pic_image_btn.setEnabled(kind == PictureKind.IMAGE)
        has = bool(self.label and self.label.picture.image_png)
        self.pic_image_btn.setText(tr("Andere afbeelding…") if has else tr("Afbeelding kiezen…"))

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Afbeelding kiezen"), "",
            tr("Afbeeldingen") + " (*.png *.jpg *.jpeg *.gif *.bmp *.tif *.tiff *.svg)")
        if path:
            self.set_image_file(Path(path))

    def set_image_file(self, path: Path) -> bool:
        """Put the image in *path* on the current label.  False when it cannot be read."""
        if self.label is None:
            return False
        try:
            data = load_image(path)
        except pictures.ImageError:
            QMessageBox.warning(self, tr("Afbeelding"), tr(
                "'{name}' kon niet worden gelezen als afbeelding.", name=path.name))
            return False
        self.label.picture.image_png = data
        self.label.picture.kind = PictureKind.IMAGE
        self._loading = True
        self.pic_kind.setCurrentIndex([k for k, _ in PICTURE_KINDS].index(PictureKind.IMAGE))
        self._loading = False
        self._update_picture_widgets()
        self._emit(False)
        return True

    @staticmethod
    def _code_index(kind: CodeKind, side: HAlign) -> int:
        for i, (k, sd, _) in enumerate(CODE_CHOICES):
            if k == kind and (k != CodeKind.QR or sd == side):
                return i
        return 0

    def _update_code_hint(self) -> None:
        kind = CODE_CHOICES[max(0, self.code_kind.currentIndex())][0]
        self.code_text.setEnabled(kind != CodeKind.NONE)
        self.code_field_btn.setEnabled(kind != CodeKind.NONE)
        bottom = self.lines[SLOT_BOTTOM]
        if kind == CodeKind.CODE128:
            bottom.setTitle(tr("{slot} (vervangen door barcode)", slot=tr(SLOT_NAMES[SLOT_BOTTOM])))
        else:
            bottom.setTitle(tr(SLOT_NAMES[SLOT_BOTTOM]))
        self.code_hint.setText({
            CodeKind.NONE: "",
            CodeKind.QR: tr("Scan met je telefoon. Korte tekst geeft grotere blokjes die "
                            "makkelijker scannen; een link past tot ongeveer 40 tekens goed."),
            CodeKind.CODE128: tr("Voor een handscanner. Komt op de plaats van de onderregel; "
                                 "die tekst blijft bewaard. Past tot ongeveer 15 tekens "
                                 "(cijfers het dubbele); korter geeft dikkere streepjes. "
                                 "Alleen letters, cijfers en leestekens zonder accenten."),
        }[kind])

    def _commit_category(self) -> None:
        if self._loading or self.label is None:
            return
        cat = self.category.currentText().strip()
        if cat != self.label.category:
            self.label.category = cat
            self._emit(True)

    def _emit(self, structural: bool) -> None:
        if self.label is not None:
            self.label.touch()
        self.changed.emit(structural)

