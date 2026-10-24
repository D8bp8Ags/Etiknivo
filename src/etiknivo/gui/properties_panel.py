"""Right panel: label properties."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from etiknivo.model import (
    LAYOUT_TITLES,
    SLOT_NAMES,
    HAlign,
    Label,
    LayoutPreset,
    VAlign,
)

ALIGN_TEXT = {HAlign.LEFT: "Links", HAlign.CENTER: "Midden", HAlign.RIGHT: "Rechts"}
VALIGN_TEXT = {VAlign.TOP: "Boven", VAlign.CENTER: "Midden", VAlign.BOTTOM: "Onder"}


def _spin(lo: float, hi: float, step: float, suffix: str, decimals: int = 1) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


class LineEditor(QGroupBox):
    """Editor for one text slot."""

    changed = Signal()

    def __init__(self, slot: int, parent: QWidget | None = None) -> None:
        super().__init__(SLOT_NAMES[slot], parent)
        self.slot = slot
        self.setCheckable(True)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Tekst…")
        self.font = QComboBox()
        self.font.setEditable(True)
        self.font.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.size = _spin(3, 60, 0.5, " pt")
        self.bold = QCheckBox("Vet")
        self.italic = QCheckBox("Cursief")
        self.align = QComboBox()
        for a, t in ALIGN_TEXT.items():
            self.align.addItem(t, a)
        self.fitted = QLabel()
        self.fitted.setObjectName("hint")

        form = QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow("Tekst", self.text)
        form.addRow("Lettertype", self.font)
        row = QHBoxLayout()
        row.addWidget(self.size)
        row.addWidget(self.bold)
        row.addWidget(self.italic)
        form.addRow("Grootte", row)
        form.addRow("Uitlijning", self.align)
        form.addRow("", self.fitted)

        self.toggled.connect(self.changed)
        self.text.textEdited.connect(self.changed)
        self.font.currentTextChanged.connect(self.changed)
        self.size.valueChanged.connect(self.changed)
        self.bold.toggled.connect(self.changed)
        self.italic.toggled.connect(self.changed)
        self.align.currentIndexChanged.connect(self.changed)

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

        gen = QGroupBox("Label")
        f = QFormLayout(gen)
        self.name = QLineEdit()
        self.tray = QLineEdit()
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.layout_combo = QComboBox()
        for preset, title in LAYOUT_TITLES.items():
            self.layout_combo.addItem(title, preset)
        f.addRow("Naam", self.name)
        f.addRow("Lade-ID", self.tray)
        f.addRow("Categorie", self.category)
        f.addRow("Layout", self.layout_combo)
        hint = QLabel("De lade-ID wordt niet op het etiket afgedrukt. Wisselen van layout "
                      "bewaart de tekst van alle regels.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        f.addRow(hint)
        lay.addWidget(gen)

        self.lines = [LineEditor(i) for i in range(3)]
        for le in self.lines:
            lay.addWidget(le)
            le.changed.connect(lambda le=le: self._line_changed(le))

        st = QGroupBox("Opmaak")
        f2 = QFormLayout(st)
        self.valign = QComboBox()
        for a, t in VALIGN_TEXT.items():
            self.valign.addItem(t, a)
        self.spacing = _spin(-3, 5, 0.1, " mm")
        self.margin_h = _spin(0, 10, 0.25, " mm", 2)
        self.margin_v = _spin(0, 5, 0.25, " mm", 2)
        self.autofit = QCheckBox("Tekst automatisch passend maken")
        self.rotation = QComboBox()
        self.rotation.addItem("0°", 0)
        self.rotation.addItem("180° (ondersteboven)", 180)
        self.border = QCheckBox("Rand rond printbaar gebied")
        self.invert = QCheckBox("Wit op zwart")
        f2.addRow("Verticaal", self.valign)
        f2.addRow("Regelafstand", self.spacing)
        f2.addRow("Marge horizontaal", self.margin_h)
        f2.addRow("Marge verticaal", self.margin_v)
        f2.addRow("Rotatie", self.rotation)
        f2.addRow(self.autofit)
        f2.addRow(self.border)
        f2.addRow(self.invert)
        lay.addWidget(st)

        meta = QGroupBox("Specificaties en notities")
        f3 = QFormLayout(meta)
        self.specs = QPlainTextEdit()
        self.specs.setPlaceholderText("Eén per regel, bv.\nSpanning: 50 V\nTolerantie: 10%")
        self.specs.setFixedHeight(70)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(60)
        f3.addRow("Technisch", self.specs)
        f3.addRow("Notities", self.notes)
        lay.addWidget(meta)
        lay.addStretch(1)
        self.setWidget(body)

        self.name.textEdited.connect(lambda: self._apply(True))
        self.tray.textEdited.connect(lambda: self._apply(True))
        self.category.currentTextChanged.connect(lambda: self._apply(True))
        self.layout_combo.activated.connect(self._layout_chosen)
        for w in (self.valign, self.rotation):
            w.currentIndexChanged.connect(lambda: self._apply(False))
        for w in (self.spacing, self.margin_h, self.margin_v):
            w.valueChanged.connect(lambda: self._apply(False))
        for w in (self.autofit, self.border, self.invert):
            w.toggled.connect(lambda: self._apply(False))
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
                le.fitted.setText(f"Automatisch verkleind tot {fitted[0]:.1f} pt")
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
        lbl.category = self.category.currentText().strip()
        s = lbl.style
        s.valign = VAlign(self.valign.currentData())
        s.line_spacing_mm = self.spacing.value()
        s.margin_h_mm = self.margin_h.value()
        s.margin_v_mm = self.margin_v.value()
        s.autofit = self.autofit.isChecked()
        s.rotation = int(self.rotation.currentData() or 0)
        s.border = self.border.isChecked()
        s.invert = self.invert.isChecked()
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

    def _emit(self, structural: bool) -> None:
        if self.label is not None:
            self.label.touch()
        self.changed.emit(structural)

