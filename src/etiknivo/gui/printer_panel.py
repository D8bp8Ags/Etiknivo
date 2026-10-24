"""Printer management panel (Bluetooth scan, connect, status, test prints)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from etiknivo import i18n
from etiknivo.gui import theme
from etiknivo.i18n import N_, tr
from etiknivo.printing import registry
from etiknivo.printing.backend import ConnectionState
from etiknivo.printing.manager import PrinterState
from etiknivo.printing.profiles import PrinterProfile

STATE_TEXT = {
    ConnectionState.DISCONNECTED: (N_("Niet verbonden"), "muted"),
    ConnectionState.CONNECTING: (N_("Verbinden…"), "warning"),
    ConnectionState.CONNECTED: (N_("Verbonden"), "success"),
    ConnectionState.ERROR: (N_("Fout"), "danger"),
}


def size_text(length: float, height: float) -> str:
    """'30 × 14 mm', with a decimal comma in Dutch."""
    comma = i18n.language() == "nl"
    return " × ".join(f"{v:g}".replace(".", ",") if comma else f"{v:g}"
                      for v in (length, height)) + " mm"


class PrinterPanel(QWidget):
    scanRequested = Signal()
    connectRequested = Signal(str)
    disconnectRequested = Signal()
    refreshRequested = Signal()
    testLabelRequested = Signal()
    calibrationRequested = Signal()
    calibrationSettingsRequested = Signal()
    mockToggled = Signal(bool)
    modelChanged = Signal(str)  # printer model key
    labelSizeChanged = Signal(float, float)  # roll length, height in mm

    def __init__(self, profile: PrinterProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 14)
        lay.setSpacing(2)

        conn = QGroupBox(tr("Bluetooth-printer"))
        cl = QVBoxLayout(conn)
        # printer model choice: only shown once there is more than one model
        self.model = QComboBox()
        for key, m in registry.MODELS.items():
            self.model.addItem(m.display_name, key)
        self.model.setCurrentIndex(max(0, self.model.findData(profile.key)))
        self.model.setVisible(len(registry.MODELS) > 1)
        self.model.activated.connect(lambda: self.modelChanged.emit(self.model.currentData()))
        self.mock = QCheckBox(tr("Simulatieprinter gebruiken (geen hardware)"))
        self.mock.setToolTip(tr("Voor testen zonder printer. Er wordt niets echt afgedrukt."))
        self.only_printers = QCheckBox(tr("Alleen labelprinters tonen"))
        self.only_printers.setChecked(True)
        self.devices = QListWidget()
        self.devices.setMaximumHeight(110)
        self.scan_btn = QPushButton(tr("Zoeken"))
        self.scan_busy = QProgressBar()
        self.scan_busy.setRange(0, 0)
        self.scan_busy.setMaximumHeight(6)
        self.scan_busy.setTextVisible(False)
        self.scan_busy.hide()
        self.connect_btn = QPushButton(tr("Verbinden"))
        self.disconnect_btn = QPushButton(tr("Verbreken"))
        row = QHBoxLayout()
        row.addWidget(self.scan_btn)
        row.addWidget(self.connect_btn)
        row.addWidget(self.disconnect_btn)
        cl.addWidget(self.model)
        cl.addWidget(self.mock)
        cl.addWidget(self.only_printers)
        cl.addWidget(self.devices)
        cl.addWidget(self.scan_busy)
        cl.addLayout(row)
        lay.addWidget(conn)

        st = QGroupBox(tr("Status"))
        f = QFormLayout(st)
        self.state_lbl = QLabel()
        self.state_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.model_lbl = QLabel("–")
        self.battery = QProgressBar()
        self.battery.setRange(0, 100)
        self.battery.setTextVisible(False)
        self.battery_lbl = QLabel("–")
        self.battery_lbl.setObjectName("muted")
        self.status_lbl = QLabel("–")
        self.status_lbl.setWordWrap(True)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("hint")
        self.refresh_btn = QPushButton(tr("Status vernieuwen"))
        f.addRow(tr("Verbinding"), self.state_lbl)
        f.addRow(tr("Printer"), self.model_lbl)
        bat = QHBoxLayout()
        bat.addWidget(self.battery, 1)
        bat.addWidget(self.battery_lbl)
        f.addRow(tr("Batterij"), bat)
        f.addRow(tr("Toestand"), self.status_lbl)
        f.addRow(self.message)
        f.addRow(self.refresh_btn)
        lay.addWidget(st)

        pr = QGroupBox(tr("Afdrukinstellingen"))
        f2 = QFormLayout(pr)
        self.roll = QComboBox()
        self.roll.setToolTip(tr("Welke etiketten er in de printer zitten. Alle labels worden "
                                "voor deze maat ontworpen en afgedrukt."))
        self._sizes: list[tuple[float, float]] = []
        self.set_label_size(profile)
        self.roll.activated.connect(self._roll_chosen)
        self.density = QComboBox()
        self.density.addItems(list(profile.densities))
        self.copies = QSpinBox()
        self.copies.setRange(1, 99)
        self.test_btn = QPushButton(tr("Testlabel afdrukken"))
        self.cal_btn = QPushButton(tr("Kalibratietest afdrukken"))
        self.cal_settings_btn = QPushButton(tr("Kalibratie-instellingen…"))
        f2.addRow(tr("Etiketrol"), self.roll)
        f2.addRow(tr("Printdichtheid"), self.density)
        f2.addRow(tr("Exemplaren"), self.copies)
        f2.addRow(self.test_btn)
        f2.addRow(self.cal_btn)
        f2.addRow(self.cal_settings_btn)
        lay.addWidget(pr)
        lay.addStretch(1)
        self.apply_theme()
        theme.manager().changed.connect(self.apply_theme)

        self.scan_btn.clicked.connect(self._scan)
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(self.disconnectRequested)
        self.refresh_btn.clicked.connect(self.refreshRequested)
        self.test_btn.clicked.connect(self.testLabelRequested)
        self.cal_btn.clicked.connect(self.calibrationRequested)
        self.cal_settings_btn.clicked.connect(self.calibrationSettingsRequested)
        self.mock.toggled.connect(self.mockToggled)
        self.only_printers.toggled.connect(lambda: self._fill_devices(self._last_devices))
        self.devices.itemDoubleClicked.connect(lambda _it: self._connect())
        self._last_devices: list = []
        self._remembered = ""
        self.set_state(PrinterState())

    def apply_theme(self) -> None:
        for btn, name in ((self.scan_btn, "bluetooth"), (self.connect_btn, "plug"),
                          (self.disconnect_btn, "unplug"), (self.refresh_btn, "refresh-cw"),
                          (self.test_btn, "printer"), (self.cal_btn, "ruler"),
                          (self.cal_settings_btn, "sliders-horizontal")):
            btn.setIcon(theme.icon(name, size=16))
        if hasattr(self, "_state"):
            self.set_state(self._state)

    def remember_address(self, address: str) -> None:
        self._remembered = address

    # -- label roll -----------------------------------------------------------------------

    def set_label_size(self, profile: PrinterProfile) -> None:
        """Fill the roll choice: the model's sizes, the current one if it is
        custom, and 'Custom…'."""
        current = profile.label_size
        self._sizes = list(profile.label_sizes or (current,))
        if current not in self._sizes:
            self._sizes.append(current)
        self.roll.blockSignals(True)
        self.roll.clear()
        for length, height in self._sizes:
            self.roll.addItem(size_text(length, height))
        self.roll.addItem(tr("Aangepast…"))
        self.roll.setCurrentIndex(self._sizes.index(current))
        self.roll.blockSignals(False)
        self._current = current

    def _roll_chosen(self, index: int) -> None:
        if index < len(self._sizes):
            size = self._sizes[index]
        else:
            from etiknivo.gui.dialogs import LabelSizeDialog

            dlg = LabelSizeDialog(*self._current, parent=self)
            if dlg.exec() != LabelSizeDialog.DialogCode.Accepted:
                self.roll.setCurrentIndex(self._sizes.index(self._current))
                return
            size = dlg.size_mm()
        if size != self._current:
            self.labelSizeChanged.emit(*size)
        else:
            self.roll.setCurrentIndex(self._sizes.index(self._current))

    def _scan(self) -> None:
        self.scan_btn.setEnabled(False)
        self.scan_busy.show()
        self.scanRequested.emit()

    def scan_finished(self) -> None:
        self.scan_btn.setEnabled(True)
        self.scan_busy.hide()

    def selected_address(self) -> str:
        it = self.devices.currentItem()
        if it is not None:
            return str(it.data(Qt.ItemDataRole.UserRole))
        return self._remembered

    def _connect(self) -> None:
        self.connectRequested.emit(self.selected_address())

    def _fill_devices(self, devices: list) -> None:
        self._last_devices = devices
        self.devices.clear()
        for d in devices:
            if self.only_printers.isChecked() and not d.supported:
                continue
            it = QListWidgetItem(f"{d.name}  ·  {d.address}  ·  {d.rssi} dBm")
            if d.supported:
                it.setIcon(theme.icon("printer", size=16))
            it.setData(Qt.ItemDataRole.UserRole, d.address)
            self.devices.addItem(it)
            if d.address == self._remembered or (self.devices.count() == 1 and d.supported):
                self.devices.setCurrentItem(it)

    def set_state(self, st: PrinterState) -> None:
        self._state = st
        t = theme.tokens()
        text, tone = STATE_TEXT[st.connection]
        text = tr(text)
        if st.simulated:
            text = tr("{state} (simulatie)", state=text)
        self.state_lbl.setText(f"<span style='color:{getattr(t, tone)}'>●</span>&nbsp; {text}")
        connected = st.connection == ConnectionState.CONNECTED
        busy = st.connection == ConnectionState.CONNECTING
        self.connect_btn.setEnabled(not connected and not busy)
        self.disconnect_btn.setEnabled(connected)
        self.refresh_btn.setEnabled(connected)
        self.test_btn.setEnabled(connected)
        self.cal_btn.setEnabled(connected)
        info = st.info
        if info and connected:
            self.model_lbl.setText(f"{info.model} · fw {info.firmware}")
            if info.battery is None:
                self.battery.setValue(0)
                self.battery_lbl.setText(tr("onbekend"))
            else:
                self.battery.setValue(info.battery)
                self.battery_lbl.setText(f"{info.battery}%")
            self.battery.setProperty("level", "low" if (info.battery or 100) < 20 else "")
            s = info.status
            color = t.success if s.ok and not s.unknown else t.danger
            self.status_lbl.setText(f"<span style='color:{color}'>{s.describe()}</span>")
        else:
            self.model_lbl.setText("–")
            self.battery.setValue(0)
            self.battery_lbl.setText("–")
            self.status_lbl.setText("–")
        self.battery.style().unpolish(self.battery)
        self.battery.style().polish(self.battery)
        self.message.setText(st.message)
        if st.devices is not self._last_devices:
            self._fill_devices(st.devices)
        if st.address:
            self._remembered = st.address
