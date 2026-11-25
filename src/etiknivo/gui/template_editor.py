"""Window for the user's own templates: make one (empty or as a copy of a
ready-made one), place and size its parts, rename and delete it.

A template is edited like a label in the free layout, on a sample label, so
what you see is what a label gets.  Its texts use the part fields
(``{Hoofdregel}``, ``{Lade}``, ``{Code}``…), so every label fills it with its
own content.  The ready-made templates cannot be changed; a copy of one can.
"""

from __future__ import annotations

import copy
import json
import time

import shiboken6
from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui.element_panel import ElementPanel, new_element
from etiknivo.gui.preview import DesignView
from etiknivo.gui.properties_panel import custom_template_icon
from etiknivo.i18n import tr
from etiknivo.model import (
    PICTOGRAM_FIELD,
    TEMPLATE_INFO,
    CodeKind,
    ElementKind,
    HAlign,
    Label,
    LabelTemplate,
    LayoutPreset,
    PictureKind,
    UserTemplate,
    make_label,
    part_field,
    part_field_names,
)
from etiknivo.rendering.engine import RenderEngine
from etiknivo.rendering.templates import apply_template, template_from_builtin, tray_field
from etiknivo.storage.library import Library

#: the parts the "Add part" menu places: (title, element kind, content, size in mm, pt)
PARTS: tuple[tuple[str, ElementKind, str, tuple[float, float], float], ...] = (
    ("Bovenregel", ElementKind.TEXT, "top", (12.0, 3.0), 8.0),
    ("Hoofdregel", ElementKind.TEXT, "main", (16.0, 5.0), 15.0),
    ("Onderregel", ElementKind.TEXT, "bottom", (16.0, 3.0), 7.0),
    ("Lade-ID", ElementKind.TEXT, "tray", (6.0, 3.0), 7.0),
    ("QR-code", ElementKind.QR, "code", (8.0, 8.0), 10.0),
    ("Tekst onder de QR-code", ElementKind.TEXT, "code", (8.0, 2.5), 7.0),
    ("Pictogram van het label", ElementKind.SYMBOL, "", (7.0, 7.0), 10.0),
)


def sample_label() -> Label:
    """The label a template is shown on while it is edited."""
    lbl = make_label("A17", tr("Halfgeleiders"), tr("Rood"), "Ø 3 mm | THT | 20 mA")
    lbl.top.text, lbl.top.enabled = "LED", True
    lbl.picture.kind, lbl.picture.symbol = PictureKind.SYMBOL, "led"
    lbl.code.kind = CodeKind.QR
    lbl.layout = LayoutPreset.FREE
    return lbl


def _alive(widget: QWidget) -> bool:
    """Whether Qt still has the widget (a closed window may be gone)."""
    return shiboken6.isValid(widget)


def scaled(tpl: UserTemplate, area_mm: tuple[float, float]) -> UserTemplate:
    """A copy of *tpl* drawn on a printable area of *area_mm*."""
    out = copy.deepcopy(tpl)
    sx, sy = area_mm[0] / tpl.width_mm, area_mm[1] / tpl.height_mm
    if abs(sx - 1) < 1e-6 and abs(sy - 1) < 1e-6:
        return out
    for el in out.elements:
        el.move_to(el.x_mm * sx, el.y_mm * sy)
        el.resize(el.w_mm * sx, el.h_mm * sy)
        el.font_size_pt = round(el.font_size_pt * sy, 2)
    out.width_mm, out.height_mm = area_mm
    return out


