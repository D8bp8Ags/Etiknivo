"""Dialogs: print preview/confirmation, calibration settings and About."""

from __future__ import annotations

import html
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from etiknivo import APP_NAME, __version__
from etiknivo.gui import theme
from etiknivo.gui.qt_util import pil_to_pixmap, remember_size
from etiknivo.i18n import N_, language, tr
from etiknivo.model import FORMAT_PARTS, Label, PictureKind
from etiknivo.printing.profiles import LABEL_HEIGHT_RANGE, LABEL_LENGTH_RANGE, PrinterProfile
from etiknivo.privacy import short_path
from etiknivo.rendering.engine import RenderEngine
from etiknivo.settings import Calibration


class PrintPreviewDialog(QDialog):
    """Shows exactly what will be printed and asks for confirmation."""

    def __init__(self, engine: RenderEngine, labels: list[Label], copies: int | list[int],
                 density: int, printer_text: str, can_print: bool,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Afdrukvoorbeeld"))
        self.labels = labels
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        intro = QLabel(tr("<b>{n} label(s)</b> — dit is de 1-bit printerraster zoals die naar "
                          "de printer gaat. Printer: {printer}", n=len(labels),
                          printer=printer_text))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self.table = QTableWidget(len(labels), 4)
        self.table.setHorizontalHeaderLabels([tr("Voorbeeld"), tr("Label"), tr("Exemplaren"),
                                              tr("Let op")])
        self.table.verticalHeader().hide()
        self.table.setIconSize(QSize(180, 84))
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 190)
        self.table.setColumnWidth(1, 200)
        remember_size(self, "print_preview", self.table.horizontalHeader())
        self.spins: list[QSpinBox] = []
        self.overflow = 0
        for row, lbl in enumerate(labels):
            r = engine.render(lbl)
            pm = pil_to_pixmap(engine.raster_on_label(r.raster).convert("L")).scaled(
                180, 84, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation)
            icon_item = QTableWidgetItem()
            icon_item.setData(Qt.ItemDataRole.DecorationRole, pm)
            self.table.setItem(row, 0, icon_item)
            self.table.setItem(row, 1, QTableWidgetItem(
                f"{lbl.tray_id}  {lbl.name}".strip()))
            sp = QSpinBox()
            sp.setRange(1, 99)
            sp.setValue(copies[row] if isinstance(copies, list) else copies)
            sp.valueChanged.connect(self._update_total)
            self.spins.append(sp)
            cell = QWidget()  # keep the spin box at its normal height in the tall row
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(6, 0, 6, 0)
            cl.addWidget(sp, 0, Qt.AlignmentFlag.AlignVCenter)
            self.table.setCellWidget(row, 2, cell)
            warn = "; ".join(r.warnings)
            if r.has_overflow:
                self.overflow += 1
            it = QTableWidgetItem(warn or "OK")
            if warn:
                it.setForeground(QColor(theme.tokens().danger))
                it.setToolTip(warn)
            self.table.setItem(row, 3, it)
            self.table.setRowHeight(row, 92)
        lay.addWidget(self.table, 1)

        form = QFormLayout()
        self.density = QComboBox()
        self.density.addItems(list(engine.profile.densities))
        self.density.setCurrentIndex(density)
        self.total = QLabel()
        form.addRow(tr("Printdichtheid"), self.density)
        form.addRow(tr("Totaal"), self.total)
        lay.addLayout(form)
        if self.overflow:
            w = QLabel("⚠ " + tr("{n} label(s) hebben tekst buiten het printbare gebied.",
                                 n=self.overflow))
            w.setStyleSheet(f"color: {theme.tokens().danger};")
            lay.addWidget(w)
        if not can_print:
            w = QLabel("⚠ " + tr("Geen printer verbonden. Verbind eerst in het printerpaneel "
                                 "(of zet de simulatieprinter aan)."))
            w.setStyleSheet(f"color: {theme.tokens().danger};")
            w.setWordWrap(True)
            lay.addWidget(w)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = bb.addButton(tr("Afdrukken"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setProperty("primary", True)
        self.ok.setIcon(theme.icon("printer", theme.tokens().on_accent, 16))
        self.ok.setEnabled(can_print)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._update_total()

    def _update_total(self) -> None:
        self.total.setText(tr("{n} etiketten", n=sum(s.value() for s in self.spins)))

    def copies_per_label(self) -> list[int]:
        return [s.value() for s in self.spins]


class CalibrationDialog(QDialog):
    """Fine-tuning of position and print quality, explained step by step."""

    def __init__(self, cal: Calibration, parent: QWidget | None = None,
                 dots_per_mm: int = 8) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Kalibratie"))
        self.setMinimumWidth(520)
        self._dpm = dots_per_mm
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        intro = QLabel(
            "<b>" + tr("Zo kalibreer je") + "</b><ol style='margin-left:-20px'><li>"
            + tr("Kies <i>Afdrukken → Kalibratietest</i>. Er komt een kader met middellijnen "
                 "en een millimeterliniaal op het etiket.") + "</li><li>"
            + tr("Kijk of er links en rechts evenveel wit naast het kader staat (ongeveer "
                 "2 mm), en boven en onder ook.") + "</li><li>"
            + tr("Staat het scheef? Verschuif hieronder, druk opnieuw af en herhaal tot het "
                 "klopt.") + "</li></ol>"
            + tr("Bekende afwijkingen van je printer worden al automatisch gecorrigeerd. "
                 "Meestal is alles hier 0 goed."))
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(intro)

        def hint(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            return lbl

        def add(box: QVBoxLayout, title: str, control: QWidget, below: QLabel) -> None:
            # title + control on one line, the explanation underneath it
            line = QHBoxLayout()
            if title:
                cap = QLabel(title)
                cap.setMinimumWidth(130)
                line.addWidget(cap)
            line.addWidget(control, 1)
            box.addLayout(line)
            box.addWidget(below)
            box.addSpacing(6)

        pos = QGroupBox(tr("Positie op het etiket"))
        f = QVBoxLayout(pos)
        f.setSpacing(3)
        self.feed = QSpinBox()
        self.feed.setRange(-40, 40)
        self.feed.setValue(cal.offset_feed_px)
        self.feed.setSuffix(" dots")
        self.head = QSpinBox()
        self.head.setRange(-16, 16)
        self.head.setValue(cal.offset_head_px)
        self.head.setSuffix(" dots")
        self.feed_hint = hint("")
        self.head_hint = hint("")
        add(f, tr("Links / rechts"), self.feed, self.feed_hint)
        add(f, tr("Omhoog / omlaag"), self.head, self.head_hint)
        self.feed.valueChanged.connect(self._update_hints)
        self.head.valueChanged.connect(self._update_hints)
        lay.addWidget(pos)

        quality = QGroupBox(tr("Afdrukkwaliteit"))
        q = QVBoxLayout(quality)
        q.setSpacing(3)
        self.threshold = QSpinBox()
        self.threshold.setRange(40, 230)
        self.threshold.setValue(cal.threshold)
        self.supersample = QComboBox()
        for n in (1, 2, 3, 4, 6, 8):
            self.supersample.addItem(f"{n}×", n)
        self.supersample.setCurrentIndex(max(0, self.supersample.findData(cal.supersample)))
        self.clockwise = QCheckBox(tr("Etiket ondersteboven afdrukken"))
        self.clockwise.setChecked(cal.rotate_clockwise)
        add(q, tr("Zwartdrempel"), self.threshold, hint(tr(
            "Bepaalt hoe dik letters worden. Hoger = dikker en zwarter, lager = dunner. "
            "Standaard 140; pas aan als kleine tekst dichtloopt of wegvalt.")))
        add(q, tr("Gladde randen"), self.supersample, hint(tr(
            "Hoe nauwkeurig letters naar printerdots worden omgezet. 4× is scherp en snel "
            "genoeg; hoger maakt weinig verschil.")))
        add(q, "", self.clockwise, hint(tr(
            "Alleen nodig als je labels op hun kop uit de printer komen.")))
        lay.addWidget(quality)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel
                              | QDialogButtonBox.StandardButton.RestoreDefaults)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText(tr("Standaardwaarden"))
        bb.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._defaults)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Annuleren"))
        lay.addWidget(bb)
        self._update_hints()

    def showEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt API
        # wrapped explanations need the height that belongs to the width
        super().showEvent(event)
        h = self.layout().totalHeightForWidth(self.width())
        if h > self.height():
            self.resize(self.width(), h)

    def _shift_text(self, dots: int, plus: str, minus: str, ask: str) -> str:
        if dots == 0:
            return tr("Geen verschuiving.") + " " + ask
        mm = abs(dots) / self._dpm
        side = plus if dots > 0 else minus
        mm_text = f"{mm:.2f}".rstrip("0").rstrip(".")
        if language() == "nl":
            mm_text = mm_text.replace(".", ",")
        return tr("Afdruk schuift {mm} mm {direction} ({dpm} dots = 1 mm).", mm=mm_text,
                  direction=tr(side), dpm=self._dpm)

    def _update_hints(self) -> None:
        self.feed_hint.setText(self._shift_text(
            self.feed.value(), N_("naar rechts"), N_("naar links"),
            tr("Meer wit links dan rechts? Kies een negatief getal; meer wit rechts: positief.")))
        self.head_hint.setText(self._shift_text(
            self.head.value(), N_("naar onder"), N_("naar boven"),
            tr("Meer wit boven dan onder? Kies een negatief getal; meer wit onder: positief.")))

    def _defaults(self) -> None:
        d = Calibration()
        self.feed.setValue(d.offset_feed_px)
        self.head.setValue(d.offset_head_px)
        self.threshold.setValue(d.threshold)
        self.supersample.setCurrentIndex(self.supersample.findData(d.supersample))
        self.clockwise.setChecked(d.rotate_clockwise)

    def calibration(self, base: Calibration) -> Calibration:
        return replace(base, offset_feed_px=self.feed.value(), offset_head_px=self.head.value(),
                       threshold=self.threshold.value(),
                       supersample=int(self.supersample.currentData()),
                       rotate_clockwise=self.clockwise.isChecked())


class CopyFormatDialog(QDialog):
    """'Opmaak overnemen': which parts of the open label's look go to which labels."""

    def __init__(self, source: Label, selected: int, categories: list[str],
                 count: Callable[[str, str], int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Opmaak overnemen"))
        self._count = count
        lay = QVBoxLayout(self)
        intro = QLabel(tr("De opmaak van <b>{name}</b> overnemen. De tekst, specificaties en "
                          "notities van de andere labels blijven zoals ze zijn.",
                          name=html.escape(source.name)))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        what = QGroupBox(tr("Wat"))
        wl = QVBoxLayout(what)
        self.parts: dict[str, QCheckBox] = {}
        for key, text in FORMAT_PARTS.items():
            box = QCheckBox(tr(text))
            box.setChecked(key in ("layout", "style"))
            box.toggled.connect(self._update)
            wl.addWidget(box)
            self.parts[key] = box
        lay.addWidget(what)

        where = QGroupBox(tr("Op welke labels"))
        gl = QVBoxLayout(where)
        self.on_selection = QRadioButton(tr("Geselecteerde labels ({n})", n=selected))
        self.on_category = QRadioButton(tr("Alle labels in categorie"))
        self.category = QComboBox()
        self.category.addItems(categories)
        if source.category in categories:
            self.category.setCurrentText(source.category)
        self.on_all = QRadioButton(tr("Alle labels"))
        cat_row = QHBoxLayout()
        cat_row.addWidget(self.on_category)
        cat_row.addWidget(self.category, 1)
        gl.addWidget(self.on_selection)
        gl.addLayout(cat_row)
        gl.addWidget(self.on_all)
        self.on_selection.setEnabled(selected > 0)
        self.on_category.setEnabled(bool(categories))
        (self.on_selection if selected else self.on_category if categories
         else self.on_all).setChecked(True)
        for w in (self.on_selection, self.on_category, self.on_all):
            w.toggled.connect(self._update)
        self.category.currentIndexChanged.connect(self._update)
        lay.addWidget(where)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = bb.addButton(tr("Toepassen"), QDialogButtonBox.ButtonRole.AcceptRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._update()

    def target(self) -> tuple[str, str]:
        """('selection' | 'category' | 'all', category name)."""
        if self.on_selection.isChecked():
            return "selection", ""
        if self.on_category.isChecked():
            return "category", self.category.currentText()
        return "all", ""

    def chosen_parts(self) -> set[str]:
        return {k for k, box in self.parts.items() if box.isChecked()}

    def _update(self) -> None:
        self.category.setEnabled(self.on_category.isChecked())
        n = self._count(*self.target())
        self.ok.setText(tr("Toepassen op {n} label(s)", n=n))
        self.ok.setEnabled(n > 0 and bool(self.chosen_parts()))


class PictogramsDialog(QDialog):
    """'Pictogrammen': one symbol per category, the labels underneath.  A label
    follows its category unless it has a symbol of its own; only ticked labels
    change."""

    FOLLOW = None  # a label without a symbol of its own

    def __init__(self, labels: list[Label], category_symbol: Callable[[str], str],
                 checked: set[str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Pictogrammen"))
        self.resize(680, 640)
        self._labels = {lbl.id: lbl for lbl in labels}
        #: label id -> its own symbol ("" = none), or FOLLOW
        self._own: dict[str, str | None] = {}
        #: category -> its symbol ("" = none); its row shows it, a click changes it
        self._cat_symbols: dict[str, str] = {}
        self._cat_items: dict[str, QTreeWidgetItem] = {}
        #: categories whose symbol the user picked here (so "none" was meant)
        self._picked: set[str] = set()
        self._items: dict[str, QTreeWidgetItem] = {}
        self._filling = True

        lay = QVBoxLayout(self)
        intro = QLabel(tr("Kies per categorie een pictogram; de labels eronder krijgen het, "
                          "behalve labels met een eigen pictogram. Alleen aangevinkte labels "
                          "veranderen. Selecteer meerdere labels (Shift-klik) om ze samen aan "
                          "te passen."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Zoeken in labels…"))
        self.search.setClearButtonEnabled(True)
        lay.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([tr("Label"), tr("Lade-ID"), tr("Pictogram")])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setIconSize(QSize(20, 20))
        self.tree.setUniformRowHeights(True)
        head = self.tree.header()
        head.setStretchLastSection(False)
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        head.resizeSection(2, 220)
        remember_size(self, "pictograms", head)
        groups: dict[str, list[Label]] = {}
        for lbl in labels:
            groups.setdefault(lbl.category, []).append(lbl)
        bold = self.font()
        bold.setBold(True)
        for cat in sorted(groups, key=lambda c: (c == "", c.casefold())):
            top = QTreeWidgetItem([f"{cat or tr('(zonder categorie)')}  ({len(groups[cat])})"])
            top.setFont(0, bold)
            top.setData(0, Qt.ItemDataRole.UserRole, ("cat", cat))
            top.setFlags(top.flags() | Qt.ItemFlag.ItemIsUserCheckable
                         | Qt.ItemFlag.ItemIsAutoTristate)
            top.setFont(2, bold)
            top.setToolTip(2, tr("Klik om het pictogram van deze categorie te kiezen"))
            self.tree.addTopLevelItem(top)
            self._cat_items[cat] = top
            self._cat_symbols[cat] = category_symbol(cat) if cat else ""
            for lbl in sorted(groups[cat], key=lambda x: (x.tray_id == "", x.tray_id, x.name)):
                item = QTreeWidgetItem([lbl.name, lbl.tray_id, ""])
                item.setData(0, Qt.ItemDataRole.UserRole, ("label", lbl.id))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                on = (checked is None or lbl.id in checked) \
                    and lbl.picture.kind != PictureKind.IMAGE
                item.setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
                top.addChild(item)
                self._items[lbl.id] = item
            # a label keeps the symbol it has when that differs from its category's
            for lbl in groups[cat]:
                current = self._current(lbl)
                self._own[lbl.id] = self.FOLLOW if lbl.picture.kind == PictureKind.NONE \
                    or current == self._cat_symbols[cat] else current
            top.setExpanded(True)
        lay.addWidget(self.tree, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.set_btn = QPushButton(tr("Eigen pictogram…"))
        self.set_btn.setToolTip(tr("De geselecteerde labels een eigen pictogram geven"))
        self.set_btn.setMenu(self._symbol_menu(self._set_own))
        self.follow_btn = QPushButton(tr("Volgt categorie"))
        self.follow_btn.setToolTip(tr("De geselecteerde labels krijgen weer het pictogram "
                                      "van hun categorie"))
        self.include_btn = QPushButton(tr("Meenemen"))
        self.exclude_btn = QPushButton(tr("Overslaan"))
        self.include_btn.setToolTip(tr("De geselecteerde labels aanvinken"))
        self.exclude_btn.setToolTip(tr("De geselecteerde labels uitvinken: die blijven zoals ze "
                                       "zijn"))
        for w in (self.set_btn, self.follow_btn, self.include_btn, self.exclude_btn):
            actions.addWidget(w)
        actions.addStretch(1)
        lay.addLayout(actions)

        side_row = QHBoxLayout()
        side_row.addWidget(QLabel(tr("Plaats bij labels zonder pictogram")))
        self.side = QComboBox()
        self.side.addItem(tr("Links"), "left")
        self.side.addItem(tr("Rechts"), "right")
        side_row.addWidget(self.side)
        side_row.addStretch(1)
        lay.addLayout(side_row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = bb.addButton(tr("Toepassen"), QDialogButtonBox.ButtonRole.AcceptRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.follow_btn.clicked.connect(lambda: self._set_own(self.FOLLOW))
        self.include_btn.clicked.connect(lambda: self._check(True))
        self.exclude_btn.clicked.connect(lambda: self._check(False))
        self.tree.itemChanged.connect(lambda *_: self._update())
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        self.search.textChanged.connect(self._filter)
        self._filling = False
        self._refresh_rows()
        self._update_buttons()

    # -- results ----------------------------------------------------------------------

    def target(self, label_id: str) -> str:
        """The symbol *label_id* gets: its own, else its category's ("" = none)."""
        own = self._own.get(label_id)
        if own is not None:
            return own
        return self._cat_symbols[self._labels[label_id].category]

    def changes(self) -> dict[str, str]:
        """{label id: symbol key, or "" for none} for the ticked labels that change."""
        out: dict[str, str] = {}
        for lid, item in self._items.items():
            if item.checkState(0) != Qt.CheckState.Checked:
                continue
            key = self.target(lid)
            if key != self._current(self._labels[lid]) or (
                    not key and self._labels[lid].picture.kind == PictureKind.IMAGE):
                out[lid] = key
        return out

    def category_choices(self) -> dict[str, str]:
        """The pictogram per category, to remember for new labels.  "None" is
        only remembered when picked here, so a category without a suggestion
        gets one once Etiknivo has a fitting symbol for it."""
        return {cat: key for cat, key in self._cat_symbols.items()
                if cat and (key or cat in self._picked)}

    def set_category_symbol(self, category: str, key: str) -> None:
        """Give *category* the symbol *key* ("" = none); its labels follow."""
        self._cat_symbols[category] = key
        self._picked.add(category)
        self._refresh_rows()

    # -- helpers ----------------------------------------------------------------------

    @staticmethod
    def _current(lbl: Label) -> str:
        return lbl.picture.symbol if lbl.picture.kind == PictureKind.SYMBOL else ""

    def _selected_ids(self) -> list[str]:
        """Selected labels; a selected category counts as all its labels."""
        ids: list[str] = []
        for item in self.tree.selectedItems():
            kind, value = item.data(0, Qt.ItemDataRole.UserRole)
            if kind == "label":
                ids.append(value)
            else:
                ids += [item.child(i).data(0, Qt.ItemDataRole.UserRole)[1]
                        for i in range(item.childCount())]
        return list(dict.fromkeys(ids))

    def _symbol_menu(self, choose: Callable[[str], None]) -> QMenu:
        from etiknivo.gui.widgets import symbol_icon
        from etiknivo.rendering.symbols import SYMBOL_CATEGORIES, SYMBOLS

        menu = QMenu(self)
        menu.addAction(tr("Geen pictogram")).triggered.connect(lambda: choose(""))
        menu.addSeparator()
        for category, keys in SYMBOL_CATEGORIES:
            sub = menu.addMenu(tr(category))
            for key in keys:
                act = sub.addAction(symbol_icon(key), tr(SYMBOLS[key][0]))
                act.triggered.connect(lambda _c=False, k=key: choose(k))
        return menu

    def _clicked(self, item: QTreeWidgetItem, column: int) -> None:
        kind, cat = item.data(0, Qt.ItemDataRole.UserRole)
        if kind != "cat" or column != 2:
            return
        rect = self.tree.visualItemRect(item)
        x = self.tree.header().sectionViewportPosition(2)
        menu = self._symbol_menu(lambda key: self.set_category_symbol(cat, key))
        menu.exec(self.tree.viewport().mapToGlobal(QPoint(x, rect.bottom())))

    def _set_own(self, key: str | None) -> None:
        for lid in self._selected_ids():
            self._own[lid] = key
            self._items[lid].setCheckState(0, Qt.CheckState.Checked)
        self._refresh_rows()

    def _check(self, on: bool) -> None:
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        for lid in self._selected_ids():
            self._items[lid].setCheckState(0, state)
        self._update()

    def _refresh_rows(self) -> None:
        from etiknivo.gui.widgets import symbol_icon
        from etiknivo.rendering.symbols import SYMBOLS

        muted = QColor(theme.tokens().muted)
        for cat, top in self._cat_items.items():
            key = self._cat_symbols[cat]
            top.setText(2, (tr(SYMBOLS[key][0]) if key in SYMBOLS else tr("Geen")) + "  ▾")
            top.setIcon(2, symbol_icon(key) if key in SYMBOLS else QIcon())
        for lid, item in self._items.items():
            key = self.target(lid)
            name = tr(SYMBOLS[key][0]) if key in SYMBOLS else tr("Geen")
            follows = self._own.get(lid) is None
            item.setText(2, ("↳ " + name) if follows else name)
            item.setIcon(2, symbol_icon(key) if key in SYMBOLS else QIcon())
            item.setForeground(2, muted if follows else self.palette().text().color())
            item.setToolTip(2, tr("Volgt de categorie") if follows else tr("Eigen pictogram"))
        self._update()

    def _filter(self, text: str) -> None:
        needle = text.casefold().strip()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            shown = 0
            for j in range(top.childCount()):
                child = top.child(j)
                hit = not needle or needle in (child.text(0) + " " + child.text(1)
                                               + " " + top.text(0)).casefold()
                child.setHidden(not hit)
                shown += hit
            top.setHidden(shown == 0)

    def _update_buttons(self) -> None:
        any_selected = bool(self._selected_ids())
        for w in (self.set_btn, self.follow_btn, self.include_btn, self.exclude_btn):
            w.setEnabled(any_selected)

    def _update(self) -> None:
        if self._filling:
            return
        n = len(self.changes())
        self.ok.setText(tr("Toepassen op {n} label(s)", n=n))
        # changing only the category choices is worth saving too
        self.ok.setEnabled(True)


class LabelSizeDialog(QDialog):
    """Asks for a custom label roll: length along the feed and height."""

    def __init__(self, length_mm: float, height_mm: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Andere etiketmaat"))
        lay = QVBoxLayout(self)
        intro = QLabel(tr("Meet een etiket op de rol, zonder de tussenruimte. De lengte is de "
                          "richting waarin het papier uit de printer komt; de hoogte gaat over "
                          "de printkop (die drukt maximaal 12 mm)."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        self.length = QDoubleSpinBox()
        self.length.setRange(*LABEL_LENGTH_RANGE)
        self.length.setDecimals(1)
        self.length.setSuffix(" mm")
        self.length.setValue(length_mm)
        self.height_mm = QDoubleSpinBox()
        self.height_mm.setRange(*LABEL_HEIGHT_RANGE)
        self.height_mm.setDecimals(1)
        self.height_mm.setSuffix(" mm")
        self.height_mm.setValue(height_mm)
        form.addRow(tr("Lengte"), self.length)
        form.addRow(tr("Hoogte"), self.height_mm)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def size_mm(self) -> tuple[float, float]:
        return round(self.length.value(), 1), round(self.height_mm.value(), 1)


class AboutDialog(QDialog):
    """Name, version, the printer in use, where the data lives and the credits."""

    REPO_URL = "https://github.com/D8bp8Ags/Etiknivo"

    def __init__(self, profile: PrinterProfile, data_path: Path, log_path: Path,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Over {app}", app=APP_NAME))
        self.setMinimumWidth(460)
        t = theme.tokens()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 18)
        lay.setSpacing(4)

        logo = QLabel()
        logo.setPixmap(theme.app_icon().pixmap(QSize(112, 112)))
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        name = QLabel(APP_NAME)
        name.setStyleSheet("font-size: 22px; font-weight: 700;")
        version = QLabel(tr("Versie {version}", version=__version__))
        version.setObjectName("muted")
        tagline = QLabel(tr("Etiketten ontwerpen, beheren en afdrukken.\n"
                            "Open source."))
        tagline.setWordWrap(True)
        for w in (logo, name, version, tagline):
            w.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(w)
        lay.addSpacing(14)

        def section(title: str, rows: list[tuple[str, str]]) -> None:
            head = QLabel(title.upper())
            head.setObjectName("caption")
            lay.addWidget(head)
            grid = QFormLayout()
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(3)
            for key, value in rows:
                k = QLabel(key)
                k.setObjectName("muted")
                v = QLabel(value)
                v.setWordWrap(True)
                v.setTextFormat(Qt.TextFormat.RichText)
                v.setOpenExternalLinks(True)
                v.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                grid.addRow(k, v)
            lay.addLayout(grid)
            lay.addSpacing(10)

        p = profile
        section(tr("Printer"), [
            (tr("Model"), p.display_name),
            (tr("Printkop"), f"{p.printhead_px} dots · {p.dpi} dpi"),
            (tr("Etiket"), tr("{w} × {h} mm, veilig gebied {sw} × {sh} mm",
                              w=f"{p.label_width_mm:g}", h=f"{p.label_height_mm:g}",
                              sw=f"{p.label_width_mm - 2 * p.feed_margin_mm:g}",
                              sh=f"{p.printable_across_px / p.dots_per_mm:g}")),
        ])
        link = f"color:{t.accent}; text-decoration:none"
        section(tr("Gegevens"), [
            (tr("Bibliotheek"), f"<a style='{link}' href='{QUrl.fromLocalFile(str(data_path)).toString()}'>"
                            f"{short_path(data_path)}</a>"),
            (tr("Logs"), f"<a style='{link}' href='{QUrl.fromLocalFile(str(log_path)).toString()}'>"
                     f"{short_path(log_path)}</a>"),
            (tr("Broncode"), f"<a style='{link}' href='{self.REPO_URL}'>"
                         f"{self.REPO_URL.removeprefix('https://')}</a>"),
        ])
        section(tr("Met dank aan"), [
            (tr("Interface"), "Qt for Python (PySide6), LGPL"),
            (tr("Bluetooth"), "Bleak, MIT"),
            (tr("Beeldbewerking"), "Pillow, MIT-CMU"),
            (tr("Lettertype"), tr("DejaVu Sans, vrije licentie")),
        ])
        lic = QLabel(tr("© {app}-bijdragers · MIT-licentie", app=APP_NAME))
        lic.setObjectName("hint")
        lic.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(lic)
        lay.addSpacing(8)

        bb = QDialogButtonBox()
        copy = bb.addButton(tr("Systeeminfo kopiëren"), QDialogButtonBox.ButtonRole.ActionRole)
        copy.setToolTip(tr("Versies van Etiknivo, Python, Qt en het besturingssysteem, "
                           "handig bij een foutmelding"))
        copy.clicked.connect(self._copy_info)
        close = bb.addButton(tr("Sluiten"), QDialogButtonBox.ButtonRole.AcceptRole)
        close.setProperty("primary", True)
        close.setDefault(True)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
        self._profile = profile

    def system_info(self) -> str:
        import platform

        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion

        return "\n".join([
            f"{APP_NAME} {__version__}",
            f"Printer: {self._profile.display_name} ({self._profile.key})",
            f"Python {platform.python_version()}",
            f"PySide6 {pyside_version}, Qt {qVersion()}",
            f"{platform.system()} {platform.release()} ({platform.machine()})",
        ])

    def _copy_info(self) -> None:
        QApplication.clipboard().setText(self.system_info())
        sender = self.sender()
        if isinstance(sender, QPushButton):
            sender.setText(tr("Gekopieerd ✓"))
