"""Left panel: the label library."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QModelIndex, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui import theme
from etiknivo.gui.qt_util import pil_to_pixmap
from etiknivo.gui.widgets import combo
from etiknivo.i18n import N_, tr
from etiknivo.model import ElementKind, Label
from etiknivo.rendering.engine import RenderEngine
from etiknivo.storage.library import Library

ID_ROLE = Qt.ItemDataRole.UserRole + 1
SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 2
HEADER_ROLE = Qt.ItemDataRole.UserRole + 3
DIRTY_ROLE = Qt.ItemDataRole.UserRole + 4  # label has unsaved changes
ALL_CATEGORIES = N_("Alle categorieën")  # always the first filter entry
SORT_KEYS: dict[str, tuple[str, Callable[[Label], object]]] = {
    "tray_id": (N_("Lade-ID"), lambda lbl: (lbl.tray_id == "", lbl.tray_id.casefold(), lbl.name)),
    "name": (N_("Naam"), lambda lbl: lbl.name.casefold()),
    "category": (N_("Categorie"), lambda lbl: (lbl.category.casefold(), lbl.tray_id.casefold())),
    "modified": (N_("Laatst gewijzigd"), lambda lbl: lbl.modified),
}
THUMB = QSize(86, 40)
ROW_H = THUMB.height() + 16
HEADER_H = 30


def _scaled(font: QFont, factor: float) -> QFont:
    f = QFont(font)
    if f.pixelSize() > 0:
        f.setPixelSize(max(8, round(f.pixelSize() * factor)))
    else:
        f.setPointSizeF(max(6.0, f.pointSizeF() * factor))
    return f


class LabelCardDelegate(QStyledItemDelegate):
    """Paints library rows as cards (thumbnail, name, tray · category) and
    category rows as small section headings."""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), HEADER_H if index.data(HEADER_ROLE) else ROW_H)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        t = theme.tokens()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRect(option.rect)
        if index.data(HEADER_ROLE):
            f = _scaled(option.font, 0.85)
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            p.setPen(QColor(t.muted))
            p.drawText(r.adjusted(14, 8, -14, 0), Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter, str(index.data(Qt.ItemDataRole.DisplayRole)))
            p.restore()
            return
        card = QRectF(r.adjusted(6, 2, -6, -2))
        if option.state & QStyle.StateFlag.State_Selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.selection))
            p.drawRoundedRect(card, 8, 8)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.hover))
            p.drawRoundedRect(card, 8, 8)
        # thumbnail on a small piece of "paper"
        thumb = QRectF(card.left() + 8, card.top() + (card.height() - THUMB.height() - 4) / 2,
                       THUMB.width() + 4, THUMB.height() + 4)
        p.setPen(QPen(QColor(t.border), 1))
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(thumb, 4, 4)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon):
            icon.paint(p, thumb.adjusted(2, 2, -2, -2).toRect())
        # text
        x = int(thumb.right()) + 12
        text_r = QRect(x, int(card.top()), int(card.right()) - x - 8, int(card.height()))
        half = text_r.height() // 2
        if index.data(DIRTY_ROLE):  # unsaved changes: small accent dot after the name
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent))
            p.drawEllipse(QRectF(text_r.right() - 8, text_r.top() + half - 12, 8, 8))
            text_r.setRight(text_r.right() - 14)
        name_f = QFont(option.font)
        name_f.setWeight(QFont.Weight.DemiBold)
        sub_f = _scaled(option.font, 0.92)
        p.setFont(name_f)
        p.setPen(QColor(t.text))
        name = p.fontMetrics().elidedText(str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
                                          Qt.TextElideMode.ElideRight, text_r.width())
        p.drawText(text_r.adjusted(0, 0, 0, -half), Qt.AlignmentFlag.AlignLeft
                   | Qt.AlignmentFlag.AlignBottom, name)
        p.setFont(sub_f)
        p.setPen(QColor(t.muted))
        sub = p.fontMetrics().elidedText(str(index.data(SUBTITLE_ROLE) or ""),
                                         Qt.TextElideMode.ElideRight, text_r.width())
        p.drawText(text_r.adjusted(0, half + 2, 0, 0), Qt.AlignmentFlag.AlignLeft
                   | Qt.AlignmentFlag.AlignTop, sub)
        p.restore()


class LibraryPanel(QWidget):
    currentLabelChanged = Signal(str)  # label id ('' when none)
    selectionChanged = Signal(list)  # list[str] of label ids
    newRequested = Signal()
    duplicateRequested = Signal()
    copyFormatRequested = Signal()
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
        self._restoring = False
        self._explicit = False  # selection set by the program, not by a click
        self._last_ids: list[str] = []
        self._pinned = ""  # label being edited: stays visible even if the search no longer matches
        self._dirty = ""  # label with unsaved changes (dot in the list)

        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        title = QLabel(tr("Bibliotheek"))
        title.setObjectName("heading")
        self.count = QLabel()
        self.count.setObjectName("muted")
        self.search = QLineEdit(placeholderText=tr("Zoeken op naam, tekst, lade-ID…"))
        self.search.setClearButtonEnabled(True)
        self._search_icon = self.search.addAction(QIcon(), QLineEdit.ActionPosition.LeadingPosition)
        self.category = combo(11)
        self.sort = combo()
        self.sort.setToolTip(tr("Sorteren"))
        for key, (text, _fn) in SORT_KEYS.items():
            self.sort.addItem(tr(text), key)
        self.options = QToolButton()
        self.options.setToolTip(tr("Weergaveopties"))
        self.options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        opt_menu = QMenu(self.options)
        self.descending = QAction(tr("Aflopend sorteren"), self, checkable=True)
        self.group = QAction(tr("Groeperen per categorie"), self, checkable=True)
        self.group.setChecked(True)
        opt_menu.addAction(self.group)
        opt_menu.addAction(self.descending)
        self.options.setMenu(opt_menu)

        self.tree = QTreeWidget()
        self.tree.setObjectName("libraryList")
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)
        self.tree.setItemDelegate(LabelCardDelegate(self.tree))
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setRootIsDecorated(False)
        self.tree.setItemsExpandable(False)
        self.tree.setIndentation(0)
        self.tree.setUniformRowHeights(False)
        self.tree.setMouseTracking(True)
        self.tree.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 6, 8)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.count)
        lay.addLayout(head)
        lay.addWidget(self.search)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.category, 3)
        row.addWidget(self.sort, 2)
        row.addWidget(self.options)
        lay.addLayout(row)
        lay.addWidget(self.tree, 1)
        self.apply_theme()
        theme.manager().changed.connect(self.apply_theme)

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

    def apply_theme(self) -> None:
        self._search_icon.setIcon(theme.icon("search", theme.tokens().muted, 16))
        self.options.setIcon(theme.icon("sliders-horizontal"))
        self.tree.viewport().update()

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
        self._explicit = True
        try:
            self._on_selection()
        finally:
            self._explicit = False

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
        if not needle or lbl.id == self._pinned:
            return True
        hay = " ".join([lbl.name, lbl.tray_id, lbl.category, lbl.notes,
                        *(ln.text for ln in lbl.lines), *(e.text for e in lbl.elements),
                        *lbl.specs.values()]).casefold()
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
        self.category.addItem(tr(ALL_CATEGORIES))
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
                groups.setdefault(lbl.category or tr("(zonder categorie)"), []).append(lbl)
            for cat in sorted(groups, key=str.casefold, reverse=self.descending.isChecked()):
                head = QTreeWidgetItem([f"{cat}  ·  {len(groups[cat])}"])
                head.setFlags(Qt.ItemFlag.ItemIsEnabled)
                head.setData(0, HEADER_ROLE, True)
                self.tree.addTopLevelItem(head)
                for lbl in groups[cat]:
                    head.addChild(self._make_item(lbl))
                head.setExpanded(True)
        else:
            for lbl in labels:
                self.tree.addTopLevelItem(self._make_item(lbl))
        self.count.setText(tr("{n} van {total}", n=len(labels), total=len(self.library))
                           if len(labels) != len(self.library)
                           else tr("{n} labels", n=len(labels)))
        self._building = False
        self._restoring = True  # restoring the old selection must not drop the pin
        try:
            self.select_ids([i for i in keep_sel if self.library.get(i)], keep_cur or None)
        finally:
            self._restoring = False

    @staticmethod
    def _subtitle(lbl: Label) -> str:
        return "  ·  ".join(x for x in (lbl.tray_id, lbl.category) if x) or "—"

    def _fill_item(self, it: QTreeWidgetItem, lbl: Label) -> None:
        it.setText(0, lbl.name)
        it.setData(0, DIRTY_ROLE, lbl.id == self._dirty)
        it.setData(0, SUBTITLE_ROLE, self._subtitle(lbl))
        it.setIcon(0, self.thumbnail(lbl))
        it.setToolTip(0, self._tooltip(lbl))

    @staticmethod
    def _tooltip(lbl: Label) -> str:
        if lbl.is_free:
            texts = [lbl.resolve(e.text)[0] for e in lbl.elements
                     if e.kind == ElementKind.TEXT and e.text.strip()]
        else:
            texts = [lbl.display_text(ln) for _, ln in lbl.visible_lines()]
        parts = ["\n".join(texts)]
        if lbl.specs:
            parts.append("\n".join(f"{k}: {v}" if v else k for k, v in lbl.specs.items()))
        if lbl.notes.strip():
            parts.append(lbl.notes.strip())
        return "\n\n".join(p for p in parts if p)

    def _make_item(self, lbl: Label) -> QTreeWidgetItem:
        it = QTreeWidgetItem()
        it.setData(0, ID_ROLE, lbl.id)
        self._fill_item(it, lbl)
        return it

    def update_label(self, lbl: Label) -> None:
        """Cheap in-place update of one row (no rebuild)."""
        for it in self._iter_items():
            if it.data(0, ID_ROLE) == lbl.id:
                self._fill_item(it, lbl)
                return

    # -- events -------------------------------------------------------------------------

    def set_dirty(self, label_id: str) -> None:
        """Mark *label_id* as having unsaved changes ('' for none)."""
        if label_id == self._dirty:
            return
        self._dirty = label_id
        for it in self._iter_items():
            lid = it.data(0, ID_ROLE)
            if lid:
                it.setData(0, DIRTY_ROLE, lid == label_id)

    def pin(self, label_id: str) -> None:
        """Keep *label_id* in the list while it is being edited, even when the
        search text no longer matches it.  Cleared when another label is chosen."""
        self._pinned = label_id

    def reveal(self, lbl: Label) -> bool:
        """Make sure *lbl* is listed and selected after its category changed.

        An active category filter follows the label to its new category (or
        falls back to all categories for a label without one).  Returns True
        when the filter changed."""
        self.pin(lbl.id)
        idx = self.category.currentIndex()
        changed = idx > 0 and self.category.currentText() != lbl.category
        self.refresh()
        if changed:
            target = self.category.findText(lbl.category) if lbl.category else 0
            self.category.setCurrentIndex(max(0, target))  # triggers refresh
        self.select_ids([lbl.id])
        return changed

    def _on_selection(self) -> None:
        if self._building:
            return
        ids = self.selected_ids()
        if not ids and not self._explicit and self._keep_last_selection():
            return  # a click on a category heading or empty space keeps the open label
        self._last_ids = ids
        if self._pinned and self._pinned not in ids and not self._restoring:
            self._pinned = ""
        self.selectionChanged.emit(ids)
        cur = self.current_id()
        if cur not in ids and ids:
            cur = ids[0]
        self.currentLabelChanged.emit(cur if ids else "")

    def _keep_last_selection(self) -> bool:
        """Select the previous labels again (silently) if they are still listed."""
        wanted = set(self._last_ids)
        items = [it for it in self._iter_items() if it.data(0, ID_ROLE) in wanted]
        if not items:
            return False
        self._building = True
        try:
            for it in items:
                it.setSelected(True)
            self.tree.setCurrentItem(items[0], 0,
                                     self.tree.selectionModel().SelectionFlag.NoUpdate)
        finally:
            self._building = False
        return True

    def _context_menu(self, pos) -> None:  # noqa: ANN001
        m = QMenu(self)
        m.addAction(tr("Nieuw label"), self.newRequested.emit)
        if self.selected_ids():
            m.addAction(tr("Dupliceren"), self.duplicateRequested.emit)
            m.addAction(tr("Opmaak overnemen…"), self.copyFormatRequested.emit)
            m.addAction(tr("Hernoemen…"), self.renameRequested.emit)
            m.addAction(tr("Verwijderen"), self.deleteRequested.emit)
            m.addSeparator()
            m.addAction(tr("Selectie afdrukken…"), self.printSelectedRequested.emit)
            m.addAction(tr("Selectie exporteren als PNG…"), self.exportPngRequested.emit)
        m.exec(self.tree.viewport().mapToGlobal(pos))
