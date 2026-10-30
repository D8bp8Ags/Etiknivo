"""Right panel: label properties."""

from __future__ import annotations

import html
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui import theme
from etiknivo.gui.element_panel import ElementPanel
from etiknivo.gui.notes_edit import NotesEdit, find_links
from etiknivo.gui.specs_editor import SpecsEditor
from etiknivo.gui.widgets import (
    ALIGN_TEXT,
    FieldButton,
    combo,
    load_image,
    segmented,
    select_symbol,
    spin,
    style_row,
    symbol_combo,
)
from etiknivo.i18n import N_, tr
from etiknivo.model import (
    FIELD_RE,
    LINE_COUNT_PRESETS,
    SLOT_NAMES,
    CodeKind,
    CodeSize,
    HAlign,
    Label,
    LayoutPreset,
    PictureKind,
    VAlign,
)
from etiknivo.rendering import pictures
from etiknivo.settings import data_dir

VALIGN_TEXT = {VAlign.TOP: N_("Boven"), VAlign.CENTER: N_("Midden"), VAlign.BOTTOM: N_("Onder")}
PICTURE_KINDS = ((PictureKind.NONE, N_("Geen")), (PictureKind.SYMBOL, N_("Symbool")),
                 (PictureKind.IMAGE, N_("Eigen afbeelding")))
#: Where a QR code or pictogram goes beside the text: (side, height, text)
POSITIONS = (
    (HAlign.LEFT, VAlign.TOP, N_("Links boven")),
    (HAlign.LEFT, VAlign.CENTER, N_("Links midden")),
    (HAlign.LEFT, VAlign.BOTTOM, N_("Links onder")),
    (HAlign.RIGHT, VAlign.TOP, N_("Rechts boven")),
    (HAlign.RIGHT, VAlign.CENTER, N_("Rechts midden")),
    (HAlign.RIGHT, VAlign.BOTTOM, N_("Rechts onder")),
)
#: How big a QR code or pictogram may get
SIZES = ((CodeSize.SMALL, N_("Klein")), (CodeSize.MEDIUM, N_("Middel")),
         (CodeSize.LARGE, N_("Groot")))
#: Choices for the code: (kind, text)
CODE_CHOICES = (
    (CodeKind.NONE, N_("Geen")),
    (CodeKind.QR, N_("QR-code")),
    (CodeKind.CODE128, N_("Barcode (Code 128) onderaan")),
)


def position_combo() -> QComboBox:
    box = combo()
    for _side, _valign, text in POSITIONS:
        box.addItem(tr(text))
    return box


def set_position(box: QComboBox, side: HAlign, valign: VAlign) -> None:
    box.setCurrentIndex(next((i for i, (sd, va, _t) in enumerate(POSITIONS)
                              if (sd, va) == (side, valign)), 1))


def chosen_position(box: QComboBox) -> tuple[HAlign, VAlign]:
    side, valign, _t = POSITIONS[max(0, box.currentIndex())]
    return side, valign


def set_size(buttons: list[QToolButton], size: CodeSize) -> None:
    buttons[[sz for sz, _t in SIZES].index(size)].setChecked(True)


def chosen_size(buttons: list[QToolButton]) -> CodeSize:
    return next(sz for (sz, _t), b in zip(SIZES, buttons) if b.isChecked())


