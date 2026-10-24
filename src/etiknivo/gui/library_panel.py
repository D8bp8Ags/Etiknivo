"""Left panel: the label library."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui.qt_util import pil_to_pixmap
from etiknivo.model import Label
from etiknivo.rendering.engine import RenderEngine
from etiknivo.storage.library import Library

ID_ROLE = Qt.ItemDataRole.UserRole + 1
ALL_CATEGORIES = "Alle categorieën"
SORT_KEYS: dict[str, tuple[str, Callable[[Label], object]]] = {
    "tray_id": ("Lade-ID", lambda lbl: (lbl.tray_id == "", lbl.tray_id.casefold(), lbl.name)),
    "name": ("Naam", lambda lbl: lbl.name.casefold()),
    "category": ("Categorie", lambda lbl: (lbl.category.casefold(), lbl.tray_id.casefold())),
    "modified": ("Laatst gewijzigd", lambda lbl: lbl.modified),
}
THUMB = QSize(86, 40)


class LibraryPanel(QWidget):
    currentLabelChanged = Signal(str)  # label id ('' when none)
    selectionChanged = Signal(list)  # list[str] of label ids
    newRequested = Signal()
    duplicateRequested = Signal()
    renameRequested = Signal()
    deleteRequested = Signal()
    printSelectedRequested = Signal()
    exportPngRequested = Signal()

    def __init__(self, library: Library, engine: RenderEngine, parent: QWidget | None = None):
        super().__init__(parent)
        self.library = library
        self.engine = engine
        self._thumbs: dict[str, tuple[str, QIcon]] = {}
        self._building = False

        title = QLabel("<b>Labelbibliotheek</b>")
        self.search = QLineEdit(placeholderText="Zoeken op naam, tekst, lade-ID…")
        self.search.setClearButtonEnabled(True)
        self.category = QComboBox()
        self.sort = QComboBox()
        for key, (text, _fn) in SORT_KEYS.items():
            self.sort.addItem(f"Sorteer: {text}", key)
        self.descending = QCheckBox("Aflopend")
        self.group = QCheckBox("Groeperen per categorie")
        self.group.setChecked(True)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Voorbeeld", "Naam", "Lade", "Categorie"])
        self.tree.setIconSize(THUMB)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(0, THUMB.width() + 34)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(False)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.count = QLabel()
        self.count.setStyleSheet("color: palette(mid);")

        b_new = QPushButton("Nieuw")
        b_dup = QPushButton("Dupliceren")
        b_ren = QPushButton("Hernoemen")
        b_del = QPushButton("Verwijderen")
        b_new.clicked.connect(self.newRequested)
        b_dup.clicked.connect(self.duplicateRequested)
        b_ren.clicked.connect(self.renameRequested)
        b_del.clicked.connect(self.deleteRequested)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(title)
        lay.addWidget(self.search)
        row = QHBoxLayout()
        row.addWidget(self.category, 1)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(self.sort, 1)
        row2.addWidget(self.descending)
        lay.addLayout(row2)
        lay.addWidget(self.group)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.count)
        btns = QHBoxLayout()
        for b in (b_new, b_dup, b_ren, b_del):
            btns.addWidget(b)
        lay.addLayout(btns)

        self.search.textChanged.connect(self.refresh)
        self.category.currentIndexChanged.connect(self.refresh)
        self.sort.currentIndexChanged.connect(self.refresh)
        self.descending.toggled.connect(self.refresh)
        self.group.toggled.connect(self.refresh)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        self.tree.customContextMenuRequested.connect(self._context_menu)

        act_del = QAction(self.tree)
        act_del.setShortcut(QKeySequence.StandardKey.Delete)
        act_del.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        act_del.triggered.connect(self.deleteRequested)
        self.tree.addAction(act_del)

        self.refresh()

    # -- view state -------------------------------------------------------------------

    def set_sort_key(self, key: str) -> None:
        i = self.sort.findData(key)
        if i >= 0:
            self.sort.setCurrentIndex(i)

    def sort_key(self) -> str:
        return str(self.sort.currentData())

    def selected_ids(self) -> list[str]:
        ids = [it.data(0, ID_ROLE) for it in self.tree.selectedItems()]
        return [i for i in ids if i]

    def current_id(self) -> str:
        it = self.tree.currentItem()
        return (it.data(0, ID_ROLE) or "") if it else ""

    def visible_ids(self) -> list[str]:
        out = []

        def walk(item: QTreeWidgetItem) -> None:
            lid = item.data(0, ID_ROLE)
            if lid:
                out.append(lid)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out

    def select_ids(self, ids: list[str], current: str | None = None) -> None:
        wanted = set(ids)
        self._building = True
        self.tree.clearSelection()
        cur_item = None
        for it in self._iter_items():
            lid = it.data(0, ID_ROLE)
            if lid in wanted:
                it.setSelected(True)
                if lid == (current or (ids[0] if ids else None)):
                    cur_item = it
        self._building = False
        if cur_item is not None:
            self.tree.setCurrentItem(cur_item, 0,
                                     self.tree.selectionModel().SelectionFlag.NoUpdate)
            self.tree.scrollToItem(cur_item)
        self._on_selection()

    def _iter_items(self):  # type: ignore[no-untyped-def]
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            it = stack.pop()
            yield it
            stack.extend(it.child(i) for i in range(it.childCount()))

    # -- building -----------------------------------------------------------------------

    def _matches(self, lbl: Label, needle: str, category: str | None) -> bool:
        if category and lbl.category != category:
            return False
        if not needle:
            return True
        hay = " ".join([lbl.name, lbl.tray_id, lbl.category, lbl.notes,
                        *(ln.text for ln in lbl.lines), *lbl.specs.values()]).casefold()
        return all(part in hay for part in needle.casefold().split())

    def thumbnail(self, lbl: Label) -> QIcon:
        key = lbl.render_key()
        hit = self._thumbs.get(lbl.id)
        if hit and hit[0] == key:
            return hit[1]
        img = self.engine.render(lbl).mono.convert("L")
        pm = pil_to_pixmap(img).scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
        icon = QIcon(pm)
        self._thumbs[lbl.id] = (key, icon)
        return icon

    def invalidate_thumbnails(self) -> None:
        self._thumbs.clear()

    def refresh(self) -> None:
        """Rebuild the tree, keeping selection and filters."""
        keep_sel = self.selected_ids()
        keep_cur = self.current_id()
        self._building = True
        # category filter
        cats = self.library.categories()
        cur_cat = self.category.currentText()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem(ALL_CATEGORIES)
        self.category.addItems(cats)
        idx = self.category.findText(cur_cat)
        self.category.setCurrentIndex(idx if idx >= 0 else 0)
        self.category.blockSignals(False)
        cat_filter = None if self.category.currentIndex() <= 0 else self.category.currentText()

        _, keyfn = SORT_KEYS.get(self.sort_key(), SORT_KEYS["tray_id"])
        labels = [lbl for lbl in self.library if self._matches(lbl, self.search.text().strip(),
                                                              cat_filter)]
        labels.sort(key=keyfn, reverse=self.descending.isChecked())

        self.tree.clear()
        if self.group.isChecked():
            groups: dict[str, list[Label]] = {}
            for lbl in labels:
                groups.setdefault(lbl.category or "(zonder categorie)", []).append(lbl)
            for cat in sorted(groups, key=str.casefold, reverse=self.descending.isChecked()):
                head = QTreeWidgetItem([f"{cat}  ({len(groups[cat])})"])
                head.setFlags(Qt.ItemFlag.ItemIsEnabled)
                f = head.font(0)
                f.setBold(True)
                head.setFont(0, f)
                self.tree.addTopLevelItem(head)
                for lbl in groups[cat]:
                    head.addChild(self._make_item(lbl))
                head.setFirstColumnSpanned(True)
                head.setExpanded(True)
        else:
            for lbl in labels:
                self.tree.addTopLevelItem(self._make_item(lbl))
        self.count.setText(f"{len(labels)} van {len(self.library)} labels")
        self._building = False
        self.select_ids([i for i in keep_sel if self.library.get(i)], keep_cur or None)

    def _make_item(self, lbl: Label) -> QTreeWidgetItem:
        it = QTreeWidgetItem(["", lbl.name, lbl.tray_id, lbl.category])
        it.setData(0, ID_ROLE, lbl.id)
        it.setIcon(0, self.thumbnail(lbl))
        it.setSizeHint(0, QSize(THUMB.width(), THUMB.height() + 6))
        it.setToolTip(1, "\n".join(ln.text for _, ln in lbl.visible_lines()))
        return it

    def update_label(self, lbl: Label) -> None:
        """Cheap in-place update of one row (no rebuild)."""
        for it in self._iter_items():
            if it.data(0, ID_ROLE) == lbl.id:
                it.setText(1, lbl.name)
                it.setText(2, lbl.tray_id)
                it.setText(3, lbl.category)
                it.setIcon(0, self.thumbnail(lbl))
                it.setToolTip(1, "\n".join(ln.text for _, ln in lbl.visible_lines()))
                return

    # -- events -------------------------------------------------------------------------

    def _on_selection(self) -> None:
        if self._building:
            return
        ids = self.selected_ids()
        self.selectionChanged.emit(ids)
        cur = self.current_id()
        if cur not in ids and ids:
            cur = ids[0]
        self.currentLabelChanged.emit(cur if ids else "")

    def _context_menu(self, pos) -> None:  # noqa: ANN001
        m = QMenu(self)
        m.addAction("Nieuw label", self.newRequested.emit)
        if self.selected_ids():
            m.addAction("Dupliceren", self.duplicateRequested.emit)
            m.addAction("Hernoemen…", self.renameRequested.emit)
            m.addAction("Verwijderen", self.deleteRequested.emit)
            m.addSeparator()
            m.addAction("Selectie afdrukken…", self.printSelectedRequested.emit)
            m.addAction("Selectie exporteren als PNG…", self.exportPngRequested.emit)
        m.exec(self.tree.viewport().mapToGlobal(pos))
