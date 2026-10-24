"""Dialogs: print preview/confirmation and calibration settings."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui.printer_panel import DENSITIES
from etiknivo.gui.qt_util import pil_to_pixmap
from etiknivo.model import Label
from etiknivo.rendering.engine import RenderEngine
from etiknivo.settings import Calibration


class PrintPreviewDialog(QDialog):
    """Shows exactly what will be printed and asks for confirmation."""

    def __init__(self, engine: RenderEngine, labels: list[Label], copies: int, density: int,
                 printer_text: str, can_print: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Afdrukvoorbeeld")
        self.labels = labels
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        intro = QLabel(f"<b>{len(labels)} label(s)</b> — dit is de 1-bit printerraster zoals "
                       f"die naar de printer gaat. Printer: {printer_text}")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self.table = QTableWidget(len(labels), 4)
        self.table.setHorizontalHeaderLabels(["Voorbeeld", "Label", "Exemplaren", "Let op"])
        self.table.verticalHeader().hide()
        self.table.setIconSize(QSize(180, 84))
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 190)
        self.table.setColumnWidth(1, 200)
        self.spins: list[QSpinBox] = []
        self.overflow = 0
        for row, lbl in enumerate(labels):
            r = engine.render(lbl)
            pm = pil_to_pixmap(engine.raster_to_design(r.raster).convert("L")).scaled(
                180, 84, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation)
            icon_item = QTableWidgetItem()
            icon_item.setData(Qt.ItemDataRole.DecorationRole, pm)
            self.table.setItem(row, 0, icon_item)
            self.table.setItem(row, 1, QTableWidgetItem(
                f"{lbl.tray_id}  {lbl.name}".strip()))
            sp = QSpinBox()
            sp.setRange(1, 99)
            sp.setValue(copies)
            sp.valueChanged.connect(self._update_total)
            self.spins.append(sp)
            self.table.setCellWidget(row, 2, sp)
            warn = "; ".join(r.warnings)
            if r.has_overflow:
                self.overflow += 1
            it = QTableWidgetItem(warn or "OK")
            if warn:
                it.setForeground(Qt.GlobalColor.red)
                it.setToolTip(warn)
            self.table.setItem(row, 3, it)
            self.table.setRowHeight(row, 92)
        lay.addWidget(self.table, 1)

        form = QFormLayout()
        self.density = QComboBox()
        self.density.addItems(DENSITIES)
        self.density.setCurrentIndex(density)
        self.total = QLabel()
        form.addRow("Printdichtheid", self.density)
        form.addRow("Totaal", self.total)
        lay.addLayout(form)
        if self.overflow:
            w = QLabel(f"⚠ {self.overflow} label(s) hebben tekst buiten het printbare gebied.")
            w.setStyleSheet("color: #d22;")
            lay.addWidget(w)
        if not can_print:
            w = QLabel("⚠ Geen printer verbonden. Verbind eerst in het printerpaneel "
                       "(of zet de simulatieprinter aan).")
            w.setStyleSheet("color: #d22;")
            w.setWordWrap(True)
            lay.addWidget(w)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = bb.addButton("Afdrukken", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setEnabled(can_print)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._update_total()

    def _update_total(self) -> None:
        self.total.setText(f"{sum(s.value() for s in self.spins)} etiketten")

    def copies_per_label(self) -> list[int]:
        return [s.value() for s in self.spins]


class CalibrationDialog(QDialog):
    def __init__(self, cal: Calibration, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kalibratie")
        lay = QVBoxLayout(self)
        info = QLabel(
            "Druk een kalibratietest af. Het kader (26 × 12 mm) hoort met aan beide uiteinden "
            "evenveel witruimte (ca. 2 mm) op het etiket te staan. Verschuif zo nodig. "
            "8 dots = 1 mm. <i>Langs rol</i> = 30 mm-zijde, <i>dwars</i> = 14 mm-zijde.")
        info.setWordWrap(True)
        lay.addWidget(info)
        f = QFormLayout()
        self.feed = QSpinBox()
        self.feed.setRange(-40, 40)
        self.feed.setValue(cal.offset_feed_px)
        self.feed.setSuffix(" dots")
        self.head = QSpinBox()
        self.head.setRange(-16, 16)
        self.head.setValue(cal.offset_head_px)
        self.head.setSuffix(" dots")
        self.threshold = QSpinBox()
        self.threshold.setRange(40, 230)
        self.threshold.setValue(cal.threshold)
        self.threshold.setToolTip("Hoger = dikkere letters (meer zwart), lager = dunner")
        self.supersample = QComboBox()
        for n in (1, 2, 3, 4, 6, 8):
            self.supersample.addItem(f"{n}×", n)
        self.supersample.setCurrentIndex(max(0, self.supersample.findData(cal.supersample)))
        self.clockwise = QCheckBox("Afdrukrichting omdraaien (label komt ondersteboven uit)")
        self.clockwise.setChecked(cal.rotate_clockwise)
        f.addRow("Verschuiving langs rol", self.feed)
        f.addRow("Verschuiving dwars", self.head)
        f.addRow("Zwartdrempel (0–255)", self.threshold)
        f.addRow("Antialiasing (supersampling)", self.supersample)
        f.addRow(self.clockwise)
        lay.addLayout(f)
        row = QHBoxLayout()
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel
                              | QDialogButtonBox.StandardButton.RestoreDefaults)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText("Standaardwaarden")
        bb.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._defaults)
        row.addWidget(bb)
        lay.addLayout(row)

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
