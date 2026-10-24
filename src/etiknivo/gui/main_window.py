"""Etiknivo main window: wires library, editor, properties, printer and queue."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from etiknivo import APP_NAME
from etiknivo.gui import theme
from etiknivo.gui.dialogs import (
    AboutDialog,
    CalibrationDialog,
    CopyFormatDialog,
    PrintPreviewDialog,
)
from etiknivo.gui.library_panel import LibraryPanel
from etiknivo.gui.log_window import LogWindow
from etiknivo.gui.preview import DesignView, RasterView
from etiknivo.gui.printer_bridge import PrinterBridge
from etiknivo.gui.printer_panel import PrinterPanel, size_text
from etiknivo.gui.properties_panel import PropertiesPanel
from etiknivo.gui.queue_panel import QueuePanel
from etiknivo.i18n import LANGUAGES, language, tr
from etiknivo.i18n import resolve as resolve_language
from etiknivo.model import FORMAT_PARTS, Label, copy_format, make_label
from etiknivo.printing.backend import ConnectionState, PrinterBackend
from etiknivo.printing.manager import PrinterState
from etiknivo.printing.profiles import PrinterProfile
from etiknivo.printing.queue import PrintJob
from etiknivo.printing.registry import create_backend, get_model
from etiknivo.rendering.engine import RenderEngine
from etiknivo.rendering.export import ExportView, export_pdf, export_pngs, export_svg, safe_filename
from etiknivo.rendering.fonts import default_registry
from etiknivo.rendering.patterns import calibration_raster, test_label
from etiknivo.settings import Settings, data_dir, load_settings, log_dir, save_settings
from etiknivo.storage import io as lio
from etiknivo.storage.history import History, Snapshot
from etiknivo.storage.library import Library, LibraryError

log = logging.getLogger(__name__)
PRINT_GUARD_SECONDS = 1.0


def _format_key(lbl: Label) -> str:
    """The look of a label (not its text), to see whether it was changed by hand."""
    d = lbl.to_dict()
    for line in d["lines"]:
        line.pop("text", None)
    return json.dumps([d["layout"], d["lines"], d["style"], d["code"], d["picture"]],
                      sort_keys=True, default=str)


class MainWindow(QMainWindow):
    fontsLoaded = Signal(list)

    def __init__(self, library: Library, settings: Settings | None = None,
                 backend: PrinterBackend | None = None, poll_interval: float = 30.0) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}[*]")
        self.resize(1400, 860)
        self.setUnifiedTitleAndToolBarOnMac(True)
        self.library = library
        self.settings = settings or load_settings()
        theme.apply(self.settings.theme)
        self.profile = self._roll_profile()
        self.engine = RenderEngine(self.profile, self.settings.calibration)
        # The open label is edited as a draft (a copy); the library keeps the
        # saved version until the user clicks Opslaan.
        self.current: Label | None = None
        self._last_print = 0.0
        self._switching = False
        self._applying_history = False
        self._log_window: LogWindow | None = None
        #: labels made with Nieuw label whose look is still untouched:
        #: id -> (category, look); they take the style of a category they move to
        self._fresh: dict[str, tuple[str, str]] = {}

        self.bridge = PrinterBridge(backend or self.make_backend(self.settings.use_mock_printer),
                                    self,
                                    poll_interval=poll_interval)

        # --- panels -------------------------------------------------------------------
        self.library_panel = LibraryPanel(library, self.engine)
        self.library_panel.group.setChecked(self.settings.group_by_category)
        self.library_panel.set_sort_key(self.settings.sort_key)
        self.properties = PropertiesPanel()
        self.printer_panel = PrinterPanel(self.profile)
        self.printer_panel.mock.setChecked(self.settings.use_mock_printer)
        densities = self.profile.densities
        self.printer_panel.density.setCurrentIndex(
            self.settings.density if 0 <= self.settings.density < len(densities)
            else self.profile.default_density)
        self.printer_panel.copies.setValue(self.settings.default_copies)
        self.printer_panel.remember_address(self.settings.printer_address)
        self.queue_panel = QueuePanel(self.profile.densities)

        self.printer_panel.setObjectName("inspector")
        self.printer_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        right = QTabWidget()
        right.setDocumentMode(True)
        self.design_tab = self._build_design_tab()
        right.addTab(self.design_tab, tr("Ontwerp"))
        right.addTab(self.printer_panel, tr("Printer"))
        self.right_tabs = right
        inspector = QWidget()
        inspector.setObjectName("inspector")
        inspector.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        il = QVBoxLayout(inspector)
        il.setContentsMargins(0, 0, 0, 0)
        il.addWidget(right)

        center = self._build_editor()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.library_panel)
        splitter.addWidget(center)
        splitter.addWidget(inspector)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([340, 700, 360])
        self.setCentralWidget(splitter)

        dock = QDockWidget(tr("Printwachtrij"), self)
        dock.setObjectName("queue")
        dock.setWidget(self.queue_panel)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                         | QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.queue_dock = dock
        self.resizeDocks([dock], [190], Qt.Orientation.Vertical)
        dock.hide()

        self.printer_status = QLabel()
        self.statusBar().addPermanentWidget(self.printer_status)

        self._save_timer = QTimer(self, singleShot=True, interval=600)
        self._save_timer.timeout.connect(self.save_library)
        self._render_timer = QTimer(self, singleShot=True, interval=30)
        self._render_timer.timeout.connect(self.update_preview)

        self._build_toolbar()
        self._build_menus()
        self._connect_signals()
        self.apply_theme()
        theme.manager().changed.connect(self.apply_theme)
        self.properties.set_categories(self.library.categories())
        self._load_fonts_async()
        self.on_printer_state(self.bridge.state)
        self._update_queue_button()
        if self.bridge.manager.backend.simulated:
            self._connect("")

        first = self.library_panel.visible_ids()
        if first:
            self.library_panel.select_ids([first[0]])
        self._restore_geometry()
        self.history = History()
        self.history.reset(self._snapshot())
        self._update_undo_actions()
        QApplication.instance().installEventFilter(self)

    # -- construction --------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        tb = QToolBar(tr("Werkbalk"), self)
        tb.setObjectName("toolbar")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        tb.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self.toolbar = tb

        self.act_new = QAction(tr("Nieuw label"), self, toolTip=tr("Nieuw label (⌘N)"))
        self.act_dup = QAction(tr("Dupliceren"), self, toolTip=tr("Dupliceren (⌘D)"))
        self.act_rename = QAction(tr("Hernoemen"), self, toolTip=tr("Hernoemen (F2)"))
        self.act_del = QAction(tr("Verwijderen"), self, toolTip=tr("Verwijderen"))
        self.act_new.triggered.connect(self.new_label)
        self.act_dup.triggered.connect(self.duplicate_label)
        self.act_rename.triggered.connect(self.rename_label)
        self.act_del.triggered.connect(self.delete_labels)
        for a in (self.act_new, self.act_dup, self.act_rename, self.act_del):
            tb.addAction(a)
        tb.addSeparator()
        self.act_undo = QAction(tr("Ongedaan maken"), self, toolTip=tr("Ongedaan maken (⌘Z)"))
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self.undo)
        self.act_redo = QAction(tr("Opnieuw"), self, toolTip=tr("Opnieuw (⇧⌘Z)"))
        redo_keys = QKeySequence.keyBindings(QKeySequence.StandardKey.Redo)
        if QKeySequence("Ctrl+Shift+Z") not in redo_keys:  # Windows/Linux default is Ctrl+Y
            redo_keys.append(QKeySequence("Ctrl+Shift+Z"))
        self.act_redo.setShortcuts(redo_keys)
        self.act_redo.triggered.connect(self.redo)
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        title = QWidget()
        tl = QVBoxLayout(title)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)
        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("title")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_lbl = QLabel()
        self.subtitle_lbl.setObjectName("subtitle")
        self.subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tl.addWidget(self.title_lbl)
        tl.addWidget(self.subtitle_lbl)
        tb.addWidget(title)
        spacer2 = QWidget()
        spacer2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer2)

        self.printer_chip = QToolButton()
        self.printer_chip.setObjectName("chip")
        self.printer_chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.printer_chip.setToolTip(tr("Printer beheren"))
        self.printer_chip.clicked.connect(
            lambda: self.right_tabs.setCurrentWidget(self.printer_panel))
        tb.addWidget(self.printer_chip)
        self.queue_btn = QToolButton()
        self.queue_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.queue_btn.setToolTip(tr("Printwachtrij tonen of verbergen"))
        self.queue_btn.setCheckable(True)
        self.queue_btn.toggled.connect(lambda on: self.queue_dock.setVisible(on))
        self.queue_dock.visibilityChanged.connect(self.queue_btn.setChecked)
        tb.addWidget(self.queue_btn)

        self.print_btn = QPushButton(tr(" Afdrukken"))
        self.print_btn.setProperty("primary", True)
        self.print_btn.setToolTip(tr("Huidig label afdrukken (⌘P)"))
        self.print_btn.setDefault(True)
        self.print_more = QToolButton()
        self.print_more.setToolTip(tr("Meer afdrukopties"))
        self.print_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more = QMenu(self.print_more)
        self.print_sel_btn = more.addAction(tr("Geselecteerde labels…"), self.print_selected)
        more.addAction(tr("Alle labels uit categorie…"), self.print_category)
        more.addAction(tr("Alle labels…"), self.print_all)
        more.addSeparator()
        more.addAction(tr("Testlabel"), self.print_test_label)
        more.addAction(tr("Kalibratietest"), self.print_calibration)
        self.print_more.setMenu(more)
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(8, 0, 0, 0)
        hl.setSpacing(2)
        hl.addWidget(self.print_more)
        hl.addWidget(self.print_btn)
        tb.addWidget(holder)

    def _build_design_tab(self) -> QWidget:
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.properties, 1)
        footer = QWidget()
        footer.setObjectName("inspectorFooter")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(footer)
        row.setContentsMargins(14, 10, 14, 12)
        row.setSpacing(6)
        self.dirty_lbl = QLabel()
        self.dirty_lbl.setObjectName("dirty")
        self.revert_btn = QPushButton(tr("Herstellen"))
        self.revert_btn.setToolTip(tr("Wijzigingen aan dit label ongedaan maken"))
        self.revert_btn.clicked.connect(self.revert_current)
        self.save_btn = QPushButton(tr("Opslaan"))
        self.save_btn.setProperty("primary", True)
        self.save_btn.setToolTip(tr("Wijzigingen opslaan (⌘S)"))
        self.save_btn.clicked.connect(self.save_current)
        row.addWidget(self.dirty_lbl, 1)
        row.addWidget(self.revert_btn)
        row.addWidget(self.save_btn)
        v.addWidget(footer)
        return tab

    def _build_editor(self) -> QWidget:
        w = QWidget()
        w.setObjectName("canvas")
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        body = QWidget()
        body.setObjectName("canvas")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 28, 24, 24)
        bl.setSpacing(6)
        h1 = QLabel(tr("ONTWERP"))
        h1.setObjectName("caption")
        h1.setToolTip(tr("Bewerken met antialiasing. Gearceerd = wordt niet geprint (buiten de "
                         "printkop of in de veilige marge); blauw = printbaar; groen = marges."))
        self.design_view = DesignView(self.engine)
        h2 = self.raster_caption = QLabel()
        h2.setObjectName("caption")
        h2.setToolTip(tr("1-bit: exact de dots die geprint worden, op de plek waar ze op het "
                         "etiket komen (inclusief je kalibratie)."))
        self.raster_view = RasterView(self.engine)
        self.warnings = QLabel()
        self.warnings.setObjectName("pill")
        self.warnings.setTextFormat(Qt.TextFormat.RichText)
        for cap in (h1, h2):
            cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        bl.addWidget(h1)
        bl.addWidget(self.design_view, 0, Qt.AlignmentFlag.AlignHCenter)
        bl.addSpacing(18)
        bl.addWidget(h2)
        bl.addWidget(self.raster_view, 0, Qt.AlignmentFlag.AlignHCenter)
        bl.addSpacing(10)
        bl.addWidget(self.warnings, 0, Qt.AlignmentFlag.AlignHCenter)
        bl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        bar = QWidget()
        bar.setObjectName("canvas")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 6, 12, 8)
        row.setSpacing(4)
        self.guides = QToolButton()
        self.guides.setText(tr("Hulplijnen"))
        self.guides.setToolTip(tr("Printbaar gebied en marges tonen"))
        self.guides.setCheckable(True)
        self.guides.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.guides.setChecked(self.settings.show_printable_area)
        self.native = QToolButton()
        self.native.setToolTip(tr("Printerraster in de oriëntatie van de printkop tonen"))
        self.native.setCheckable(True)
        self.native.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.native.setChecked(self.settings.show_native_raster)
        self._update_size_texts()
        self.zoom_out = QToolButton()
        self.zoom_out.setToolTip(tr("Uitzoomen"))
        self.zoom_in = QToolButton()
        self.zoom_in.setToolTip(tr("Inzoomen"))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(6, 40)
        self.zoom.setValue(int(self.settings.zoom))
        self.zoom.setFixedWidth(120)
        self.zoom_lbl = QLabel()
        self.zoom_lbl.setObjectName("muted")
        self.zoom_lbl.setMinimumWidth(42)
        self.zoom_out.clicked.connect(lambda: self.zoom.setValue(self.zoom.value() - 2))
        self.zoom_in.clicked.connect(lambda: self.zoom.setValue(self.zoom.value() + 2))
        row.addWidget(self.guides)
        row.addWidget(self.native)
        row.addStretch(1)
        row.addWidget(self.zoom_out)
        row.addWidget(self.zoom)
        row.addWidget(self.zoom_in)
        row.addWidget(self.zoom_lbl)
        lay.addWidget(bar)

        self.raster_view.set_native(self.native.isChecked())
        self._apply_zoom(self.zoom.value())
        self.design_view.set_show_guides(self.guides.isChecked())
        return w

    def apply_theme(self) -> None:
        t = theme.tokens()
        for a, name in ((self.act_new, "plus"), (self.act_dup, "copy"),
                        (self.act_rename, "pencil"), (self.act_del, "trash-2"),
                        (self.act_undo, "undo-2"), (self.act_redo, "redo-2")):
            a.setIcon(theme.icon(name))
        self.guides.setIcon(theme.icon("square-dashed", size=16))
        self.native.setIcon(theme.icon("frame", size=16))
        self.zoom_out.setIcon(theme.icon("zoom-out", size=16))
        self.zoom_in.setIcon(theme.icon("zoom-in", size=16))
        self.queue_btn.setIcon(theme.icon("layers"))
        self.print_more.setIcon(theme.icon("chevron-down", size=16))
        self.print_btn.setIcon(theme.icon("printer", t.on_accent, 16))
        self.on_printer_state(self.bridge.state)
        self.update_preview()

    def _build_menus(self) -> None:
        mb = self.menuBar()

        def act(menu, text, slot, shortcut=None):  # type: ignore[no-untyped-def]
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        m = mb.addMenu(tr("&Bestand"))
        act(m, tr("Nieuw label"), self.new_label, QKeySequence.StandardKey.New)
        self.act_save = act(m, tr("Label opslaan"), self.save_current, QKeySequence.StandardKey.Save)
        self.act_revert = act(m, tr("Wijzigingen herstellen"), self.revert_current)
        m.addSeparator()
        act(m, tr("Bibliotheek importeren (JSON)…"), self.import_json)
        act(m, tr("Bibliotheek exporteren (JSON)…"), self.export_json)
        act(m, tr("Labels importeren (CSV)…"), self.import_csv)
        act(m, tr("Labels exporteren (CSV)…"), self.export_csv)
        m.addSeparator()
        act(m, tr("Selectie exporteren als PNG…"), self.export_png)
        act(m, tr("Selectie exporteren als PDF…"), self.export_pdf)
        act(m, tr("Huidig label exporteren als SVG…"), self.export_svg)
        m.addSeparator()
        act(m, tr("Back-up maken…"), self.backup)
        act(m, tr("Back-up herstellen…"), self.restore)
        act(m, tr("Datamap openen"), lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(data_dir()))))
        m.addSeparator()
        act(m, tr("Afsluiten"), self.close, QKeySequence.StandardKey.Quit)

        m = mb.addMenu(tr("Be&werken"))
        m.addAction(self.act_undo)
        m.addAction(self.act_redo)

        m = mb.addMenu(tr("&Label"))
        act(m, tr("Nieuw"), self.new_label)
        act(m, tr("Dupliceren"), self.duplicate_label, "Ctrl+D")
        act(m, tr("Hernoemen…"), self.rename_label, "F2")
        act(m, tr("Verwijderen"), self.delete_labels)
        m.addSeparator()
        self.act_copy_format = act(m, tr("Opmaak overnemen…"), self.copy_format)

        m = mb.addMenu(tr("&Afdrukken"))
        self.act_print = act(m, tr("Huidig label…"), self.print_current, QKeySequence.StandardKey.Print)
        act(m, tr("Geselecteerde labels…"), self.print_selected, "Ctrl+Shift+P")
        act(m, tr("Alle labels uit categorie…"), self.print_category)
        act(m, tr("Alle labels…"), self.print_all)
        m.addSeparator()
        act(m, tr("Testlabel"), self.print_test_label)
        act(m, tr("Kalibratietest"), self.print_calibration)

        m = mb.addMenu(tr("&Printer"))
        act(m, tr("Zoeken naar printers"), self._scan)
        act(m, tr("Verbinden"), lambda: self._connect(self.printer_panel.selected_address()))
        act(m, tr("Verbreken"), self._disconnect)
        act(m, tr("Status vernieuwen"), self._refresh)
        m.addSeparator()
        act(m, tr("Kalibratie-instellingen…"), self.calibration_settings)
        m.addSeparator()
        act(m, tr("Printwachtrij tonen"), lambda: (self.queue_dock.show(), self.queue_dock.raise_()))


        m = mb.addMenu(tr("&Weergave"))
        m.addAction(self.guides.text(), self.guides.toggle)
        m.addAction(tr("Printwachtrij"), lambda: self.queue_dock.setVisible(
            not self.queue_dock.isVisible()))
        m.addSeparator()
        tm = m.addMenu(tr("Thema"))
        group = QActionGroup(self)
        for key, text in theme.THEMES.items():
            a = tm.addAction(tr(text))
            a.setCheckable(True)
            a.setChecked(key == self.settings.theme)
            a.triggered.connect(lambda _c=False, k=key: self.set_theme(k))
            group.addAction(a)
        lm = m.addMenu(tr("Taal / Language"))
        langs = QActionGroup(self)
        for key, text in LANGUAGES.items():
            a = lm.addAction(tr(text))
            a.setCheckable(True)
            a.setChecked(key == self.settings.language)
            a.triggered.connect(lambda _c=False, k=key: self.set_language(k))
            langs.addAction(a)

        m = mb.addMenu(tr("&Help"))
        act(m, tr("Log tonen"), self.show_log, "Ctrl+L")
        act(m, tr("Logmap openen"), lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(log_dir()))))
        act(m, tr("Over {app}", app=APP_NAME), self.about)

    def set_language(self, choice: str) -> None:
        if choice == self.settings.language:
            return
        self.settings.language = choice
        self._save_settings()
        if resolve_language(choice) != language():
            # every text is built once; a restart applies the new language everywhere
            QMessageBox.information(self, APP_NAME, tr(
                "De nieuwe taal wordt gebruikt zodra je {app} opnieuw start.", app=APP_NAME))

    def set_theme(self, mode: str) -> None:
        self.settings.theme = mode
        self._save_settings()
        theme.apply(mode)

    def _connect_signals(self) -> None:
        lp = self.library_panel
        lp.currentLabelChanged.connect(self.set_current)
        lp.newRequested.connect(self.new_label)
        lp.duplicateRequested.connect(self.duplicate_label)
        lp.copyFormatRequested.connect(self.copy_format)
        lp.renameRequested.connect(self.rename_label)
        lp.deleteRequested.connect(self.delete_labels)
        lp.printSelectedRequested.connect(self.print_selected)
        lp.exportPngRequested.connect(self.export_png)
        lp.group.toggled.connect(self._save_view_settings)
        lp.sort.currentIndexChanged.connect(self._save_view_settings)
        self.properties.changed.connect(self.on_label_edited)
        self.zoom.valueChanged.connect(self._apply_zoom)
        self.guides.toggled.connect(self.design_view.set_show_guides)
        self.guides.toggled.connect(self._save_view_settings)
        self.native.toggled.connect(self.raster_view.set_native)
        self.native.toggled.connect(self._save_view_settings)
        self.print_btn.clicked.connect(self.print_current)
        self.bridge.queueChanged.connect(self._update_queue_button)

        pp = self.printer_panel
        pp.scanRequested.connect(self._scan)
        pp.connectRequested.connect(self._connect)
        pp.disconnectRequested.connect(self._disconnect)
        pp.refreshRequested.connect(self._refresh)
        pp.testLabelRequested.connect(self.print_test_label)
        pp.calibrationRequested.connect(self.print_calibration)
        pp.calibrationSettingsRequested.connect(self.calibration_settings)
        pp.mockToggled.connect(self.set_mock)
        pp.modelChanged.connect(self.set_printer_model)
        pp.labelSizeChanged.connect(self.set_label_size)
        pp.density.currentIndexChanged.connect(self._save_view_settings)
        pp.copies.valueChanged.connect(self._save_view_settings)

        qp = self.queue_panel
        qp.pauseRequested.connect(lambda: self.bridge.manager.queue_call("pause"))
        qp.resumeRequested.connect(self._resume_queue)
        qp.retryRequested.connect(lambda: self.bridge.manager.queue_call("retry_failed"))
        qp.cancelRequested.connect(lambda: self.bridge.manager.queue_call("cancel_pending"))
        qp.clearRequested.connect(lambda: self.bridge.manager.queue_call("clear_finished"))

        self.bridge.stateChanged.connect(self.on_printer_state)
        self.bridge.queueChanged.connect(self.queue_panel.set_snapshot)
        self.bridge.taskFinished.connect(self.on_task_finished)
        self.fontsLoaded.connect(self.properties.set_families)

    def _load_fonts_async(self) -> None:
        reg = default_registry()
        self.properties.set_families(["DejaVu Sans", "DejaVu Sans Condensed"])
        threading.Thread(target=lambda: self.fontsLoaded.emit(reg.families()), daemon=True,
                         name="font-scan").start()

    @staticmethod
    def _qsettings() -> QSettings:
        return QSettings(str(data_dir() / "window.ini"), QSettings.Format.IniFormat)

    def _restore_geometry(self) -> None:
        qs = self._qsettings()
        geo = qs.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        state = qs.value("windowState")
        if state is not None:
            self.restoreState(state)

    # -- editing -------------------------------------------------------------------------

    def set_current(self, label_id: str) -> None:
        cur = self.current
        if self._switching or self._applying_history:
            return
        if cur is not None and label_id == cur.id:
            return  # same label re-selected (list refresh): keep the draft
        if cur is not None and label_id != cur.id and self.is_dirty():
            answer = self._ask_unsaved(cur)
            if answer == "cancel":
                self._reselect(cur.id)
                return
            if answer == "save":
                self.save_current(follow=False)
        self._open(label_id)

    def _open(self, label_id: str, draft: Label | None = None) -> None:
        """Load *label_id* into the editor as a fresh draft (or the given one)."""
        saved = self.library.get(label_id) if label_id else None
        if saved is None:
            self.current = None
        elif draft is not None and draft.id == saved.id:
            self.current = draft
        else:
            self.current = saved.clone(new_id=False)
        self.properties.set_label(self.current)
        self._update_title()
        self._update_dirty()
        self.update_preview()

    def _reselect(self, label_id: str) -> None:
        self._switching = True
        try:
            self.library_panel.pin(label_id)
            self.library_panel.select_ids([label_id])
        finally:
            self._switching = False

    def _ask_unsaved(self, lbl: Label) -> str:
        """Ask what to do with unsaved changes: 'save', 'discard' or 'cancel'."""
        box = QMessageBox(QMessageBox.Icon.Question, APP_NAME,
                          tr("Wijzigingen in “{name}” opslaan?", name=lbl.name), parent=self)
        box.setInformativeText(tr("Je wijzigingen gaan verloren als je ze niet opslaat."))
        box.setStandardButtons(QMessageBox.StandardButton.Save
                               | QMessageBox.StandardButton.Discard
                               | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        box.button(QMessageBox.StandardButton.Discard).setText(tr("Niet opslaan"))
        box.button(QMessageBox.StandardButton.Cancel).setText(tr("Annuleren"))
        box.button(QMessageBox.StandardButton.Save).setText(tr("Opslaan"))
        result = box.exec()
        if result == QMessageBox.StandardButton.Save:
            return "save"
        if result == QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"

    def saved_version(self) -> Label | None:
        return self.library.get(self.current.id) if self.current is not None else None

    def is_dirty(self) -> bool:
        saved = self.saved_version()
        if saved is None:
            return False
        a, b = saved.to_dict(), self.current.to_dict()
        a.pop("modified"), b.pop("modified")
        return a != b

    def _update_dirty(self) -> None:
        dirty = self.is_dirty()
        self.setWindowModified(dirty)
        self.dirty_lbl.setText(tr("● Niet opgeslagen") if dirty else "")
        self.save_btn.setEnabled(dirty)
        self.revert_btn.setEnabled(dirty)
        self.act_save.setEnabled(dirty)
        self.act_revert.setEnabled(dirty)
        self.library_panel.set_dirty(self.current.id if dirty else "")

    def save_current(self, follow: bool = True) -> None:
        """Store the draft in the library and write it to disk.

        With *follow* the list (and an active category filter) follows the
        label to a new category; while switching to another label it doesn't."""
        saved = self.saved_version()
        if saved is None or not self.is_dirty():
            return
        moved = saved.category != self.current.category
        self.current.touch()
        self.library.update(self.current.clone(new_id=False))
        self._save_timer.stop()
        self.save_library()
        if moved:
            self.properties.set_categories(self.library.categories())
            if follow:
                self.library_panel.pin(self.current.id)
                self._switching = True
                try:
                    changed = self.library_panel.reveal(self.current)
                finally:
                    self._switching = False
                if changed:
                    where = self.current.category or tr("Alle categorieën")
                    self.statusBar().showMessage(
                        tr("Opgeslagen en verplaatst naar {where}", where=where), 4000)
            else:
                self.library_panel.refresh()
        else:
            self.library_panel.update_label(self.current)
        self._update_dirty()
        self._record()

    def revert_current(self) -> None:
        if self.current is None or not self.is_dirty():
            return
        self._open(self.current.id)
        self._record()
        self.statusBar().showMessage(tr("Wijzigingen hersteld"), 2000)

    def _with_draft(self, labels: list[Label]) -> list[Label]:
        """*labels* with the open label replaced by its draft (print what you see)."""
        cur = self.current
        return [cur if cur is not None and lbl.id == cur.id else lbl for lbl in labels]

    def _update_title(self) -> None:
        lbl = self.current
        self.title_lbl.setText(lbl.name if lbl else tr("Geen label geselecteerd"))
        self.subtitle_lbl.setText("  ·  ".join(x for x in (lbl.tray_id, lbl.category) if x)
                                  if lbl else "")
        for a in (self.act_dup, self.act_rename, self.act_del):
            a.setEnabled(lbl is not None)
        self.print_btn.setEnabled(lbl is not None)

    def on_label_edited(self, structural: bool) -> None:  # noqa: ARG002
        # Edits only change the draft: preview and title follow live, the
        # library (list, file) only changes on Opslaan.
        if self.current is None:
            return
        fresh = self._fresh.get(self.current.id)
        if fresh is not None:
            cat, look = fresh
            if _format_key(self.current) != look:
                del self._fresh[self.current.id]  # styled by hand: leave it alone
            elif self.current.category != cat:
                # a new label got a category: give it that category's style
                self._apply_category_style(self.current)
                self._fresh[self.current.id] = (self.current.category,
                                                _format_key(self.current))
                self.properties.set_label(self.current)
        self._render_timer.start()
        self._update_title()
        self.library_panel.pin(self.current.id)
        self._update_dirty()
        self._record(merge_key=self.current.id)

    def update_preview(self) -> None:
        if self.current is None:
            self.design_view.set_result(None)
            self.raster_view.set_result(None)
            self.warnings.setText("")
            self.warnings.setProperty("state", "")
            return
        r = self.engine.render(self.current)
        self.design_view.set_result(r)
        self.raster_view.set_result(r)
        self.properties.show_fitted_sizes({lb.slot: (lb.size_pt, lb.requested_pt)
                                           for lb in r.lines})
        if r.warnings:
            self.warnings.setProperty("state", "warn")
            self.warnings.setText("<br>".join(f"⚠&nbsp; {w}" for w in r.warnings))
        else:
            self.warnings.setProperty("state", "ok")
            self.warnings.setText("✓&nbsp; " + tr("Alle tekst valt binnen het printbare gebied"))
        self.warnings.style().unpolish(self.warnings)
        self.warnings.style().polish(self.warnings)

    def _apply_zoom(self, value: int) -> None:
        self.design_view.set_zoom(float(value))
        self.raster_view.set_zoom(float(value))
        self.zoom_lbl.setText(f"{value / (96 / 25.4):.0%}")
        self.settings.zoom = float(value)

    def schedule_save(self) -> None:
        self._save_timer.start()

    def save_library(self) -> None:
        try:
            self.library.save()
            self.statusBar().showMessage(tr("Opgeslagen"), 1500)
        except OSError as exc:
            log.exception("Opslaan mislukt")
            QMessageBox.critical(self, APP_NAME,
                                 tr("Bibliotheek opslaan mislukt:\n{error}", error=exc))

    def _save_view_settings(self) -> None:
        s = self.settings
        s.group_by_category = self.library_panel.group.isChecked()
        s.sort_key = self.library_panel.sort_key()
        s.show_printable_area = self.guides.isChecked()
        s.show_native_raster = self.native.isChecked()
        s.density = self.printer_panel.density.currentIndex()
        s.default_copies = self.printer_panel.copies.value()
        self._save_settings()

    def _save_settings(self) -> None:
        try:
            save_settings(self.settings)
        except OSError as exc:
            log.warning("Instellingen opslaan mislukt: %s", exc)

    def _after_library_change(self, select: list[str] | None = None) -> None:
        self.library_panel.refresh()
        self.properties.set_categories(self.library.categories())
        if select is not None:
            self.library_panel.select_ids(select)
        self.schedule_save()
        self._record()

    # -- undo / redo ---------------------------------------------------------------------

    def _snapshot(self) -> Snapshot:
        draft = self.current if self.is_dirty() else None
        return Snapshot.take(self.library.labels, self.library_panel.selected_ids(), draft)

    def _record(self, merge_key: str | None = None) -> None:
        if self._applying_history or not hasattr(self, "history"):
            return
        self.history.record(self._snapshot(), merge_key)
        self._update_undo_actions()

    def _update_undo_actions(self) -> None:
        self.act_undo.setEnabled(self.history.can_undo())
        self.act_redo.setEnabled(self.history.can_redo())

    def undo(self) -> None:
        self._apply_snapshot(self.history.undo(), tr("Ongedaan gemaakt"))

    def redo(self) -> None:
        self._apply_snapshot(self.history.redo(), tr("Opnieuw uitgevoerd"))

    def _apply_snapshot(self, state: Snapshot | None, message: str) -> None:
        if state is None:
            return
        self._applying_history = True
        try:
            self._render_timer.stop()
            self.library.replace_all(state.labels())
            self.library_panel.refresh()
            self.properties.set_categories(self.library.categories())
            ids = [i for i in state.selection if self.library.get(i)]
            if ids:
                self.library_panel.pin(ids[0])
                self.library_panel.reveal(self.library.get(ids[0]))
                self.library_panel.select_ids(ids)
            else:
                self.library_panel.select_ids([])
            self.schedule_save()
        finally:
            self._applying_history = False
        self._open(self.library_panel.current_id(), state.draft())
        self._update_undo_actions()
        self.statusBar().showMessage(message, 2000)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        # Text fields have their own undo, which would bypass the label (and
        # only knows about that one field).  Route Ctrl+Z / Ctrl+Shift+Z to the
        # application-wide history instead while focus is in this window.
        if event.type() == QEvent.Type.ShortcutOverride:
            focus = QApplication.focusWidget()
            if focus is not None and self.isAncestorOf(focus) and (
                    event.matches(QKeySequence.StandardKey.Undo)
                    or event.matches(QKeySequence.StandardKey.Redo)
                    or QKeySequence(event.keyCombination()) == QKeySequence("Ctrl+Shift+Z")):
                event.ignore()
                return True
        return super().eventFilter(obj, event)

    def new_label(self) -> None:
        combo = self.library_panel.category
        cat = combo.currentText() if combo.currentIndex() > 0 else ""
        lbl = make_label("", cat, tr("Nieuw label"), "")
        lbl.name = tr("Nieuw label")
        self._apply_category_style(lbl)
        self._fresh[lbl.id] = (cat, _format_key(lbl))  # see on_label_edited
        self.library.add(lbl)
        self.library_panel.pin(lbl.id)  # visible even when a search is active
        self._after_library_change([lbl.id])
        self.right_tabs.setCurrentWidget(self.design_tab)
        self.properties.lines[1].text.setFocus()
        self.properties.lines[1].text.selectAll()

    def category_template(self, category: str, exclude: str = "") -> Label | None:
        """The most recently edited label in *category*: new labels look like it."""
        if not category:
            return None
        same = [lbl for lbl in self.library.labels
                if lbl.category == category and lbl.id != exclude]
        return max(same, key=lambda lbl: lbl.modified, default=None)

    def _apply_category_style(self, lbl: Label) -> bool:
        template = self.category_template(lbl.category, lbl.id)
        if template is None:
            return False
        copy_format(template, lbl, set(FORMAT_PARTS))
        return True

    def duplicate_label(self) -> None:
        ids = self.library_panel.selected_ids()
        new = [d.id for i in ids if (d := self.library.duplicate(i)) is not None]
        if new:
            self.library_panel.pin(new[0])
            self._after_library_change(new)

    def rename_label(self) -> None:
        if self.current is None:
            return
        name, ok = QInputDialog.getText(self, tr("Label hernoemen"), tr("Nieuwe naam:"),
                                        text=self.current.name)
        if ok and name.strip():
            # renaming is a library action: saved at once, draft keeps its other edits
            for lbl in (self.saved_version(), self.current):
                if lbl is not None:
                    lbl.name = name.strip()
                    lbl.touch()
            self._after_library_change([self.current.id])
            self.properties.set_label(self.current)
            self._update_title()

    def _format_targets(self, kind: str, category: str) -> list[str]:
        """Ids of the labels 'Opmaak overnemen' would change (never the source)."""
        src = self.current.id if self.current else ""
        if kind == "selection":
            ids = self.library_panel.selected_ids()
        elif kind == "category":
            ids = [lbl.id for lbl in self.library.labels if lbl.category == category]
        else:
            ids = [lbl.id for lbl in self.library.labels]
        return [i for i in ids if i != src]

    def copy_format(self) -> None:
        """Give other labels the look of the open label (its draft as shown)."""
        if self.current is None:
            return
        selected = len([i for i in self.library_panel.selected_ids() if i != self.current.id])
        dlg = CopyFormatDialog(self.current, selected, self.library.categories(),
                               lambda k, c: len(self._format_targets(k, c)), self)
        if dlg.exec() != CopyFormatDialog.DialogCode.Accepted:
            return
        self.apply_format(self._format_targets(*dlg.target()), dlg.chosen_parts())

    def apply_format(self, ids: list[str], parts: set[str]) -> int:
        if self.current is None or not ids or not parts:
            return 0
        changed = 0
        for lid in ids:
            lbl = self.library.get(lid)
            if lbl is None:
                continue
            copy_format(self.current, lbl, parts)
            lbl.touch()
            changed += 1
        self.library_panel.invalidate_thumbnails()
        self._after_library_change(None)
        self.statusBar().showMessage(tr("Opmaak overgenomen op {n} label(s)", n=changed), 5000)
        return changed

    def delete_labels(self) -> None:
        ids = self.library_panel.selected_ids()
        if not ids:
            return
        names = ", ".join(self.library.get(i).name for i in ids[:5] if self.library.get(i))
        more = tr(" en {n} andere", n=len(ids) - 5) if len(ids) > 5 else ""
        if QMessageBox.question(self, tr("Verwijderen"),
                                tr("{n} label(s) verwijderen?", n=len(ids)) + f"\n\n{names}{more}"
                                ) != QMessageBox.StandardButton.Yes:
            return
        visible = self.library_panel.visible_ids()
        nxt = next((i for i in visible[visible.index(ids[-1]) + 1:] if i not in ids), None) \
            if ids[-1] in visible else None
        self.library.remove(ids)
        self._after_library_change([nxt] if nxt else [])

    # -- printing ------------------------------------------------------------------------

    def _guard(self) -> bool:
        """Ignore print requests fired twice in quick succession (double-click)."""
        now = time.monotonic()
        if now - self._last_print < PRINT_GUARD_SECONDS:
            return False
        self._last_print = now
        return True

    def _connected(self) -> bool:
        return self.bridge.state.connection == ConnectionState.CONNECTED

    def print_labels(self, labels: list[Label]) -> None:
        if not labels or not self._guard():
            return
        st = self.bridge.state
        printer_text = (f"{st.backend_name}" + (f" ({st.address})" if st.address else "")
                        if self._connected() else tr("niet verbonden"))
        dlg = PrintPreviewDialog(self.engine, labels, self.printer_panel.copies.value(),
                                 self.printer_panel.density.currentIndex(), printer_text,
                                 self._connected(), self)
        if dlg.exec() != PrintPreviewDialog.DialogCode.Accepted:
            return
        density = dlg.density.currentIndex()
        jobs = [PrintJob(lbl.id, f"{lbl.tray_id} {lbl.name}".strip(),
                         self.engine.render(lbl).raster, copies, density)
                for lbl, copies in zip(labels, dlg.copies_per_label())]
        self._submit(jobs)

    def _submit(self, jobs: list[PrintJob]) -> None:
        if not self._connected():
            QMessageBox.warning(self, APP_NAME, tr("Er is geen printer verbonden."))
            return
        self.queue_dock.show()
        self.bridge.track("enqueue", self.bridge.manager.enqueue(jobs))
        self._resume_queue_if_idle()

    def _resume_queue_if_idle(self) -> None:
        snap = self.bridge.queue_snapshot()
        if snap.paused and not snap.failed:
            self.bridge.manager.queue_call("resume")

    def _resume_queue(self) -> None:
        if not self._connected():
            QMessageBox.warning(self, APP_NAME, tr("Verbind eerst de printer opnieuw."))
            return
        self.bridge.manager.queue_call("resume")

    def print_current(self) -> None:
        if self.current is not None:
            self.print_labels([self.current])

    def _selected_in_view_order(self) -> list[Label]:
        sel = set(self.library_panel.selected_ids())
        return self._with_draft([lbl for i in self.library_panel.visible_ids()
                                 if i in sel and (lbl := self.library.get(i)) is not None])

    def print_selected(self) -> None:
        self.print_labels(self._selected_in_view_order())

    def print_category(self) -> None:
        cats = self.library.categories()
        if not cats:
            return
        cur = self.current.category if self.current and self.current.category in cats else cats[0]
        cat, ok = QInputDialog.getItem(self, tr("Categorie afdrukken"), tr("Categorie:"), cats,
                                       cats.index(cur), False)
        if ok:
            self.print_labels(self._with_draft(self.library.by_category(cat)))

    def print_all(self) -> None:
        # every label in the library, in the on-screen order (filtered-out ones last)
        order = {lid: n for n, lid in enumerate(self.library_panel.visible_ids())}
        self.print_labels(self._with_draft(
            sorted(self.library.labels, key=lambda lbl: order.get(lbl.id, len(order)))))

    def print_test_label(self) -> None:
        if not self._guard():
            return
        d = self.printer_panel.density.currentIndex()
        lbl = test_label(self.profile.densities[d])
        self._submit([PrintJob("test", tr("Testlabel"), self.engine.render(lbl).raster, 1, d)])

    def print_calibration(self) -> None:
        if not self._guard():
            return
        _mono, raster = calibration_raster(self.engine)
        self._submit([PrintJob("calibration", tr("Kalibratietest"), raster, 1,
                               self.printer_panel.density.currentIndex())])

    def calibration_settings(self) -> None:
        dlg = CalibrationDialog(self.engine.calibration, self, self.profile.dots_per_mm)
        if dlg.exec() == CalibrationDialog.DialogCode.Accepted:
            self.settings.calibration = dlg.calibration(self.settings.calibration)
            self.engine.calibration = self.settings.calibration
            self._save_settings()
            self.library_panel.invalidate_thumbnails()
            self.library_panel.refresh()
            self.update_preview()

    # -- printer -------------------------------------------------------------------------

    def _scan(self) -> None:
        self.right_tabs.setCurrentWidget(self.printer_panel)
        self.printer_panel.scan_btn.setEnabled(False)
        self.printer_panel.scan_busy.show()
        self.bridge.track("scan", self.bridge.manager.scan())

    def _connect(self, address: str) -> None:
        self.bridge.track("connect", self.bridge.manager.connect(address or None))

    def _disconnect(self) -> None:
        self.bridge.track("disconnect", self.bridge.manager.disconnect())

    def _refresh(self) -> None:
        self.bridge.track("refresh", self.bridge.manager.refresh())

    def set_mock(self, on: bool) -> None:
        self.settings.use_mock_printer = on
        self._save_settings()
        swap = self.bridge.manager.set_backend(self.make_backend(on))
        self.bridge.track("backend", swap)
        if on:  # the simulated printer is always "in range": connect straight away
            swap.add_done_callback(lambda _f: self.bridge.track(
                "connect", self.bridge.manager.connect(None)))

    def make_backend(self, simulated: bool) -> PrinterBackend:
        return create_backend(self.profile.key, simulated=simulated)

    def _roll_profile(self) -> PrinterProfile:
        """The printer model's profile for the label roll in the settings."""
        base = get_model(self.settings.printer_model).profile
        size = self.settings.label_size_mm
        try:
            return base.with_label(*size) if len(size) == 2 else base
        except (TypeError, ValueError):
            return base

    def _update_size_texts(self) -> None:
        w, h = self.profile.native_raster_size
        self.raster_caption.setText(tr("PRINTERRASTER  ·  {w} × {h} DOTS", w=w, h=h))
        self.native.setText(tr("Native {w} × {h}", w=w, h=h))

    def set_label_size(self, length_mm: float, height_mm: float) -> None:
        """Switch to another label roll: every label is shown and printed at that size."""
        self.settings.label_size_mm = [length_mm, height_mm]
        self._save_settings()
        self.profile = self._roll_profile()
        self.engine.profile = self.profile
        self.printer_panel.set_label_size(self.profile)
        self._update_size_texts()
        self.library_panel.invalidate_thumbnails()
        for view in (self.design_view, self.raster_view):
            view.updateGeometry()
            view.adjustSize()
        self.update_preview()
        self.statusBar().showMessage(tr("Etiketrol: {size}", size=size_text(*self.profile.label_size)),
                                     5000)

    def set_printer_model(self, key: str) -> None:
        if key == self.settings.printer_model:
            return
        self.settings.printer_model = key
        self._save_settings()
        QMessageBox.information(self, APP_NAME, tr(
            "Printer gewijzigd in {model}. Start {app} opnieuw om dit model te gebruiken.",
            model=get_model(key).display_name, app=APP_NAME))

    def on_printer_state(self, st: PrinterState) -> None:
        self.printer_panel.set_state(st)
        t = theme.tokens()
        text, tone = {ConnectionState.CONNECTED: (tr("Verbonden"), t.success),
                      ConnectionState.CONNECTING: (tr("Verbinden…"), t.warning),
                      ConnectionState.ERROR: (tr("Printerfout"), t.danger),
                      ConnectionState.DISCONNECTED: (tr("Geen printer"), t.muted)}[st.connection]
        chip = text
        if st.connection == ConnectionState.CONNECTED and st.info:
            chip = st.info.model or text
        if st.simulated:
            sim = tr("simulatie")
            text = tr("{state} (simulatie)", state=text)
            if sim not in chip:
                chip += f" · {sim}"
        battery = (st.info.battery if st.info and st.connection == ConnectionState.CONNECTED
                   else None)
        if battery is not None:
            text += tr(" · batterij {pct}%", pct=battery)
            chip += f" · {battery}%"
        self.printer_status.setText(text)
        self.printer_chip.setText(chip)
        self.printer_chip.setIcon(theme.dot(tone))
        if st.connection == ConnectionState.CONNECTED and st.address and not st.simulated \
                and st.address != self.settings.printer_address:
            self.settings.printer_address = st.address
            self._save_settings()

    def _update_queue_button(self, snap: object = None) -> None:
        snap = snap or self.bridge.queue_snapshot()
        busy = snap.pending + (1 if snap.running else 0)
        self.queue_btn.setText(tr("Wachtrij  {n}", n=busy) if busy else tr("Wachtrij"))

    def on_task_finished(self, tag: str, result: object, exc: object) -> None:
        if tag == "scan":
            self.printer_panel.scan_finished()
        if tag == "enqueue" and isinstance(result, list):
            self.statusBar().showMessage(
                tr("{n} opdracht(en) in de wachtrij", n=len(result)), 3000)
        if exc is not None:
            log.info("Taak %s mislukt: %s", tag, exc)
            self.statusBar().showMessage(f"{exc}", 8000)

    # -- import / export -----------------------------------------------------------------

    def _selected_or_all(self) -> list[Label]:
        return self._selected_in_view_order() or self._with_draft(self.library.labels)

    def import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Bibliotheek importeren"), "", "JSON (*.json)")
        if not path:
            return
        try:
            labels = lio.import_json(Path(path))
        except LibraryError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        box = QMessageBox(QMessageBox.Icon.Question, tr("Importeren"),
                          tr("{n} labels gevonden. Samenvoegen met de huidige bibliotheek of "
                             "de bibliotheek vervangen?", n=len(labels)), parent=self)
        merge = box.addButton(tr("Samenvoegen"), QMessageBox.ButtonRole.AcceptRole)
        replace = box.addButton(tr("Vervangen"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is merge:
            added, updated = self.library.merge(labels)
            msg = tr("{added} toegevoegd, {updated} bijgewerkt", added=added, updated=updated)
        elif box.clickedButton() is replace:
            self.library.replace_all(labels)
            msg = tr("Bibliotheek vervangen ({n} labels)", n=len(labels))
        else:
            return
        self._after_library_change()
        if self.current is not None:  # the open label may have been replaced
            self._open(self.current.id)
        self.statusBar().showMessage(msg, 5000)

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("Bibliotheek exporteren"),
                                              "etiknivo-bibliotheek.json", "JSON (*.json)")
        if path:
            lio.export_json(self.library.labels, Path(path))
            self.statusBar().showMessage(tr("{n} labels geëxporteerd", n=len(self.library)),
                                         4000)

    def import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("CSV importeren"), "", "CSV (*.csv *.txt)")
        if not path:
            return
        labels, errors = lio.import_csv(Path(path))
        for lbl in labels:
            self.library.add(lbl)
        self._after_library_change([lbl.id for lbl in labels])
        msg = tr("{n} labels geïmporteerd.", n=len(labels))
        if errors:
            msg += "\n\n" + tr("Problemen:") + "\n" + "\n".join(errors[:20])
        QMessageBox.information(self, tr("CSV-import"), msg)

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("CSV exporteren"), "etiknivo-labels.csv",
                                              "CSV (*.csv)")
        if path:
            lio.export_csv(self._selected_or_all(), Path(path))
            self.statusBar().showMessage(tr("CSV geëxporteerd"), 4000)

    def export_png(self) -> None:
        labels = self._selected_or_all()
        directory = QFileDialog.getExistingDirectory(
            self, tr("Map kiezen voor {n} PNG's", n=len(labels)))
        if not directory:
            return
        box = QMessageBox(QMessageBox.Icon.Question, tr("PNG-export"),
                          tr("Welke weergave exporteren?"), parent=self)
        dw, dh = self.engine.design_size
        rw, rh = self.profile.native_raster_size
        design = box.addButton(tr("Ontwerp ({w} × {h}, 4× vergroot)", w=dw, h=dh),
                               QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("Printerraster ({w} × {h}, 1:1)", w=rw, h=rh),
                      QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        view, scale = ((ExportView.DESIGN, 4) if box.clickedButton() is design
                       else (ExportView.RASTER, 1))
        paths = export_pngs(self.engine, labels, Path(directory), view, scale)
        self.statusBar().showMessage(
            tr("{n} PNG's opgeslagen in {folder}", n=len(paths), folder=directory), 5000)

    def export_pdf(self) -> None:
        labels = self._selected_or_all()
        path, _ = QFileDialog.getSaveFileName(self, tr("PDF exporteren"), "etiknivo-labels.pdf",
                                              "PDF (*.pdf)")
        if path:
            export_pdf(self.engine, labels, Path(path))
            self.statusBar().showMessage(tr("PDF met {n} pagina's opgeslagen", n=len(labels)),
                                         4000)

    def export_svg(self) -> None:
        if self.current is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("SVG exporteren"),
                                              f"{safe_filename(self.current)}.svg", "SVG (*.svg)")
        if path:
            export_svg(self.engine, self.current, Path(path))

    def backup(self) -> None:
        self.save_library()
        self._save_settings()
        path, _ = QFileDialog.getSaveFileName(self, tr("Back-up maken"), lio.default_backup_name(),
                                              "Zip (*.zip)")
        if path:
            files = lio.create_backup(data_dir(), Path(path))
            self.statusBar().showMessage(tr("Back-up gemaakt ({files})", files=", ".join(files)),
                                         5000)

    def restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Back-up herstellen"), "", "Zip (*.zip)")
        if not path:
            return
        if QMessageBox.question(self, tr("Herstellen"), tr(
                "De huidige bibliotheek en instellingen worden overschreven. Doorgaan?")
                ) != QMessageBox.StandardButton.Yes:
            return
        try:
            lio.restore_backup(Path(path), data_dir())
            self.library.load()
        except LibraryError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        self.settings = load_settings()
        self.engine.calibration = self.settings.calibration
        self.library_panel.invalidate_thumbnails()
        self.current = None
        self._after_library_change([])
        first = self.library_panel.visible_ids()
        if first:
            self.library_panel.select_ids([first[0]])
        self.statusBar().showMessage(tr("Back-up hersteld"), 5000)

    def show_log(self) -> None:
        if self._log_window is None or not self._log_window.isVisible():
            self._log_window = LogWindow(parent=self)
            self._log_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self._log_window.destroyed.connect(lambda: setattr(self, "_log_window", None))
        self._log_window.show()
        self._log_window.raise_()
        self._log_window.activateWindow()

    def about(self) -> None:
        AboutDialog(self.profile, data_dir(), log_dir(), self).exec()

    # -- shutdown ------------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        snap = self.bridge.queue_snapshot()
        if snap.running or snap.pending and not snap.paused:
            if QMessageBox.question(self, APP_NAME, tr("Er wordt nog geprint. Toch afsluiten?")) \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.is_dirty():
            answer = self._ask_unsaved(self.current)
            if answer == "cancel":
                event.ignore()
                return
            if answer == "save":
                self.save_current(follow=False)
        self._save_timer.stop()
        self.save_library()
        self._save_view_settings()
        qs = self._qsettings()
        qs.setValue("geometry", self.saveGeometry())
        qs.setValue("windowState", self.saveState())
        self.bridge.shutdown()
        QApplication.instance().removeEventFilter(self)
        event.accept()
