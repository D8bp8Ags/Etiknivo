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

from etiknivo.printing.backend import ConnectionState
from etiknivo.printing.manager import PrinterState

STATE_TEXT = {
    ConnectionState.DISCONNECTED: ("Niet verbonden", "#888"),
    ConnectionState.CONNECTING: ("Verbinden…", "#c80"),
    ConnectionState.CONNECTED: ("Verbonden", "#2a2"),
    ConnectionState.ERROR: ("Fout", "#d22"),
}
DENSITIES = ["Licht", "Normaal", "Donker"]


class PrinterPanel(QWidget):
    scanRequested = Signal()
    connectRequested = Signal(str)
    disconnectRequested = Signal()
    refreshRequested = Signal()
    testLabelRequested = Signal()
    calibrationRequested = Signal()
    calibrationSettingsRequested = Signal()
    mockToggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        conn = QGroupBox("Bluetooth-printer")
        cl = QVBoxLayout(conn)
        self.mock = QCheckBox("Simulatieprinter gebruiken (geen hardware)")
        self.mock.setToolTip("Voor testen zonder Fichero. Er wordt niets echt afgedrukt.")
        self.only_printers = QCheckBox("Alleen labelprinters tonen")
        self.only_printers.setChecked(True)
        self.devices = QListWidget()
        self.devices.setMaximumHeight(110)
        self.scan_btn = QPushButton("Zoeken")
        self.scan_busy = QProgressBar()
        self.scan_busy.setRange(0, 0)
        self.scan_busy.setMaximumHeight(6)
        self.scan_busy.setTextVisible(False)
        self.scan_busy.hide()
        self.connect_btn = QPushButton("Verbinden")
        self.disconnect_btn = QPushButton("Verbreken")
        row = QHBoxLayout()
        row.addWidget(self.scan_btn)
        row.addWidget(self.connect_btn)
        row.addWidget(self.disconnect_btn)
        cl.addWidget(self.mock)
        cl.addWidget(self.only_printers)
        cl.addWidget(self.devices)
        cl.addWidget(self.scan_busy)
        cl.addLayout(row)
        lay.addWidget(conn)

        st = QGroupBox("Status")
        f = QFormLayout(st)
        self.state_lbl = QLabel()
        self.state_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.model_lbl = QLabel("–")
        self.battery = QProgressBar()
        self.battery.setRange(0, 100)
        self.battery.setFormat("%p%")
        self.status_lbl = QLabel("–")
        self.status_lbl.setWordWrap(True)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: palette(mid);")
        self.refresh_btn = QPushButton("Status vernieuwen")
        f.addRow("Verbinding", self.state_lbl)
        f.addRow("Printer", self.model_lbl)
        f.addRow("Batterij", self.battery)
        f.addRow("Toestand", self.status_lbl)
        f.addRow(self.message)
        f.addRow(self.refresh_btn)
        lay.addWidget(st)

        pr = QGroupBox("Afdrukinstellingen")
        f2 = QFormLayout(pr)
        self.density = QComboBox()
        self.density.addItems(DENSITIES)
        self.copies = QSpinBox()
        self.copies.setRange(1, 99)
        self.test_btn = QPushButton("Testlabel afdrukken")
        self.cal_btn = QPushButton("Kalibratietest afdrukken")
        self.cal_settings_btn = QPushButton("Kalibratie-instellingen…")
        f2.addRow("Printdichtheid", self.density)
        f2.addRow("Exemplaren", self.copies)
        f2.addRow(self.test_btn)
        f2.addRow(self.cal_btn)
        f2.addRow(self.cal_settings_btn)
        lay.addWidget(pr)
        lay.addStretch(1)

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

    def remember_address(self, address: str) -> None:
        self._remembered = address

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
            mark = "🖨 " if d.supported else ""
            it = QListWidgetItem(f"{mark}{d.name}  ·  {d.address}  ·  {d.rssi} dBm")
            it.setData(Qt.ItemDataRole.UserRole, d.address)
            self.devices.addItem(it)
            if d.address == self._remembered or (self.devices.count() == 1 and d.supported):
                self.devices.setCurrentItem(it)

    def set_state(self, st: PrinterState) -> None:
        text, color = STATE_TEXT[st.connection]
        if st.simulated:
            text += " (simulatie)"
        self.state_lbl.setText(f"<span style='color:{color}'>●</span> {text}")
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
                self.battery.setFormat("onbekend")
            else:
                self.battery.setValue(info.battery)
                self.battery.setFormat("%p%")
            s = info.status
            color = "#2a2" if s.ok and not s.unknown else "#d22"
            self.status_lbl.setText(f"<span style='color:{color}'>{s.describe()}</span>")
        else:
            self.model_lbl.setText("–")
            self.battery.setValue(0)
            self.battery.setFormat("–")
            self.status_lbl.setText("–")
        self.message.setText(st.message)
        if st.devices is not self._last_devices:
            self._fill_devices(st.devices)
        if st.address:
            self._remembered = st.address
