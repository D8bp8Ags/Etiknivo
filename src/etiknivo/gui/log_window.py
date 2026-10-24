"""Log window: the application log, live, without digging in folders."""

from __future__ import annotations

import html

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui import theme
from etiknivo.logging_setup import LogEntry, MemoryLog, memory_log
from etiknivo.settings import log_dir

FILTERS = {"all": "Alles", "problems": "Waarschuwingen en fouten", "print": "Printopdrachten"}


class _Relay(QObject):
    """Moves log entries from any thread to the GUI thread."""

    entry = Signal(object)


class LogWindow(QDialog):
    def __init__(self, log: MemoryLog | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Log")
        self.resize(820, 480)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.log = log or memory_log()

        self.filter = QComboBox()
        for key, text in FILTERS.items():
            self.filter.addItem(text, key)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Zoeken in log…")
        self.search.setClearButtonEnabled(True)
        self.count = QLabel()
        self.count.setObjectName("muted")
        top = QHBoxLayout()
        top.addWidget(self.filter)
        top.addWidget(self.search, 1)
        top.addWidget(self.count)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.view.setMaximumBlockCount(5000)

        hint = QLabel("Bewaard in app.log en print.log, ook na afsluiten of een crash.")
        hint.setObjectName("hint")
        self.copy_btn = QPushButton("Kopiëren")
        self.copy_btn.setToolTip("Zichtbare regels naar het klembord, bv. voor een foutmelding")
        folder = QPushButton("Logmap openen")
        clear = QPushButton("Wissen")
        clear.setToolTip("Leegt dit venster; de logbestanden blijven bewaard")
        close = QPushButton("Sluiten")
        bottom = QHBoxLayout()
        bottom.addWidget(hint, 1)
        for b in (self.copy_btn, folder, clear, close):
            bottom.addWidget(b)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.view, 1)
        lay.addLayout(bottom)

        self.filter.currentIndexChanged.connect(self.reload)
        self.search.textChanged.connect(self.reload)
        self.copy_btn.clicked.connect(self.copy)
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir()))))
        clear.clicked.connect(self.clear)
        close.clicked.connect(self.close)

        self._relay = _Relay(self)
        self._relay.entry.connect(self._append, Qt.ConnectionType.QueuedConnection)
        self._listener = self._relay.entry.emit
        self.log.listeners.append(self._listener)
        self.reload()

    # -- filtering ---------------------------------------------------------------------

    def _wanted(self, e: LogEntry) -> bool:
        mode = self.filter.currentData()
        if mode == "problems" and e.level < 30:  # logging.WARNING
            return False
        if mode == "print" and not e.is_print:
            return False
        needle = self.search.text().strip().casefold()
        return not needle or needle in e.format().casefold()

    def _html(self, e: LogEntry) -> str:
        t = theme.tokens()
        color = t.danger if e.level >= 40 else t.warning if e.level >= 30 else (
            t.success if e.is_print else t.text)
        return f"<span style='color:{color}; white-space:pre'>{html.escape(e.format())}</span>"

    def reload(self) -> None:
        self.view.clear()
        shown = [e for e in self.log.snapshot() if self._wanted(e)]
        for e in shown:
            self.view.appendHtml(self._html(e))
        self._shown = len(shown)
        self._update_count()
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def _append(self, e: LogEntry) -> None:
        if not self._wanted(e):
            return
        bar = self.view.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        self.view.appendHtml(self._html(e))
        self._shown += 1
        self._update_count()
        if at_end:
            bar.setValue(bar.maximum())

    def _update_count(self) -> None:
        self.count.setText(f"{self._shown} regels")

    # -- actions -----------------------------------------------------------------------

    def visible_text(self) -> str:
        return "\n".join(e.format() for e in self.log.snapshot() if self._wanted(e))

    def copy(self) -> None:
        QApplication.clipboard().setText(self.visible_text())
        self.copy_btn.setText("Gekopieerd ✓")

    def clear(self) -> None:
        self.log.clear()
        self.reload()

    def done(self, result: int) -> None:  # also runs on close
        if self._listener in self.log.listeners:
            self.log.listeners.remove(self._listener)
        super().done(result)