class TemplateEditor(QDialog):
    """Make, change, rename and delete the user's own templates."""

    #: the own templates changed (saved or deleted); the library is up to date
    templatesChanged = Signal()

    def __init__(self, library: Library, engine: RenderEngine, families: list[str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Eigen sjablonen"))
        self.library = library
        # an engine of its own: the sample label shares no sizes with a category
        self.engine = RenderEngine(engine.profile, engine.calibration, engine.fonts)
        self.work: UserTemplate | None = None
        self.dirty = False
        #: the template being edited is new and not saved yet: it is in the
        #: library only once saved, and goes away unchanged when you move on
        self.draft = False
        self.sample = sample_label()
        self._loading = False
        #: asks what to do with unsaved changes: "save", "discard" or "cancel"
        self.ask_unsaved = self._ask_box
        #: undo history of the template being edited: its states as JSON, the
        #: state shown now at ``_at``; the saved state, to know what is unsaved
        self._states: list[str] = []
        self._at = -1
        self._saved_state = ""
        self._last_edit = (0.0, 0, "")  # time, element count and kind of the last edit
        #: asks to go ahead with a deletion
        self.confirm = lambda text: QMessageBox.question(
            self, tr("Eigen sjablonen"), text) == QMessageBox.StandardButton.Yes

        # -- left: the own templates ------------------------------------------------
        self.list = QListWidget()
        self.list.setIconSize(QSize(72, 34))
        self.list.setMinimumWidth(220)
        self.new_btn = QToolButton()
        self.new_btn.setText(tr("Nieuw") + " ▾")
        self.new_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.new_btn)
        menu.addAction(tr("Leeg sjabloon"), self.new_empty)
        menu.addSection(tr("Kopie van een kant-en-klaar sjabloon"))
        for tpl, (name, _desc) in TEMPLATE_INFO.items():
            if tpl != LabelTemplate.NONE:
                menu.addAction(tr(name), lambda t=tpl: self.new_from(t))
        self.new_btn.setMenu(menu)
        self.dup_btn = QPushButton(tr("Dupliceren"))
        self.del_btn = QPushButton(tr("Verwijderen"))
        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        buttons.addWidget(self.new_btn)
        buttons.addWidget(self.dup_btn)
        buttons.addWidget(self.del_btn)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel(tr("Je eigen sjablonen")))
        ll.addWidget(self.list, 1)
        ll.addLayout(buttons)
        intro = QLabel(tr("De kant-en-klare sjablonen veranderen niet: maak met Nieuw een "
                          "kopie om op voort te bouwen."))
        intro.setWordWrap(True)
        intro.setObjectName("hint")
        ll.addWidget(intro)

        # -- middle: name and the sample label ------------------------------------------
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("Naam van het sjabloon"))
        self.view = DesignView(self.engine)
        self.view.set_zoom(16.0)
        self.parts_btn = QToolButton()
        self.parts_btn.setText(tr("Onderdeel toevoegen") + " ▾")
        self.parts_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        parts = QMenu(self.parts_btn)
        for n, (title, *_rest) in enumerate(PARTS):
            parts.addAction(tr(title), lambda n=n: self.add_part(n))
        self.parts_btn.setMenu(parts)
        self.warnings = QLabel()
        self.warnings.setWordWrap(True)
        self.warnings.setObjectName("hint")
        help_ = QLabel(tr(
            "Teksten met {Bovenregel}, {Hoofdregel}, {Onderregel}, {Lade} of {Code} tonen wat "
            "het label heeft; in hoofdletters ({BOVENREGEL}) staat de regel in hoofdletters. "
            "{Cel 1} tot {Cel 6} zijn de delen van de onderregel tussen |. Een symbool "
            "'Pictogram van het label' toont het pictogram van elk label. Een tekst met "
            "precies één regel krijgt de opmaak van die regel, die je per label kunt "
            "aanpassen."))
        help_.setWordWrap(True)
        help_.setObjectName("hint")
        middle = QWidget()
        ml = QVBoxLayout(middle)
        ml.setContentsMargins(0, 0, 0, 0)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("Naam")))
        name_row.addWidget(self.name, 1)
        ml.addLayout(name_row)
        ml.addWidget(self.view, 0, Qt.AlignmentFlag.AlignHCenter)
        self.undo_btn = QToolButton()
        self.undo_btn.setText(tr("Ongedaan maken"))
        self.undo_btn.setToolTip(tr("Ongedaan maken") + " (Ctrl+Z)")
        self.redo_btn = QToolButton()
        self.redo_btn.setText(tr("Opnieuw"))
        self.redo_btn.setToolTip(tr("Opnieuw") + " (Ctrl+Shift+Z)")
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn.clicked.connect(self.redo)
        tools = QHBoxLayout()
        tools.addWidget(self.undo_btn)
        tools.addWidget(self.redo_btn)
        tools.addWidget(self.parts_btn)
        tools.addStretch(1)
        ml.addLayout(tools)
        ml.addWidget(self.warnings)
        ml.addWidget(help_)
        ml.addStretch(1)

        # -- right: the elements ------------------------------------------------------
        self.elements = ElementPanel(lambda: self.engine.area_mm)
        self.elements.set_families(families)
        self.elements.field_btn.fields = lambda: part_field_names() + \
            self.sample.field_names()
        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setWidget(self.elements)
        right.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._right = right

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(middle)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 540, 400])
        split.setChildrenCollapsible(False)
        # the buttons keep their whole text (macOS buttons have wide padding):
        # the column is never narrower than the row of buttons
        for btn in (self.new_btn, self.dup_btn, self.del_btn):
            btn.setMinimumWidth(btn.sizeHint().width())
        left.setMinimumWidth(max(200, buttons.sizeHint().width()))
        middle.setMinimumWidth(self.view.minimumSizeHint().width())

        self.save_btn = QPushButton(tr("Opslaan"))
        self.save_btn.setDefault(True)
        close_btn = QPushButton(tr("Sluiten"))
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self.save_btn)
        bottom.addWidget(close_btn)
        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        lay.addLayout(bottom)
        self.resize(1180, 620)

        self.list.currentRowChanged.connect(self._row_changed)
        self.dup_btn.clicked.connect(self.duplicate)
        self.del_btn.clicked.connect(self.delete)
        self.save_btn.clicked.connect(self.save)
        close_btn.clicked.connect(self.close)
        self.name.textEdited.connect(self._changed)
        self.elements.changed.connect(self._changed)
        self.elements.selected.connect(self.view.select)
        self.elements.selected.connect(lambda _id: self._fit_right())
        self.view.elementSelected.connect(self.elements.select)
        self.view.elementChanged.connect(self._moved)
        for keys, slot in ((QKeySequence.StandardKey.Undo, self.undo),
                           (QKeySequence.StandardKey.Redo, self.redo),
                           (QKeySequence("Ctrl+Shift+Z"), self.redo),
                           (QKeySequence.StandardKey.Save, self.save)):
            QShortcut(QKeySequence(keys), self, activated=slot)
        # text fields have an undo of their own, that only knows that field:
        # Ctrl+Z goes to the template's history instead (as in the main window)
        QApplication.instance().installEventFilter(self)
        self._fill_list()
        self.list.setCurrentRow(0 if self.list.count() else -1)
        self._show()

    # -- the list -----------------------------------------------------------------------

    def _own(self) -> list[UserTemplate]:
        return sorted(self.library.templates, key=lambda t: t.name.casefold())

    def _fill_list(self, select_id: str = "") -> None:
        self._loading = True
        self.list.clear()
        row = -1
        own = self._own()
        if self.draft and self.work is not None:
            own.insert(0, self.work)
        for n, tpl in enumerate(own):
            name = tpl.name or tr("Naamloos sjabloon")
            if self.draft and tpl is self.work:
                name = tr("{name} (nog niet opgeslagen)", name=name)
            item = QListWidgetItem(custom_template_icon(tpl), name)
            item.setData(Qt.ItemDataRole.UserRole, tpl.id)
            if self.draft and tpl is self.work:
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
            self.list.addItem(item)
            if tpl.id == select_id:
                row = n
        self.list.setCurrentRow(row)
        self._loading = False

    def _row_changed(self, row: int) -> None:
        if self._loading:
            return
        item = self.list.item(row)
        tpl_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else ""
        if self.work is not None and tpl_id == self.work.id:
            return
        was_draft = self.draft
        if not self._may_leave():
            self._select_in_list(self.work.id if self.work else "")
            return
        tpl = next((t for t in self.library.templates if t.id == tpl_id), None)
        self._edit(tpl)
        if was_draft and not self.draft:  # the unsaved one leaves the list
            self._fill_list(tpl_id)

    def _select_in_list(self, tpl_id: str) -> None:
        self._loading = True
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == tpl_id:
                self.list.setCurrentRow(row)
                break
        self._loading = False

    # -- making and choosing ------------------------------------------------------------

    def _edit(self, tpl: UserTemplate | None, dirty: bool = False) -> None:
        """Start editing a working copy of *tpl*, drawn on the current roll."""
        self.work = scaled(tpl, self.engine.area_mm) if tpl is not None else None
        state = self._state()
        self._states, self._at = ([state], 0) if self.work is not None else ([], -1)
        # a new template is unsaved until it is saved; an existing one as stored
        self._saved_state = "" if dirty else state
        self.dirty = dirty
        self._show()

    # -- undo -------------------------------------------------------------------------

    def _state(self) -> str:
        return json.dumps(self.work.to_dict(), sort_keys=True) if self.work else ""

    def _record(self, kind: str = "edit") -> None:
        """Keep the state after an edit.  Typing and dragging in quick
        succession is one step; adding or removing a part is always its own."""
        state = self._state()
        if not self._states or state == self._states[self._at]:
            return
        now, count = time.monotonic(), len(self.work.elements)
        last_time, last_count, last_kind = self._last_edit
        merge = (self._at == len(self._states) - 1 and self._at > 0 and kind == "edit"
                 and last_kind == "edit" and now - last_time < 0.8 and count == last_count)
        del self._states[self._at + 1:]
        if merge:
            self._states[self._at] = state
        else:
            self._states.append(state)
            self._at += 1
        self._last_edit = (now, count, kind)

    def undo(self) -> None:
        if self._at > 0:
            self._go(self._at - 1)

    def redo(self) -> None:
        if 0 <= self._at < len(self._states) - 1:
            self._go(self._at + 1)

    def _go(self, at: int) -> None:
        keep = self.elements.current().id if self.elements.current() else ""
        self._at = at
        self._last_edit = (0.0, 0, "")  # the next edit is a step of its own
        self.work = UserTemplate.from_dict(json.loads(self._states[at]))
        self.dirty = self._states[at] != self._saved_state
        self._show()
        if any(el.id == keep for el in self.work.elements):
            self.elements.select(keep)
            self.view.select(keep)

    def _update_undo(self) -> None:
        self.undo_btn.setEnabled(self._at > 0)
        self.redo_btn.setEnabled(0 <= self._at < len(self._states) - 1)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.ShortcutOverride and _alive(self) and \
                self.isActiveWindow():
            focus = QApplication.focusWidget()
            if focus is not None and self.isAncestorOf(focus) and (
                    event.matches(QKeySequence.StandardKey.Undo)
                    or event.matches(QKeySequence.StandardKey.Redo)
                    or QKeySequence(event.keyCombination()) == QKeySequence("Ctrl+Shift+Z")):
                event.ignore()
                return True
        return super().eventFilter(obj, event)

    def _start_new(self, tpl: UserTemplate) -> None:
        if not self._may_leave():
            return
        # not saved yet: it joins your templates when you save it, and choosing
        # another template without changing it just lets it go (no question)
        self._edit(tpl)
        self.draft = True
        self._fill_list(tpl.id)
        self._render()
        self.name.setFocus()
        self.name.selectAll()

    def new_empty(self) -> None:
        w, h = self.engine.area_mm
        self._start_new(UserTemplate(name=tr("Nieuw sjabloon"), width_mm=w, height_mm=h))

    def new_from(self, template: LabelTemplate) -> None:
        tpl = template_from_builtin(template, self.engine.area_mm)
        tpl.name = tr("{name} (eigen)", name=tr(TEMPLATE_INFO[template][0]))
        self._start_new(tpl)

    def duplicate(self) -> None:
        if self.work is None:
            return
        tpl = copy.deepcopy(self.work)
        tpl.id = UserTemplate().id
        tpl.name = tr("{name} (kopie)", name=self.name.text().strip() or tpl.name)
        self._start_new(tpl)

    def add_part(self, n: int) -> None:
        """Place one of the label's parts, with the field that fills it."""
        if self.work is None:
            return
        _title, kind, what, (w, h), pt = PARTS[n]
        el = new_element(kind, self.engine.area_mm)
        el.resize(min(w, self.engine.area_mm[0]), min(h, self.engine.area_mm[1]))
        el.move_to((self.engine.area_mm[0] - el.w_mm) / 2,
                   (self.engine.area_mm[1] - el.h_mm) / 2)
        el.font_size_pt = pt
        if kind == ElementKind.SYMBOL:
            el.symbol = PICTOGRAM_FIELD
        elif what == "tray":
            el.text, el.bold, el.align = tray_field(), True, HAlign.RIGHT
        else:
            el.text = part_field(what)
            el.bold = what == "main"
            el.align = HAlign.CENTER if what == "code" else HAlign.LEFT
        self.work.elements.append(el)
        self.elements.set_label(self.sample)
        self.elements.select(el.id)
        self.view.select(el.id)
        self._changed("add")

    # -- showing ------------------------------------------------------------------------

    def _show(self) -> None:
        on = self.work is not None
        for w in (self.name, self.view, self.parts_btn, self.elements, self.dup_btn,
                  self.del_btn):
            w.setEnabled(on)
        self.name.setText(self.work.name if on else "")
        self.sample.elements = self.work.elements if on else []
        self.elements.set_label(self.sample if on else None)
        self._fit_right()
        self._render()

    def _fit_right(self) -> None:
        """The element column never gets narrower than its fields (which
        depend on the selected element): a smaller window narrows the middle."""
        bar = self._right.verticalScrollBar().sizeHint().width()
        self._right.setMinimumWidth(max(380, self.elements.minimumSizeHint().width()
                                        + bar + 4))

    def _render(self) -> None:
        self.view.set_label(self.sample)
        if self.work is None:
            self.view.set_result(None)
            self.warnings.setText(tr("Maak met Nieuw een eigen sjabloon."))
        else:
            r = self.engine.render(self.sample)
            self.view.set_result(r)
            self.warnings.setText("\n".join(dict.fromkeys(r.warnings)))
        self.save_btn.setEnabled(self.work is not None and (self.dirty or self.draft))
        self._update_undo()

    def _changed(self, kind: str = "edit") -> None:
        if self._loading or self.work is None:
            return
        self.work.name = self.name.text()
        self._record(kind)
        self.dirty = self._states[self._at] != self._saved_state
        self._render()

    def showEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt API
        super().showEvent(event)
        self._fit_right()

    def _moved(self) -> None:
        self.elements.refresh()
        self._changed()

    # -- saving -------------------------------------------------------------------------

    def save(self) -> bool:
        if self.work is None:
            return True
        self.work.name = self.name.text().strip() or tr("Naamloos sjabloon")
        self.name.setText(self.work.name)
        saved = copy.deepcopy(self.work)
        others = [t for t in self.library.templates if t.id != saved.id]
        self.library.set_templates([*others, saved])
        self.dirty = self.draft = False
        # the name as saved belongs to this step; undo after saving still works
        self._states[self._at] = self._saved_state = self._state()
        self._fill_list(saved.id)
        self._render()
        self.templatesChanged.emit()
        return True

    def labels_using(self, tpl_id: str) -> list[Label]:
        return [lbl for lbl in self.library.labels if lbl.template == LabelTemplate.CUSTOM
                and lbl.custom_template == tpl_id]

    def delete(self) -> None:
        """Delete the template; labels with it go back to the lines under each other."""
        if self.work is None:
            return
        tpl_id = self.work.id
        known = any(t.id == tpl_id for t in self.library.templates)
        users = self.labels_using(tpl_id)
        text = tr("Sjabloon '{name}' verwijderen?", name=self.name.text().strip())
        if users:
            text += "\n\n" + tr("{n} labels gebruiken het; die krijgen weer de regels onder "
                                "elkaar.", n=len(users))
        if known and not self.confirm(text):
            return
        for lbl in users:
            apply_template(lbl, LabelTemplate.NONE)
            lbl.touch()
        self.library.set_templates([t for t in self.library.templates if t.id != tpl_id])
        self.work, self.dirty, self.draft = None, False, False
        self._fill_list()
        self.list.setCurrentRow(0 if self.list.count() else -1)
        if self.list.count() == 0:
            self._show()
        if known:
            self.templatesChanged.emit()

    def _may_leave(self) -> bool:
        """Before another template or closing: save or drop unsaved changes."""
        if self.work is None:
            return True
        if not self.dirty:
            self.draft = False  # a new one you did not change is not kept
            return True
        answer = self.ask_unsaved(self.name.text().strip())
        if answer == "save":
            return self.save()
        if answer == "discard":
            self.dirty = self.draft = False
            return True
        return False

    def _ask_box(self, name: str) -> str:
        box = QMessageBox(QMessageBox.Icon.Question, tr("Eigen sjablonen"),
                          tr("Wijzigingen in '{name}' opslaan?", name=name), parent=self)
        save = box.addButton(tr("Opslaan"), QMessageBox.ButtonRole.AcceptRole)
        drop = box.addButton(tr("Niet opslaan"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return {save: "save", drop: "discard"}.get(box.clickedButton(), "cancel")

    def reject(self) -> None:
        """Esc: as closing, so unsaved changes are asked about."""
        if self._may_leave():
            QApplication.instance().removeEventFilter(self)
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt API
        if self._may_leave():
            QApplication.instance().removeEventFilter(self)
            event.accept()
        else:
            event.ignore()
