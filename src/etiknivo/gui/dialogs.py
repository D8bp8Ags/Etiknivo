"""Dialogs: print preview/confirmation, calibration settings and About."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QColor
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
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from etiknivo import APP_NAME, __version__
from etiknivo.gui import theme
from etiknivo.gui.qt_util import pil_to_pixmap
from etiknivo.i18n import N_, language, tr
from etiknivo.model import Label
from etiknivo.printing.profiles import LABEL_HEIGHT_RANGE, LABEL_LENGTH_RANGE, PrinterProfile
from etiknivo.rendering.engine import RenderEngine
from etiknivo.settings import Calibration


class PrintPreviewDialog(QDialog):
    """Shows exactly what will be printed and asks for confirmation."""

    def __init__(self, engine: RenderEngine, labels: list[Label], copies: int, density: int,
                 printer_text: str, can_print: bool, parent: QWidget | None = None) -> None:
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


def short_path(path: Path) -> str:
    """*path* with the home folder as ``~``, so screenshots don't show the user name."""
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


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
                            "Open source, lokaal, zonder account."))
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
        copy.setToolTip(tr("Versies van Etiknivo, Python, Qt en macOS, handig bij een foutmelding"))
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
