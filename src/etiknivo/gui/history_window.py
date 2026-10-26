"""Print history window: what was printed when, and printing it again."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui import theme
from etiknivo.i18n import format_datetime, tr
from etiknivo.storage.print_history import PrintHistory, PrintRecord


class HistoryWindow(QDialog):
    """Lists the print history, newest first.

    *exists* tells whether a label id is still in the library; records of
    deleted labels are greyed out and cannot be printed again.
    """

    reprintRequested = Signal(object)  # list[PrintRecord]

    def __init__(self, history: PrintHistory, exists: Callable[[str], bool],
                 densities: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Afdrukgeschiedenis"))
        self.resize(760, 480)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.history = history
        self.exists = exists
        self.densities = densities

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Zoeken op lade of naam…"))
        self.search.setClearButtonEnabled(True)
        self.hide_sim = QCheckBox(tr("Simulatie verbergen"))
        self.count = QLabel()
        self.count.setObjectName("muted")
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.hide_sim)
        top.addWidget(self.count)

        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setHeaderLabels([tr("Wanneer"), tr("Label"), tr("Exemplaren"),
                                   tr("Dichtheid"), tr("Printer")])
        header = self.tree.header()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        self.tree.setColumnWidth(0, 150)

        hint = QLabel(tr("Opnieuw afdrukken gebruikt het label zoals het nu is."))
        hint.setObjectName("hint")
        self.reprint_btn = QPushButton(tr("Opnieuw afdrukken…"))
        self.reprint_btn.setProperty("primary", True)
        clear = QPushButton(tr("Geschiedenis wissen…"))
        close = QPushButton(tr("Sluiten"))
        bottom = QHBoxLayout()
        bottom.addWidget(hint, 1)
        for b in (clear, self.reprint_btn, close):
            bottom.addWidget(b)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.tree, 1)
        lay.addLayout(bottom)

        self.search.textChanged.connect(self.reload)
        self.hide_sim.toggled.connect(self.reload)
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        self.tree.itemDoubleClicked.connect(lambda *_: self.reprint())
        self.reprint_btn.clicked.connect(self.reprint)
        clear.clicked.connect(self.ask_clear)
        close.clicked.connect(self.close)
        self.reload()

    # -- list ----------------------------------------------------------------------------

    def _wanted(self, r: PrintRecord) -> bool:
        if self.hide_sim.isChecked() and r.simulated:
            return False
        needle = self.search.text().strip().casefold()
        return not needle or needle in r.title.casefold()

    def reload(self) -> None:
        self.tree.clear()
        muted = QColor(theme.tokens().muted)
        shown = [r for r in self.history.newest_first() if self._wanted(r)]
        for r in shown:
            gone = not self.exists(r.label_id)
            density = self.densities[r.density] if 0 <= r.density < len(self.densities) \
                else str(r.density)
            item = QTreeWidgetItem([
                format_datetime(r.when),
                r.title + (" " + tr("(verwijderd)") if gone else ""),
                str(r.copies), density,
                tr("Simulatie") if r.simulated else tr("Printer")])
            item.setData(0, Qt.ItemDataRole.UserRole, r)
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if gone:
                for col in range(5):
                    item.setForeground(col, muted)
            self.tree.addTopLevelItem(item)
        labels = sum(r.copies for r in shown)
        self.count.setText(tr("{n} opdrachten, {m} etiketten", n=len(shown), m=labels))
        self._update_buttons()

    def selected(self) -> list[PrintRecord]:
        """Selected records that can be printed again, oldest first, one per label."""
        recs = [it.data(0, Qt.ItemDataRole.UserRole) for it in self.tree.selectedItems()]
        recs.sort(key=lambda r: r.time)
        seen: dict[str, PrintRecord] = {}
        for r in recs:
            if self.exists(r.label_id):
                seen.pop(r.label_id, None)
                seen[r.label_id] = r  # the newest record of a label wins
        return list(seen.values())

    def _update_buttons(self) -> None:
        self.reprint_btn.setEnabled(bool(self.selected()))

    # -- actions -----------------------------------------------------------------------

    def reprint(self) -> None:
        recs = self.selected()
        if recs:
            self.reprintRequested.emit(recs)

    def ask_clear(self) -> None:
        if not self.history.records:
            return
        if QMessageBox.question(self, tr("Geschiedenis wissen"),
                                tr("De hele afdrukgeschiedenis wissen?")) \
                == QMessageBox.StandardButton.Yes:
            self.history.clear()
            self.reload()
