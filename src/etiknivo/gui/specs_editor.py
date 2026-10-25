"""Specifications of a label as a small table: name | value | { }.

The name is what a text line refers to as ``{Name}``; the value is what the
label then shows.  The ``{ }`` button of a row puts that field in a text line,
so nobody has to guess where the braces go.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from etiknivo.i18n import tr
from etiknivo.model import FIELD_RE, spec_name

ROW_H = 28
VISIBLE_ROWS = (3, 6)  # the table grows with its rows between these, then scrolls


class SpecsEditor(QWidget):
    """Edits ``Label.specs`` and emits :attr:`changed` after every edit."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        #: (title, insert function) per place a field can go, asked when the menu opens
        self.targets: Callable[[], list[tuple[str, Callable[[str], None] | None]]] = list
        self._loading = False
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Naam"), tr("Waarde"), ""])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(ROW_H)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        head.resizeSection(2, 44)
        self.add_btn = QToolButton()
        self.add_btn.setText(tr("+ Specificatie"))
        self.add_btn.setToolTip(tr("Nieuwe specificatie, bv. Spanning met de waarde 50 V"))
        self.del_btn = QToolButton()
        self.del_btn.setText(tr("Verwijderen"))
        self.del_btn.setToolTip(tr("Geselecteerde specificatie verwijderen"))
        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.del_btn)
        buttons.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.table)
        lay.addLayout(buttons)
        self.warning = QLabel(tr("Een {veld} in een waarde wordt niet ingevuld: typ de waarde "
                                 "zelf, bv. 50 V."))
        self.warning.setWordWrap(True)
        self.warning.setObjectName("warnHint")
        self.warning.hide()
        lay.addWidget(self.warning)

        self.add_btn.clicked.connect(self.add_row)
        self.del_btn.clicked.connect(self.delete_row)
        self.table.itemChanged.connect(self._edited)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self._fit_height()
        self._update_buttons()

    # -- data -------------------------------------------------------------------------

    def specs(self) -> dict[str, str]:
        """The rows as a dict; rows without a name are left out."""
        out: dict[str, str] = {}
        for row in range(self.table.rowCount()):
            name = spec_name(self._text(row, 0))
            if name:
                out[name] = self._text(row, 1).strip()
        return out

    def set_specs(self, specs: dict[str, str]) -> None:
        """Show *specs*; leaves the table alone when it already shows them, so
        a row being typed in is not reset."""
        if specs == self.specs():
            return
        self._loading = True
        try:
            self.table.setRowCount(0)
            for name, value in specs.items():
                self._append(name, value)
        finally:
            self._loading = False
        self._fit_height()
        self._update_buttons()
        self._update_warning()

    def _text(self, row: int, col: int) -> str:
        item = self.table.item(row, col)
        return item.text() if item is not None else ""

    # -- editing ----------------------------------------------------------------------

    def _append(self, name: str, value: str) -> int:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(value))
        btn = QToolButton()
        btn.setText("{ }")
        btn.setObjectName("cellButton")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(btn)
        menu.aboutToShow.connect(lambda b=btn, m=menu: self._fill_menu(b, m))
        btn.setMenu(menu)
        self.table.setCellWidget(row, 2, btn)
        self._update_tooltip(row)
        return row

    def _row_of(self, button: QToolButton) -> int:
        return next((r for r in range(self.table.rowCount())
                     if self.table.cellWidget(r, 2) is button), -1)

    def _fill_menu(self, button: QToolButton, menu: QMenu) -> None:
        menu.clear()
        name = spec_name(self._text(self._row_of(button), 0))
        if not name:
            menu.addAction(tr("Geef de specificatie eerst een naam")).setEnabled(False)
            return
        menu.addSection(f"{{{name}}}")
        for title, insert in self.targets():
            act = menu.addAction(tr("In {place} zetten", place=title))
            if insert is None:
                act.setEnabled(False)
            else:
                act.triggered.connect(lambda _c=False, f=insert: f(name))

    def _update_tooltip(self, row: int) -> None:
        btn = self.table.cellWidget(row, 2)
        if btn is None:
            return
        name = spec_name(self._text(row, 0))
        btn.setToolTip(tr("{field} op het etiket zetten", field=f"{{{name}}}") if name
                       else tr("Geef de specificatie eerst een naam"))

    def add_row(self) -> None:
        self._loading = True
        try:
            row = self._append("", "")
        finally:
            self._loading = False
        self._fit_height()
        self.table.setCurrentCell(row, 0)
        self.table.editItem(self.table.item(row, 0))

    def delete_row(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        had_name = bool(spec_name(self._text(row, 0)))
        self.table.removeRow(row)
        self._fit_height()
        self._update_buttons()
        self._update_warning()
        if had_name:
            self.changed.emit()

    def _edited(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        self._update_tooltip(item.row())
        self._update_warning()
        self.changed.emit()

    def _update_warning(self) -> None:
        self.warning.setVisible(any(FIELD_RE.search(self._text(r, 1))
                                    for r in range(self.table.rowCount())))

    def _update_buttons(self) -> None:
        self.del_btn.setEnabled(self.table.currentRow() >= 0
                                and bool(self.table.selectedItems()))

    def _fit_height(self) -> None:
        lo, hi = VISIBLE_ROWS
        rows = min(hi, max(lo, self.table.rowCount()))
        frame = 2 * self.table.frameWidth()
        self.table.setFixedHeight(self.table.horizontalHeader().sizeHint().height()
                                  + rows * ROW_H + frame)