class LineEditor(QWidget):
    """Editor for one text slot: one row with the text, and its font, size,
    style and alignment folded away behind a button."""

    changed = Signal()
    toggled = Signal(bool)

    def __init__(self, slot: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.slot = slot
        self.check = QCheckBox(tr(SLOT_NAMES[slot]))
        self.text = QLineEdit()
        self.text.setPlaceholderText(tr("Tekst of {veld}…"))
        # inserts a {field} that shows a specification's value on the label
        self.fields: Callable[[], list[str]] = list
        self.field_btn = FieldButton(self.text, lambda: self.fields())
        self.field_btn.inserted.connect(self.changed)
        self.more = QToolButton()
        self.more.setCheckable(True)
        self.more.setIcon(theme.icon("sliders-horizontal"))
        self.font = combo()
        self.font.setEditable(True)
        self.font.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.size = spin(3, 60, 0.5, " pt")
        self.bold = QCheckBox(tr("Vet"))
        self.italic = QCheckBox(tr("Cursief"))
        self.align = combo()
        for a, t in ALIGN_TEXT.items():
            self.align.addItem(tr(t), a)
        self.fitted = QLabel()
        self.fitted.setObjectName("hint")
        self.note = QLabel()
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        self.note.hide()

        self.details = QWidget()
        form = QFormLayout(self.details)
        form.setContentsMargins(24, 2, 0, 8)  # indented under its line
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow(tr("Lettertype"), self.font)
        form.addRow(tr("Grootte"), self.size)
        form.addRow(tr("Stijl"), style_row(self.bold, self.italic))
        form.addRow(tr("Uitlijning"), self.align)
        self.details.hide()

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self.text, 1)
        row.addWidget(self.field_btn)
        row.addWidget(self.more)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)
        grid.addWidget(self.check, 0, 0)
        grid.addLayout(row, 0, 1)
        grid.addWidget(self.fitted, 1, 1)
        grid.addWidget(self.note, 2, 1)
        grid.addWidget(self.details, 3, 0, 1, 2)
        grid.setColumnStretch(1, 1)
        self.fitted.hide()

        self.more.toggled.connect(self.details.setVisible)
        self.check.toggled.connect(self._enable)
        self.check.toggled.connect(self.toggled)
        self.check.toggled.connect(self.changed)
        self.text.textEdited.connect(self.changed)
        self.font.currentTextChanged.connect(self.changed)
        self.size.valueChanged.connect(self.changed)
        self.bold.toggled.connect(self.changed)
        self.italic.toggled.connect(self.changed)
        self.align.currentIndexChanged.connect(self.changed)
        self.changed.connect(self._describe)
        self._enable(False)

    def title(self) -> str:
        return self.check.text()

    def isChecked(self) -> bool:  # noqa: N802 - same API as a checkable group box
        return self.check.isChecked()

    def setChecked(self, on: bool) -> None:  # noqa: N802
        self.check.setChecked(on)
        self._enable(on)

    def set_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def set_fitted(self, text: str) -> None:
        self.fitted.setText(text)
        self.fitted.setVisible(bool(text))

    def _enable(self, on: bool) -> None:
        for w in (self.text, self.field_btn, self.more, self.details):
            w.setEnabled(on)
        self._describe()

    def _describe(self) -> None:
        """The folded settings in the button's tooltip."""
        parts = [self.font.currentText(), f"{self.size.value():g} pt"]
        parts += [tr("vet")] * self.bold.isChecked() + [tr("cursief")] * self.italic.isChecked()
        parts.append(self.align.currentText().lower())
        self.more.setToolTip(tr("Lettertype, grootte, stijl en uitlijning") + "\n"
                             + " · ".join(p for p in parts if p))

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
    elementSelected = Signal(str)  # free layout: element id, "" for none

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        # never scroll sideways: the fields get narrower instead
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName("inspectorScroll")
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.label: Label | None = None
        self._loading = False
        #: size of the printable area in mm (new elements are placed in it)
        self.area_mm: Callable[[], tuple[float, float]] = lambda: (26.0, 12.0)
        #: turns a label's lines, code and picture into loose elements
        self.make_elements: Callable[[Label], list] | None = None
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(14, 0, 14, 14)
        lay.setSpacing(2)

        gen = self.label_section = CollapsibleSection(tr("Label"), "sec_label")
        f = QFormLayout(gen.body)
        self.name = QLineEdit()
        self.tray = QLineEdit()
        self.category = combo()
        self.category.setEditable(True)
        self.category.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        # Two ways of working: three text lines, or loose elements to drag.
        mode, (self.mode_lines, self.mode_free) = segmented([tr("Regels"), tr("Vrij")])
        self.mode_lines.setToolTip(tr("Tot drie tekstregels onder elkaar, met een QR-code of "
                                      "barcode en een pictogram ernaast"))
        self.mode_free.setToolTip(tr("Losse elementen die je in het ontwerp versleept en "
                                     "schaalt"))
        counts, self.count_buttons = segmented(["1", "2", "3"], exclusive=False)
        for n, (btn, tip) in enumerate(zip(self.count_buttons, (
                tr("Alleen de hoofdregel"), tr("Hoofdregel en onderregel"),
                tr("Bovenregel, hoofdregel en onderregel"))), start=1):
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _c=False, n=n: self._count_chosen(n))
        f.addRow(tr("Naam"), self.name)
        f.addRow(tr("Lade-ID"), self.tray)
        f.addRow(tr("Categorie"), self.category)
        f.addRow(tr("Layout"), mode)
        f.addRow(tr("Regels"), counts)
        self._label_form = f
        self._counts_row = counts
        self.layout_hint = QLabel()
        self.layout_hint.setWordWrap(True)
        self.layout_hint.setObjectName("hint")
        f.addRow(self.layout_hint)
        lay.addWidget(gen)

        self.elements = ElementPanel(lambda: self.area_mm())
        self.elements.changed.connect(lambda: self._emit(False))
        self.elements.selected.connect(self.elementSelected)
        lay.addWidget(self.elements)

        self.text_section = CollapsibleSection(tr("Tekst"), "sec_text")
        text_lay = QVBoxLayout(self.text_section.body)
        text_lay.setContentsMargins(0, 4, 0, 4)
        text_lay.setSpacing(6)
        self.lines = [LineEditor(i) for i in range(3)]
        for le in self.lines:
            le.fields = lambda: self.label.field_names() if self.label else []
            text_lay.addWidget(le)
            le.changed.connect(lambda le=le: self._line_changed(le))
        lay.addWidget(self.text_section)

        code = self.code_group = CollapsibleSection(tr("QR-code of barcode"), "sec_code")
        fc = QFormLayout(code.body)
        fc.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.code_kind = combo()
        for _kind, text in CODE_CHOICES:
            self.code_kind.addItem(tr(text))
        self.code_pos = position_combo()
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
        size_box, self.code_sizes = segmented([tr(t) for _s, t in SIZES])
        size_box.setToolTip(tr("Hoe groot de QR-code naast de tekst mag worden. Kleiner laat "
                               "meer ruimte voor tekst; groter scant makkelijker."))
        self._code_size_box = size_box
        fc.addRow(tr("Soort"), self.code_kind)
        fc.addRow(tr("Plaats"), self.code_pos)
        fc.addRow(tr("Grootte"), size_box)
        fc.addRow(tr("Inhoud"), code_row)
        fc.addRow(self.code_hint)
        self._code_form, self._code_row = fc, code_row
        lay.addWidget(code)

        pic = self.pic_group = CollapsibleSection(tr("Pictogram"), "sec_picture")
        fp = QFormLayout(pic.body)
        fp.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.pic_kind = combo()
        for _k, text in PICTURE_KINDS:
            self.pic_kind.addItem(tr(text))
        self.pic_pos = position_combo()
        pic_size_box, self.pic_sizes = segmented([tr(t) for _s, t in SIZES])
        pic_size_box.setToolTip(tr("Hoe groot het pictogram naast de tekst mag worden. Kleiner "
                                   "laat meer ruimte voor tekst."))
        self._pic_size_box = pic_size_box
        self.pic_symbol = symbol_combo()
        self.pic_image_btn = QPushButton(tr("Afbeelding kiezen…"))
        self.pic_image_btn.setToolTip(tr("PNG, JPG of SVG, bv. een logo. Wordt zwart-wit "
                                         "afgedrukt en in het label bewaard."))
        self.pic_image_btn.clicked.connect(self._choose_image)
        fp.addRow(tr("Soort"), self.pic_kind)
        fp.addRow(tr("Plaats"), self.pic_pos)
        fp.addRow(tr("Grootte"), pic_size_box)
        fp.addRow(tr("Symbool"), self.pic_symbol)
        fp.addRow(tr("Afbeelding"), self.pic_image_btn)
        self._pic_form = fp
        lay.addWidget(pic)

        meta = self.meta_section = CollapsibleSection(tr("Specificaties en notities"),
                                                      "sec_meta")
        f3 = QFormLayout(meta.body)
        f3.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.specs = SpecsEditor()
        self.specs.targets = self._field_targets
        spec_hint = QLabel(tr("Een specificatie heeft een naam en een waarde, bv. Spanning en "
                              "50 V. Zet {Spanning} in een tekstregel (of gebruik de knop { } "
                              "achter de specificatie) om de waarde op het etiket te tonen. Pas "
                              "je de waarde aan, dan verandert het etiket mee."))
        spec_hint.setWordWrap(True)
        spec_hint.setObjectName("hint")
        self.notes = NotesEdit()
        self.notes.setPlaceholderText(tr("Alleen voor jezelf, bv. waar besteld of een link "
                                         "naar de winkel. Komt niet op het etiket."))
        # the links in the notes, one click away
        self.notes_links = QLabel()
        self.notes_links.setObjectName("hint")
        self.notes_links.setWordWrap(True)
        self.notes_links.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.notes_links.linkActivated.connect(self.notes.open_link)
        self.notes_links.hide()
        self.notes_hint = QLabel(tr("Notities komen niet op het etiket, dus een {veld} wordt "
                                    "hier niet ingevuld. Zet het in een tekstregel."))
        self.notes_hint.setWordWrap(True)
        self.notes_hint.setObjectName("warnHint")
        self.notes_hint.hide()
        f3.addRow(tr("Specificaties"), self.specs)
        f3.addRow(spec_hint)
        f3.addRow(QLabel(tr("Notities")))
        f3.addRow(self.notes)
        f3.addRow(self.notes_links)
        f3.addRow(self.notes_hint)
        lay.addWidget(meta)

        # Style is set once per category and then copied, so it sits last and
        # folds away; whether it is open is remembered.
        self.style_section = st = CollapsibleSection(tr("Opmaak"), "style_open")
        f2 = QFormLayout(st.body)
        self.valign = combo()
        for a, t in VALIGN_TEXT.items():
            self.valign.addItem(tr(t), a)
        self.spacing = spin(-3, 5, 0.1, " mm")
        self.margin_h = spin(0, 10, 0.25, " mm", 2)
        self.margin_v = spin(0, 5, 0.25, " mm", 2)
        self.autofit = QCheckBox(tr("Tekst automatisch passend maken"))
        self.rotation = combo()
        self.rotation.addItem("0°", 0)
        self.rotation.addItem(tr("90° (van onder naar boven lezen)"), 90)
        self.rotation.addItem(tr("180° (ondersteboven)"), 180)
        self.rotation.addItem(tr("270° (van boven naar onder lezen)"), 270)
        self.border = QCheckBox(tr("Rand rond printbaar gebied"))
        self.separators = QCheckBox(tr("Lijn tussen tekstregels"))
        self.invert = QCheckBox(tr("Wit op zwart"))
        f2.addRow(tr("Verticaal"), self.valign)
        f2.addRow(tr("Regelafstand"), self.spacing)
        f2.addRow(tr("Marge horizontaal"), self.margin_h)
        f2.addRow(tr("Marge verticaal"), self.margin_v)
        f2.addRow(tr("Rotatie"), self.rotation)
        f2.addRow(self.autofit)
        f2.addRow(self.border)
        f2.addRow(self.separators)
        f2.addRow(self.invert)
        self._style_form = f2
        lay.addWidget(st)

        lay.addStretch(1)
        self.setWidget(body)

        self.name.textEdited.connect(lambda: self._apply(True))
        self.tray.textEdited.connect(lambda: self._apply(True))
        # The category is committed when editing is finished (Enter, leaving the
        # field or picking from the list), not on every keystroke: a half-typed
        # name must not create a category or move the label.
        self.category.lineEdit().editingFinished.connect(self._commit_category)
        self.category.activated.connect(self._commit_category)
        self.mode_lines.clicked.connect(lambda: self._mode_chosen(free=False))
        self.mode_free.clicked.connect(lambda: self._mode_chosen(free=True))
        for w in (self.valign, self.rotation):
            w.currentIndexChanged.connect(lambda: self._apply(False))
        for w in (self.spacing, self.margin_h, self.margin_v):
            w.valueChanged.connect(lambda: self._apply(False))
        for w in (self.autofit, self.border, self.separators, self.invert):
            w.toggled.connect(lambda: self._apply(False))
        for w in (self.code_kind, self.code_pos):
            w.currentIndexChanged.connect(lambda: self._apply(False))
        for b in self.code_sizes + self.pic_sizes:
            b.clicked.connect(lambda _c=False: self._apply(False))
        for w in (self.pic_kind, self.pic_pos, self.pic_symbol):
            w.currentIndexChanged.connect(lambda: self._apply(False))
        self.code_text.textEdited.connect(lambda: self._apply(False))
        self.specs.changed.connect(lambda: self._apply(False))
        self.notes.textChanged.connect(lambda: self._apply(False))
        self.setEnabled(False)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        # as narrow as the fields allow, plus room for the vertical scroll bar
        hint = super().minimumSizeHint()
        body = self.widget().minimumSizeHint().width() if self.widget() else 0
        return QSize(max(hint.width(), body + self.verticalScrollBar().sizeHint().width()),
                     hint.height())

    # -- loading ----------------------------------------------------------------------

    def set_families(self, families: list[str]) -> None:
        self._loading = True
        for le in self.lines:
            le.set_families(families)
        self.elements.set_families(families)
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
            self.mode_free.setChecked(label.is_free)
            self.mode_lines.setChecked(not label.is_free)
            self._show_count()
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
            self.separators.setChecked(s.separators)
            self.invert.setChecked(s.invert)
            c = label.code
            self.code_kind.setCurrentIndex(self._code_index(c.kind))
            set_position(self.code_pos, c.side, c.valign)
            set_size(self.code_sizes, c.size)
            if self.code_text.text() != c.text:
                self.code_text.setText(c.text)
            self._update_code_hint()
            p = label.picture
            self.pic_kind.setCurrentIndex([k for k, _ in PICTURE_KINDS].index(p.kind))
            set_position(self.pic_pos, p.side, p.valign)
            set_size(self.pic_sizes, p.size)
            select_symbol(self.pic_symbol, p.symbol)
            self._update_picture_widgets()
            self.specs.set_specs(label.specs)
            if self.notes.toPlainText() != label.notes:
                self.notes.setPlainText(label.notes)
            self.notes_hint.setVisible(bool(FIELD_RE.search(label.notes)))
            self._update_links(label.notes)
            self.elements.set_label(label)
        finally:
            self._loading = False
        self._update_mode()
        self._update_summaries()

    def _field_targets(self) -> list[tuple[str, Callable[[str], None] | None]]:
        """Where the { } button of a specification can put its field."""
        if self.label is not None and self.label.is_free:
            el = self.elements.current()
            ok = el is not None and el.has_text
            return [(tr("het geselecteerde element"),
                     self.elements.field_btn.insert_field if ok else None)]
        return [(tr(SLOT_NAMES[le.slot]).lower(), le.insert_field) for le in self.lines]

    def _update_mode(self) -> None:
        """The free layout edits elements; the others the three lines."""
        free = self.label is not None and self.label.is_free
        self.elements.setVisible(free)
        self._label_form.setRowVisible(self._counts_row, not free)
        self.layout_hint.setText(
            tr("De lade-ID komt alleen op het etiket als een element {Lade} bevat. De "
               "elementen staan los van de regels: wat je hier verandert, komt daar niet "
               "terug.") if free else
            tr("De lade-ID komt alleen op het etiket als een regel {Lade} bevat. Met 1, 2 of "
               "3 zet je regels aan of uit; hun tekst en opmaak blijven bewaard."))
        for w in (self.text_section, self.code_group, self.pic_group):
            w.setVisible(not free)
        for w in (self.valign, self.spacing, self.margin_h, self.margin_v, self.rotation,
                  self.autofit, self.separators):
            self._style_form.setRowVisible(w, not free)

    def show_fitted_sizes(self, sizes: dict[int, tuple[float, float]]) -> None:
        """Show the auto-fit result per slot: {slot: (fitted_pt, requested_pt)};
        in the free layout the slot is the element's index."""
        if self.label is not None and self.label.is_free:
            el = self.elements.current()
            idx = self.label.elements.index(el) if el is not None else -1
            self.elements.show_fitted(sizes[idx][0] if idx in sizes else None)
            return
        for le in self.lines:
            fitted = sizes.get(le.slot)
            if fitted and fitted[0] < fitted[1] - 0.05:
                le.set_fitted(tr("Automatisch verkleind tot {pt} pt", pt=f"{fitted[0]:.1f}"))
            else:
                le.set_fitted("")

    # -- applying -----------------------------------------------------------------------

    def _mode_chosen(self, free: bool) -> None:
        """Switch between the three lines and loose elements."""
        lbl = self.label
        if self._loading or lbl is None or free == lbl.is_free:
            self.set_label(lbl)
            return
        if free:
            if self.make_elements and (not lbl.elements or (
                    lbl.elements_from not in ("", lbl.lines_key()) and self._ask_rebuild())):
                lbl.elements = self.make_elements(lbl)
                lbl.elements_from = lbl.lines_key()
            lbl.layout = LayoutPreset.FREE
        else:
            count = lbl.line_count()
            lbl.layout = LINE_COUNT_PRESETS[count] if count else LayoutPreset.CUSTOM
        self.set_label(lbl)
        self._emit(False)

    def _ask_rebuild(self) -> bool:
        """The lines changed since the elements were made: start again from
        the lines (True) or keep the earlier free layout (False)?"""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr("Vrije layout"))
        box.setText(tr("De regels zijn veranderd sinds je de vrije layout maakte."))
        box.setInformativeText(tr("Wil je de elementen opnieuw maken uit de regels, of je "
                                  "vorige vrije layout houden?"))
        again = box.addButton(tr("Opnieuw maken"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("Vorige houden"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is again

    def _count_chosen(self, count: int) -> None:
        """Quick choice of 1, 2 or 3 lines; the lines keep their look."""
        if self._loading or self.label is None:
            return
        self.label.show_lines(count)
        self.set_label(self.label)
        self._emit(False)

    def _show_count(self) -> None:
        count = self.label.line_count() if self.label is not None else None
        for n, btn in enumerate(self.count_buttons, start=1):
            btn.setChecked(n == count)

    def _line_changed(self, le: LineEditor) -> None:
        if self._loading or self.label is None:
            return
        ln = self.label.lines[le.slot]
        toggled = ln.enabled != le.isChecked()
        ln.enabled = le.isChecked()
        if toggled:
            count = self.label.line_count()
            self.label.layout = LINE_COUNT_PRESETS[count] if count else LayoutPreset.CUSTOM
            self._show_count()
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
        s.separators = self.separators.isChecked()
        s.invert = self.invert.isChecked()
        lbl.code.kind = CODE_CHOICES[max(0, self.code_kind.currentIndex())][0]
        if lbl.code.kind == CodeKind.QR:  # a barcode keeps the QR code's place for later
            lbl.code.side, lbl.code.valign = chosen_position(self.code_pos)
            lbl.code.size = chosen_size(self.code_sizes)
        lbl.code.text = self.code_text.text()
        self._update_code_hint()
        lbl.picture.kind = PICTURE_KINDS[max(0, self.pic_kind.currentIndex())][0]
        lbl.picture.side, lbl.picture.valign = chosen_position(self.pic_pos)
        lbl.picture.size = chosen_size(self.pic_sizes)
        lbl.picture.symbol = self.pic_symbol.currentData() or lbl.picture.symbol
        self._update_picture_widgets()
        lbl.specs = self.specs.specs()
        lbl.notes = self.notes.toPlainText()
        self.notes_hint.setVisible(bool(FIELD_RE.search(lbl.notes)))
        self._update_links(lbl.notes)
        self._emit(structural)

    def _update_picture_widgets(self) -> None:
        kind = PICTURE_KINDS[max(0, self.pic_kind.currentIndex())][0]
        self.pic_pos.setEnabled(kind != PictureKind.NONE)
        self.pic_symbol.setEnabled(kind == PictureKind.SYMBOL)
        self.pic_image_btn.setEnabled(kind == PictureKind.IMAGE)
        # only the rows that matter for the chosen kind
        self._pic_form.setRowVisible(self.pic_pos, kind != PictureKind.NONE)
        self._pic_form.setRowVisible(self._pic_size_box, kind != PictureKind.NONE)
        self._pic_form.setRowVisible(self.pic_symbol, kind == PictureKind.SYMBOL)
        self._pic_form.setRowVisible(self.pic_image_btn, kind == PictureKind.IMAGE)
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
    def _code_index(kind: CodeKind) -> int:
        return next((i for i, (k, _) in enumerate(CODE_CHOICES) if k == kind), 0)

    def _update_links(self, notes: str) -> None:
        links = find_links(notes)
        self.notes_links.setVisible(bool(links))
        if not links:
            return
        shown = []
        for link in links:
            short = link.split("://", 1)[-1].removeprefix("www.").rstrip("/")
            short = short if len(short) <= 38 else short[:37] + "…"
            shown.append(f'<a href="{html.escape(link)}">{html.escape(short)}</a>')
        # one link per line, each opened with one click
        self.notes_links.setText(tr("Openen:") + "<br>" + "<br>".join("↗ " + x for x in shown))
        self.notes_links.setToolTip("\n".join(links))

    def _update_code_hint(self) -> None:
        kind = CODE_CHOICES[max(0, self.code_kind.currentIndex())][0]
        self.code_text.setEnabled(kind != CodeKind.NONE)
        self.code_field_btn.setEnabled(kind != CodeKind.NONE)
        self._code_form.setRowVisible(self._code_row, kind != CodeKind.NONE)
        self._code_form.setRowVisible(self.code_pos, kind == CodeKind.QR)
        self._code_form.setRowVisible(self._code_size_box, kind == CodeKind.QR)
        self.code_hint.setText({
            CodeKind.NONE: "",
            CodeKind.QR: tr("Scan met je telefoon. Korte tekst geeft grotere blokjes die "
                            "makkelijker scannen; een link past tot ongeveer 40 tekens goed."),
            CodeKind.CODE128: tr("Voor een handscanner. Komt onderaan, onder de tekst; met "
                                 "minder regels (1 of 2) wordt de tekst groter. Past tot "
                                 "ongeveer 15 tekens "
                                 "(cijfers het dubbele); korter geeft dikkere streepjes. "
                                 "Alleen letters, cijfers en leestekens zonder accenten."),
        }[kind])
        self._code_form.setRowVisible(self.code_hint, bool(self.code_hint.text()))

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
            self._update_summaries()
        self.changed.emit(structural)

    def _update_summaries(self) -> None:
        """One line per section, shown in its title while it is closed."""
        lbl = self.label
        if lbl is None:
            return
        self.label_section.set_summary(" · ".join(x for x in (lbl.tray_id, lbl.category) if x))
        self.text_section.set_summary(" / ".join(ln.text for ln in lbl.lines
                                                 if ln.enabled and ln.text))
        code = self.code_kind.currentText()
        if lbl.code.kind == CodeKind.QR:
            code += " · " + self.code_pos.currentText().lower()
        if lbl.code.kind != CodeKind.NONE and lbl.code.text:
            code += f" · {lbl.code.text}"
        self.code_group.set_summary(code)
        pic = self.pic_kind.currentText()
        if lbl.picture.kind == PictureKind.SYMBOL:
            pic = self.pic_symbol.currentText().strip()
        if lbl.picture.kind != PictureKind.NONE:
            pic += " · " + self.pic_pos.currentText().lower()
        self.pic_group.set_summary(pic)
        meta = [tr("{n} specificaties", n=len(lbl.specs))] if lbl.specs else []
        meta += [tr("notities")] if lbl.notes.strip() else []
        self.meta_section.set_summary(" · ".join(meta))


SUMMARY_CHARS = 26


class CollapsibleSection(QWidget):
    """A section with a title that folds its body away, like a group box
    that can be closed.  Open or closed is remembered under *key*."""

    def __init__(self, title: str, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._title, self._summary = title, ""
        self.toggle = QToolButton()
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.body = QWidget()
        rule = QFrame()
        rule.setObjectName("sectionRule")
        rule.setFixedHeight(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(rule)
        lay.addWidget(self.toggle)
        lay.addWidget(self.body)
        self.toggle.toggled.connect(self._show)
        self.toggle.setChecked(bool(_ui_state().value(key, True, type=bool)))
        self._show(self.toggle.isChecked())

    def is_open(self) -> bool:
        return self.toggle.isChecked()

    def set_summary(self, summary: str) -> None:
        """What the section holds, shown after the title while it is closed."""
        # short, so a closed section never makes the panel wider
        self._summary = summary if len(summary) <= SUMMARY_CHARS else \
            summary[:SUMMARY_CHARS - 1].rstrip() + "…"
        self._show(self.toggle.isChecked(), remember=False)

    def set_open(self, open_: bool) -> None:
        self.toggle.setChecked(open_)

    def _show(self, open_: bool, remember: bool = True) -> None:
        self.body.setVisible(open_)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow)
        closed = f"{self._title}  ·  {self._summary}" if self._summary else self._title
        self.toggle.setText(self._title if open_ else closed)
        if remember:
            _ui_state().setValue(self._key, open_)


def _ui_state() -> QSettings:
    return QSettings(str(data_dir() / "window.ini"), QSettings.Format.IniFormat)
