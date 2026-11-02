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
from etiknivo.gui.qt_util import remember_size
from etiknivo.i18n import N_, tr
from etiknivo.model import SLOT_BOTTOM, SLOT_MAIN, SLOT_TOP, CodeSize, HAlign, Label, VAlign

#: The size choices as the table shows them, as in the properties panel
SIZE_NAMES: tuple[tuple[CodeSize, str], ...] = (
    (CodeSize.SMALL, N_("Klein")), (CodeSize.MEDIUM, N_("Middel")), (CodeSize.LARGE, N_("Groot")))

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

#: The places beside the text, as in the properties panel
POSITION_NAMES: tuple[tuple[HAlign, VAlign, str], ...] = (
    (HAlign.LEFT, VAlign.TOP, N_("Links boven")),
    (HAlign.LEFT, VAlign.CENTER, N_("Links midden")),
    (HAlign.LEFT, VAlign.BOTTOM, N_("Links onder")),
    (HAlign.RIGHT, VAlign.TOP, N_("Rechts boven")),
    (HAlign.RIGHT, VAlign.CENTER, N_("Rechts midden")),
    (HAlign.RIGHT, VAlign.BOTTOM, N_("Rechts onder")),
)


def _position_name(part: object) -> str:
    return next(tr(name) for side, valign, name in POSITION_NAMES
                if (side, valign) == (part.side, part.valign))  # type: ignore[attr-defined]


def _set_position(part: str) -> Callable[[Label, str], None]:
    """Write a position name to the label's pictogram or QR code; anything
    else leaves it as it is."""
    def write(lbl: Label, text: str) -> None:
        for side, valign, name in POSITION_NAMES:
            if text.strip().casefold() == tr(name).casefold():
                getattr(lbl, part).side, getattr(lbl, part).valign = side, valign
    return write


def _size_name(size: CodeSize) -> str:
    return next(tr(name) for value, name in SIZE_NAMES if value == size)


def _set_size(part: str) -> Callable[[Label, str], None]:
    """Write a size name (in the current language) to the label's pictogram or
    QR code; anything else leaves it as it is."""
    def write(lbl: Label, text: str) -> None:
        for value, name in SIZE_NAMES:
            if text.strip().casefold() in (tr(name).casefold(), value.value):
                getattr(lbl, part).size = value
    return write


COLUMNS: tuple[Column, ...] = (
    (N_("Naam"), lambda lbl: lbl.name, _set("name")),
    (N_("Lade-ID"), lambda lbl: lbl.tray_id, _set("tray_id")),
    (N_("Categorie"), lambda lbl: lbl.category, _set("category")),
    (N_("Bovenregel"), lambda lbl: lbl.lines[SLOT_TOP].text, _set_line(SLOT_TOP)),
    (N_("Hoofdregel"), lambda lbl: lbl.lines[SLOT_MAIN].text, _set_line(SLOT_MAIN)),
    (N_("Onderregel"), lambda lbl: lbl.lines[SLOT_BOTTOM].text, _set_line(SLOT_BOTTOM)),
    (N_("Pictogramgrootte"), lambda lbl: _size_name(lbl.picture.size), _set_size("picture")),
    (N_("Pictogrampositie"), lambda lbl: _position_name(lbl.picture), _set_position("picture")),
    (N_("QR-grootte"), lambda lbl: _size_name(lbl.code.size), _set_size("code")),
    (N_("QR-positie"), lambda lbl: _position_name(lbl.code), _set_position("code")),
)
CATEGORY_COLUMN = 2
SIZE_COLUMNS = (6, 8)  # pictogram, QR code
POSITION_COLUMNS = (7, 9)


class _ChoiceDelegate(QStyledItemDelegate):
    """Picks one of a few fixed values from a list that opens at once."""

    def __init__(self, names: list[str], parent: QWidget) -> None:
        super().__init__(parent)
        self._names = names

    def createEditor(self, parent, option, index):  # type: ignore[no-untyped-def]  # noqa: N802
        editor = QComboBox(parent)
        editor.addItems([tr(name) for name in self._names])
        editor.activated.connect(lambda _i: self.commitData.emit(editor))
        QTimer.singleShot(0, editor.showPopup)
        return editor

    def setEditorData(self, editor, index):  # type: ignore[no-untyped-def]  # noqa: N802
        editor.setCurrentText(index.data() or "")

    def setModelData(self, editor, model, index):  # type: ignore[no-untyped-def]  # noqa: N802
        model.setData(index, editor.currentText())


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
                          "hem. Velden zoals {Lade} werken ook hier. Grootte en positie gelden "
                          "voor het pictogram en de QR-code, ook als je die later pas toevoegt."))
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
        sizes = [name for _value, name in SIZE_NAMES]
        places = [name for _side, _valign, name in POSITION_NAMES]
        for col in SIZE_COLUMNS:
            self.table.setItemDelegateForColumn(col, _ChoiceDelegate(sizes, self.table))
        for col in POSITION_COLUMNS:
            self.table.setItemDelegateForColumn(col, _ChoiceDelegate(places, self.table))
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
        remember_size(self, "edit_labels", head)
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
                COLUMNS[col][2](self._labels[row], text)
                shown = COLUMNS[col][1](self._labels[row])  # sizes: an unknown word stays
                if cell.text() != shown:
                    cell.setText(shown)
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
