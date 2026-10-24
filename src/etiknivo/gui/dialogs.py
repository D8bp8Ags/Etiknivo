"""Dialogs: print preview/confirmation and calibration settings."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui import theme
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
            sp.setValue(copies)
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
        form.addRow("Printdichtheid", self.density)
        form.addRow("Totaal", self.total)
        lay.addLayout(form)
        if self.overflow:
            w = QLabel(f"⚠ {self.overflow} label(s) hebben tekst buiten het printbare gebied.")
            w.setStyleSheet(f"color: {theme.tokens().danger};")
            lay.addWidget(w)
        if not can_print:
            w = QLabel("⚠ Geen printer verbonden. Verbind eerst in het printerpaneel "
                       "(of zet de simulatieprinter aan).")
            w.setStyleSheet(f"color: {theme.tokens().danger};")
            w.setWordWrap(True)
            lay.addWidget(w)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = bb.addButton("Afdrukken", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setProperty("primary", True)
        self.ok.setIcon(theme.icon("printer", theme.tokens().on_accent, 16))
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
    """Fine-tuning of position and print quality, explained step by step."""

    def __init__(self, cal: Calibration, parent: QWidget | None = None,
                 dots_per_mm: int = 8) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kalibratie")
        self.setMinimumWidth(520)
        self._dpm = dots_per_mm
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        intro = QLabel(
            "<b>Zo kalibreer je</b>"
            "<ol style='margin-left:-20px'>"
            "<li>Kies <i>Afdrukken → Kalibratietest</i>. Er komt een kader met middellijnen "
            "en een millimeterliniaal op het etiket.</li>"
            "<li>Kijk of er links en rechts evenveel wit naast het kader staat (ongeveer 2 mm), "
            "en boven en onder ook.</li>"
            "<li>Staat het scheef? Verschuif hieronder, druk opnieuw af en herhaal tot het "
            "klopt.</li></ol>"
            "Bekende afwijkingen van je printer worden al automatisch gecorrigeerd. Meestal is "
            "alles hier 0 goed.")
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

        pos = QGroupBox("Positie op het etiket")
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
        add(f, "Links / rechts", self.feed, self.feed_hint)
        add(f, "Omhoog / omlaag", self.head, self.head_hint)
        self.feed.valueChanged.connect(self._update_hints)
        self.head.valueChanged.connect(self._update_hints)
        lay.addWidget(pos)

        quality = QGroupBox("Afdrukkwaliteit")
        q = QVBoxLayout(quality)
        q.setSpacing(3)
        self.threshold = QSpinBox()
        self.threshold.setRange(40, 230)
        self.threshold.setValue(cal.threshold)
        self.supersample = QComboBox()
        for n in (1, 2, 3, 4, 6, 8):
            self.supersample.addItem(f"{n}×", n)
        self.supersample.setCurrentIndex(max(0, self.supersample.findData(cal.supersample)))
        self.clockwise = QCheckBox("Etiket ondersteboven afdrukken")
        self.clockwise.setChecked(cal.rotate_clockwise)
        add(q, "Zwartdrempel", self.threshold, hint(
            "Bepaalt hoe dik letters worden. Hoger = dikker en zwarter, lager = dunner. "
            "Standaard 140; pas aan als kleine tekst dichtloopt of wegvalt."))
        add(q, "Gladde randen", self.supersample, hint(
            "Hoe nauwkeurig letters naar printerdots worden omgezet. 4× is scherp en snel "
            "genoeg; hoger maakt weinig verschil."))
        add(q, "", self.clockwise, hint(
            "Alleen nodig als je labels op hun kop uit de printer komen."))
        lay.addWidget(quality)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel
                              | QDialogButtonBox.StandardButton.RestoreDefaults)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText("Standaardwaarden")
        bb.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._defaults)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuleren")
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
            return f"Geen verschuiving. {ask}"
        mm = abs(dots) / self._dpm
        side = plus if dots > 0 else minus
        mm_text = f"{mm:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"Afdruk schuift {mm_text} mm naar {side} ({self._dpm} dots = 1 mm)."

    def _update_hints(self) -> None:
        self.feed_hint.setText(self._shift_text(
            self.feed.value(), "rechts", "links",
            "Meer wit links dan rechts? Kies een negatief getal; meer wit rechts: positief."))
        self.head_hint.setText(self._shift_text(
            self.head.value(), "onder", "boven",
            "Meer wit boven dan onder? Kies een negatief getal; meer wit onder: positief."))

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
