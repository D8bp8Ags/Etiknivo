"""'Labels bewerken': every label as a row of a table, to change many at once."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QItemSelectionModel, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui import theme
from etiknivo.i18n import N_, tr
from etiknivo.model import SLOT_BOTTOM, SLOT_MAIN, SLOT_TOP, Label

#: (column title, read the value from a label, write it to a label)
Column = tuple[str, Callable[[Label], str], Callable[[Label, str], None]]


def _set_line(slot: int) -> Callable[[Label, str], None]:
    def write(lbl: Label, text: str) -> None:
        lbl.lines[slot].text = text
    return write


def _set(attr: str) -> Callable[[Label, str], None]:
    def write(lbl: Label, text: str) -> None:
        setattr(lbl, attr, text.strip())
    return write


COLUMNS: tuple[Column, ...] = (
    (N_("Naam"), lambda lbl: lbl.name, _set("name")),
    (N_("Lade-ID"), lambda lbl: lbl.tray_id, _set("tray_id")),
    (N_("Categorie"), lambda lbl: lbl.category, _set("category")),
    (N_("Bovenregel"), lambda lbl: lbl.lines[SLOT_TOP].text, _set_line(SLOT_TOP)),
    (N_("Hoofdregel"), lambda lbl: lbl.lines[SLOT_MAIN].text, _set_line(SLOT_MAIN)),
    (N_("Onderregel"), lambda lbl: lbl.lines[SLOT_BOTTOM].text, _set_line(SLOT_BOTTOM)),
)
CATEGORY_COLUMN = 2


class _CategoryDelegate(QStyledItemDelegate):
    """Edits the category in a list of every category, open at once after a
    double-click; typing a new name still works."""

    def __init__(self, categories: Callable[[], list[str]], parent: QWidget) -> None:
        super().__init__(parent)
        self._categories = categories
        self._open_list = False

    def editorEvent(self, event, model, option, index):  # type: ignore[no-untyped-def]  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonDblClick:
            self._open_list = True
        return super().editorEvent(event, model, option, index)

    def createEditor(self, parent, option, index):  # type: ignore[no-untyped-def]  # noqa: N802
        editor = QComboBox(parent)
        editor.setEditable(True)
        editor.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        editor.setMaxVisibleItems(20)
        editor.addItems(self._categories())
        editor.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        editor.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        if self._open_list:  # a double-click shows the choice; typing just types
            self._open_list = False
            QTimer.singleShot(0, editor.showPopup)
        return editor

    def setEditorData(self, editor, index):  # type: ignore[no-untyped-def]  # noqa: N802
        editor.setCurrentText(index.data() or "")

    def setModelData(self, editor, model, index):  # type: ignore[no-untyped-def]  # noqa: N802
        model.setData(index, editor.currentText().strip())


class BulkEditDialog(QDialog):
    """All labels in a table.  A value typed while several rows are selected
    goes to every selected row; nothing changes until 'Toepassen'."""

    def __init__(self, labels: list[Label], categories: list[str],
                 selected: set[str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Labels bewerken"))
        self.resize(1000, 640)
        self._labels = [lbl.clone(new_id=False) for lbl in labels]
        self._original = {lbl.id: [col[1](lbl) for col in COLUMNS] for lbl in labels}
        self._spreading = False

        lay = QVBoxLayout(self)
        intro = QLabel(tr("Dubbelklik een cel om hem te wijzigen. Selecteer meerdere rijen "
                          "(Shift-klik) en typ een waarde: alle geselecteerde labels krijgen "
                          "hem. Velden zoals {Lade} werken ook hier."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Zoeken in labels…"))
        self.search.setClearButtonEnabled(True)
        lay.addWidget(self.search)

        self.table = QTableWidget(len(self._labels), len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(col[0]) for col in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.verticalHeader().setVisible(False)
        self._categories = categories
        self.table.setItemDelegateForColumn(CATEGORY_COLUMN,
                                            _CategoryDelegate(self._category_list, self.table))
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        head.setStretchLastSection(True)
        for row, lbl in enumerate(self._labels):
            for col, (_title, read, _write) in enumerate(COLUMNS):
                item = QTableWidgetItem(read(lbl))
                item.setData(Qt.ItemDataRole.UserRole, lbl.id)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        for col in range(len(COLUMNS)):
            self.table.setColumnWidth(col, min(220, self.table.columnWidth(col) + 12))
        if selected:  # start with the labels selected in the library
            model, flags = self.table.selectionModel(), (
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows)
            for row, lbl in enumerate(self._labels):
                if lbl.id in selected:
                    model.select(self.table.model().index(row, 0), flags)
        lay.addWidget(self.table, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.ok = bb.addButton(tr("Toepassen"), QDialogButtonBox.ButtonRole.AcceptRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.table.itemChanged.connect(self._changed)
        self.search.textChanged.connect(self._filter)
        self._update()

    # -- results ----------------------------------------------------------------------

    def changes(self) -> dict[str, Label]:
        """{label id: the edited label} for every label with a changed cell."""
        out: dict[str, Label] = {}
        for lbl in self._labels:
            if [col[1](lbl) for col in COLUMNS] != self._original[lbl.id]:
                out[lbl.id] = lbl
        return out

    def set_cell(self, row: int, column: int, text: str) -> None:
        """Type *text* into a cell, as if edited (it spreads over the selection)."""
        self.table.item(row, column).setText(text)

    # -- helpers ----------------------------------------------------------------------

    def _category_list(self) -> list[str]:
        """The library's categories plus any typed in the table so far."""
        typed = {lbl.category for lbl in self._labels if lbl.category}
        return sorted(set(self._categories) | typed, key=str.casefold)

    def _changed(self, item: QTableWidgetItem) -> None:
        if self._spreading:
            return
        text, col = item.text(), item.column()
        rows = {i.row() for i in self.table.selectedItems()}
        targets = rows if item.row() in rows else {item.row()}
        self._spreading = True
        try:
            for row in targets:
                cell = self.table.item(row, col)
                if self.table.isRowHidden(row):
                    continue
                if cell.text() != text:
                    cell.setText(text)
                COLUMNS[col][2](self._labels[row], text)
        finally:
            self._spreading = False
        self._update()

    def _filter(self, text: str) -> None:
        needle = text.casefold().strip()
        for row in range(self.table.rowCount()):
            hay = " ".join(self.table.item(row, c).text() for c in range(len(COLUMNS)))
            self.table.setRowHidden(row, bool(needle) and needle not in hay.casefold())

    def _update(self) -> None:
        changed = self.changes()
        self.ok.setText(tr("Toepassen op {n} label(s)", n=len(changed)))
        self.ok.setEnabled(bool(changed))
        accent = QColor(theme.tokens().accent)
        normal = self.palette().text().color()
        self._spreading = True
        try:
            for row, lbl in enumerate(self._labels):
                values = [col[1](lbl) for col in COLUMNS]
                for col, value in enumerate(values):
                    edited = value != self._original[lbl.id][col]
                    self.table.item(row, col).setForeground(accent if edited else normal)
        finally:
            self._spreading = False
