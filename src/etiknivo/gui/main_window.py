"""Etiknivo main window: wires library, editor, properties, printer and queue."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from etiknivo import APP_NAME, __version__
from etiknivo.gui.dialogs import CalibrationDialog, PrintPreviewDialog
from etiknivo.gui.library_panel import ALL_CATEGORIES, LibraryPanel
from etiknivo.gui.preview import DesignView, RasterView
from etiknivo.gui.printer_bridge import PrinterBridge
from etiknivo.gui.printer_panel import DENSITIES, PrinterPanel
from etiknivo.gui.properties_panel import PropertiesPanel
from etiknivo.gui.queue_panel import QueuePanel
from etiknivo.model import Label, make_label
from etiknivo.printing.backend import ConnectionState, PrinterBackend
from etiknivo.printing.d11s_backend import D11sBackend
from etiknivo.printing.manager import PrinterState
from etiknivo.printing.mock import MockPrinterBackend
from etiknivo.printing.profiles import get_profile
from etiknivo.printing.queue import PrintJob
from etiknivo.rendering.engine import RenderEngine
from etiknivo.rendering.export import ExportView, export_pdf, export_pngs, export_svg, safe_filename
from etiknivo.rendering.fonts import default_registry
from etiknivo.rendering.patterns import calibration_raster, test_label
from etiknivo.settings import Settings, data_dir, load_settings, log_dir, save_settings
from etiknivo.storage import io as lio
from etiknivo.storage.library import Library, LibraryError

log = logging.getLogger(__name__)
PRINT_GUARD_SECONDS = 1.0


def make_backend(use_mock: bool) -> PrinterBackend:
    return MockPrinterBackend(delay=0.4) if use_mock else D11sBackend()


class MainWindow(QMainWindow):
    fontsLoaded = Signal(list)

    def __init__(self, library: Library, settings: Settings | None = None,
                 backend: PrinterBackend | None = None, poll_interval: float = 30.0) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 860)
        self.library = library
        self.settings = settings or load_settings()
        self.profile = get_profile(self.settings.printer_model)
        self.engine = RenderEngine(self.profile, self.settings.calibration)
        self.current: Label | None = None
        self._last_print = 0.0
        self._shown_category = ""

        self.bridge = PrinterBridge(backend or make_backend(self.settings.use_mock_printer), self,
                                    poll_interval=poll_interval)

        # --- panels -------------------------------------------------------------------
        self.library_panel = LibraryPanel(library, self.engine)
        self.library_panel.group.setChecked(self.settings.group_by_category)
        self.library_panel.set_sort_key(self.settings.sort_key)
        self.properties = PropertiesPanel()
        self.printer_panel = PrinterPanel()
        self.printer_panel.mock.setChecked(self.settings.use_mock_printer)
        self.printer_panel.density.setCurrentIndex(self.settings.density)
        self.printer_panel.copies.setValue(self.settings.default_copies)
        self.printer_panel.remember_address(self.settings.printer_address)
        self.queue_panel = QueuePanel()

        right = QTabWidget()
        right.addTab(self.properties, "Eigenschappen")
        right.addTab(self.printer_panel, "Printer")
        self.right_tabs = right

        center = self._build_editor()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.library_panel)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([440, 600, 370])
        self.setCentralWidget(splitter)

        dock = QDockWidget("Printwachtrij", self)
        dock.setObjectName("queue")
        dock.setWidget(self.queue_panel)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.queue_dock = dock
        self.resizeDocks([dock], [190], Qt.Orientation.Vertical)

        self.printer_status = QLabel()
        self.statusBar().addPermanentWidget(self.printer_status)

        self._save_timer = QTimer(self, singleShot=True, interval=600)
        self._save_timer.timeout.connect(self.save_library)
        self._render_timer = QTimer(self, singleShot=True, interval=30)
        self._render_timer.timeout.connect(self.update_preview)

        self._build_menus()
        self._connect_signals()
        self.properties.set_categories(self.library.categories())
        self._load_fonts_async()
        self.on_printer_state(self.bridge.state)

        first = self.library_panel.visible_ids()
        if first:
            self.library_panel.select_ids([first[0]])
        self._restore_geometry()

    # -- construction --------------------------------------------------------------------

    def _build_editor(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        bar = QHBoxLayout()
        self.title_lbl = QLabel("<b>Labeleditor</b>")
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(6, 40)
        self.zoom.setValue(int(self.settings.zoom))
        self.zoom.setMaximumWidth(180)
        self.zoom_lbl = QLabel()
        self.guides = QCheckBox("Printbaar gebied en marges")
        self.guides.setChecked(self.settings.show_printable_area)
        self.native = QCheckBox("Native oriëntatie (96×240)")
        self.native.setChecked(self.settings.show_native_raster)
        bar.addWidget(self.title_lbl)
        bar.addStretch(1)
        bar.addWidget(QLabel("Zoom"))
        bar.addWidget(self.zoom)
        bar.addWidget(self.zoom_lbl)
        lay.addLayout(bar)
        opts = QHBoxLayout()
        opts.addWidget(self.guides)
        opts.addWidget(self.native)
        opts.addStretch(1)
        lay.addLayout(opts)

        body = QWidget()
        bl = QVBoxLayout(body)
        h1 = QLabel("Ontwerpweergave <span style='color:gray'>— bewerken, met antialiasing. "
                    "Gearceerd = buiten de 96-dots printkop; blauw = printbaar; groen = marges"
                    "</span>")
        h1.setWordWrap(True)
        self.design_view = DesignView(self.engine)
        h2 = QLabel(f"Printerraster <span style='color:gray'>— 1-bit, exact wat er naar de "
                    f"printer gaat ({self.profile.printhead_px} × "
                    f"{self.profile.label_length_px} dots, kalibratie toegepast)</span>")
        h2.setWordWrap(True)
        self.raster_view = RasterView(self.engine)
        self.raster_view.set_native(self.native.isChecked())
        self.warnings = QLabel()
        self.warnings.setWordWrap(True)
        self.warnings.setTextFormat(Qt.TextFormat.RichText)
        bl.addWidget(h1)
        bl.addWidget(self.design_view, 0, Qt.AlignmentFlag.AlignHCenter)
        bl.addSpacing(8)
        bl.addWidget(h2)
        bl.addWidget(self.raster_view, 0, Qt.AlignmentFlag.AlignHCenter)
        bl.addWidget(self.warnings)
        bl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        row = QHBoxLayout()
        self.print_btn = QPushButton("Huidig label afdrukken…")
        self.print_btn.setDefault(True)
        self.print_sel_btn = QPushButton("Selectie afdrukken…")
        row.addStretch(1)
        row.addWidget(self.print_sel_btn)
        row.addWidget(self.print_btn)
        lay.addLayout(row)
        self._apply_zoom(self.zoom.value())
        self.design_view.set_show_guides(self.guides.isChecked())
        return w

    def _build_menus(self) -> None:
        mb = self.menuBar()

        def act(menu, text, slot, shortcut=None):  # type: ignore[no-untyped-def]
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        m = mb.addMenu("&Bestand")
        act(m, "Nieuw label", self.new_label, QKeySequence.StandardKey.New)
        m.addSeparator()
        act(m, "Bibliotheek importeren (JSON)…", self.import_json)
        act(m, "Bibliotheek exporteren (JSON)…", self.export_json)
        act(m, "Labels importeren (CSV)…", self.import_csv)
        act(m, "Labels exporteren (CSV)…", self.export_csv)
        m.addSeparator()
        act(m, "Selectie exporteren als PNG…", self.export_png)
        act(m, "Selectie exporteren als PDF…", self.export_pdf)
        act(m, "Huidig label exporteren als SVG…", self.export_svg)
        m.addSeparator()
        act(m, "Back-up maken…", self.backup)
        act(m, "Back-up herstellen…", self.restore)
        act(m, "Datamap openen", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(data_dir()))))
        m.addSeparator()
        act(m, "Afsluiten", self.close, QKeySequence.StandardKey.Quit)

        m = mb.addMenu("&Label")
        act(m, "Nieuw", self.new_label)
        act(m, "Dupliceren", self.duplicate_label, "Ctrl+D")
        act(m, "Hernoemen…", self.rename_label, "F2")
        act(m, "Verwijderen", self.delete_labels)

        m = mb.addMenu("&Afdrukken")
        self.act_print = act(m, "Huidig label…", self.print_current, QKeySequence.StandardKey.Print)
        act(m, "Geselecteerde labels…", self.print_selected, "Ctrl+Shift+P")
        act(m, "Alle labels uit categorie…", self.print_category)
        act(m, "Alle labels…", self.print_all)
        m.addSeparator()
        act(m, "Testlabel", self.print_test_label)
        act(m, "Kalibratietest", self.print_calibration)

        m = mb.addMenu("&Printer")
        act(m, "Zoeken naar printers", self._scan)
        act(m, "Verbinden", lambda: self._connect(self.printer_panel.selected_address()))
        act(m, "Verbreken", self._disconnect)
        act(m, "Status vernieuwen", self._refresh)
        m.addSeparator()
        act(m, "Kalibratie-instellingen…", self.calibration_settings)
        m.addSeparator()
        act(m, "Printwachtrij tonen", lambda: (self.queue_dock.show(), self.queue_dock.raise_()))

        m = mb.addMenu("&Help")
        act(m, "Logmap openen", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(log_dir()))))
        act(m, f"Over {APP_NAME}", self.about)

    def _connect_signals(self) -> None:
        lp = self.library_panel
        lp.currentLabelChanged.connect(self.set_current)
        lp.newRequested.connect(self.new_label)
        lp.duplicateRequested.connect(self.duplicate_label)
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
        self.print_sel_btn.clicked.connect(self.print_selected)

        pp = self.printer_panel
        pp.scanRequested.connect(self._scan)
        pp.connectRequested.connect(self._connect)
        pp.disconnectRequested.connect(self._disconnect)
        pp.refreshRequested.connect(self._refresh)
        pp.testLabelRequested.connect(self.print_test_label)
        pp.calibrationRequested.connect(self.print_calibration)
        pp.calibrationSettingsRequested.connect(self.calibration_settings)
        pp.mockToggled.connect(self.set_mock)
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
        self.current = self.library.get(label_id) if label_id else None
        self._shown_category = self.current.category if self.current else ""
        self.properties.set_label(self.current)
        self.title_lbl.setText(f"<b>{self.current.name}</b>" if self.current
                               else "<b>Geen label geselecteerd</b>")
        self.update_preview()

    def on_label_edited(self, structural: bool) -> None:
        if self.current is None:
            return
        self._render_timer.start()
        self.title_lbl.setText(f"<b>{self.current.name}</b>")
        if structural and self.current.category != self._shown_category:
            self._shown_category = self.current.category
            self.library_panel.refresh()  # regroup under the new category
        else:
            self.library_panel.update_label(self.current)
        self.schedule_save()

    def update_preview(self) -> None:
        if self.current is None:
            self.design_view.set_result(None)
            self.raster_view.set_result(None)
            self.warnings.setText("")
            return
        r = self.engine.render(self.current)
        self.design_view.set_result(r)
        self.raster_view.set_result(r)
        self.properties.show_fitted_sizes({lb.slot: (lb.size_pt, lb.requested_pt)
                                           for lb in r.lines})
        if r.warnings:
            self.warnings.setText("<br>".join(f"<span style='color:#d22'>⚠ {w}</span>"
                                              for w in r.warnings))
        else:
            self.warnings.setText("<span style='color:#2a2'>✓ Alle tekst valt binnen het "
                                  "printbare gebied</span>")

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
            self.statusBar().showMessage("Opgeslagen", 1500)
        except OSError as exc:
            log.exception("Opslaan mislukt")
            QMessageBox.critical(self, APP_NAME, f"Bibliotheek opslaan mislukt:\n{exc}")

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

    def new_label(self) -> None:
        cat = self.library_panel.category.currentText()
        cat = "" if cat == ALL_CATEGORIES else cat
        lbl = make_label("", cat, "Nieuw label", "")
        lbl.name = "Nieuw label"
        self.library.add(lbl)
        self._after_library_change([lbl.id])
        self.right_tabs.setCurrentWidget(self.properties)
        self.properties.lines[1].text.setFocus()
        self.properties.lines[1].text.selectAll()

    def duplicate_label(self) -> None:
        ids = self.library_panel.selected_ids()
        new = [d.id for i in ids if (d := self.library.duplicate(i)) is not None]
        if new:
            self._after_library_change(new)

    def rename_label(self) -> None:
        if self.current is None:
            return
        name, ok = QInputDialog.getText(self, "Label hernoemen", "Nieuwe naam:",
                                        text=self.current.name)
        if ok and name.strip():
            self.current.name = name.strip()
            self.current.touch()
            self._after_library_change([self.current.id])

    def delete_labels(self) -> None:
        ids = self.library_panel.selected_ids()
        if not ids:
            return
        names = ", ".join(self.library.get(i).name for i in ids[:5] if self.library.get(i))
        more = f" en {len(ids) - 5} andere" if len(ids) > 5 else ""
        if QMessageBox.question(self, "Verwijderen", f"{len(ids)} label(s) verwijderen?\n\n"
                                f"{names}{more}") != QMessageBox.StandardButton.Yes:
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
                        if self._connected() else "niet verbonden")
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
            QMessageBox.warning(self, APP_NAME, "Er is geen printer verbonden.")
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
            QMessageBox.warning(self, APP_NAME, "Verbind eerst de printer opnieuw.")
            return
        self.bridge.manager.queue_call("resume")

    def print_current(self) -> None:
        if self.current is not None:
            self.print_labels([self.current])

    def _selected_in_view_order(self) -> list[Label]:
        sel = set(self.library_panel.selected_ids())
        return [lbl for i in self.library_panel.visible_ids()
                if i in sel and (lbl := self.library.get(i)) is not None]

    def print_selected(self) -> None:
        self.print_labels(self._selected_in_view_order())

    def print_category(self) -> None:
        cats = self.library.categories()
        if not cats:
            return
        cur = self.current.category if self.current and self.current.category in cats else cats[0]
        cat, ok = QInputDialog.getItem(self, "Categorie afdrukken", "Categorie:", cats,
                                       cats.index(cur), False)
        if ok:
            self.print_labels(self.library.by_category(cat))

    def print_all(self) -> None:
        # every label in the library, in the on-screen order (filtered-out ones last)
        order = {lid: n for n, lid in enumerate(self.library_panel.visible_ids())}
        self.print_labels(sorted(self.library.labels, key=lambda lbl: order.get(lbl.id, len(order))))

    def print_test_label(self) -> None:
        if not self._guard():
            return
        d = self.printer_panel.density.currentIndex()
        lbl = test_label(DENSITIES[d])
        self._submit([PrintJob("test", "Testlabel", self.engine.render(lbl).raster, 1, d)])

    def print_calibration(self) -> None:
        if not self._guard():
            return
        _mono, raster = calibration_raster(self.engine)
        self._submit([PrintJob("calibration", "Kalibratietest", raster, 1,
                               self.printer_panel.density.currentIndex())])

    def calibration_settings(self) -> None:
        dlg = CalibrationDialog(self.engine.calibration, self)
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
        self.bridge.track("backend", self.bridge.manager.set_backend(make_backend(on)))

    def on_printer_state(self, st: PrinterState) -> None:
        self.printer_panel.set_state(st)
        text = {ConnectionState.CONNECTED: "Printer verbonden",
                ConnectionState.CONNECTING: "Printer verbinden…",
                ConnectionState.ERROR: "Printerfout",
                ConnectionState.DISCONNECTED: "Geen printer"}[st.connection]
        if st.simulated:
            text += " (simulatie)"
        if st.info and st.connection == ConnectionState.CONNECTED and st.info.battery is not None:
            text += f" · batterij {st.info.battery}%"
        self.printer_status.setText(text)
        if st.connection == ConnectionState.CONNECTED and st.address and not st.simulated \
                and st.address != self.settings.printer_address:
            self.settings.printer_address = st.address
            self._save_settings()

    def on_task_finished(self, tag: str, result: object, exc: object) -> None:
        if tag == "scan":
            self.printer_panel.scan_finished()
        if tag == "enqueue" and isinstance(result, list):
            self.statusBar().showMessage(f"{len(result)} opdracht(en) in de wachtrij", 3000)
        if exc is not None:
            log.info("Taak %s mislukt: %s", tag, exc)
            self.statusBar().showMessage(f"{exc}", 8000)

    # -- import / export -----------------------------------------------------------------

    def _selected_or_all(self) -> list[Label]:
        return self._selected_in_view_order() or self.library.labels

    def import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Bibliotheek importeren", "", "JSON (*.json)")
        if not path:
            return
        try:
            labels = lio.import_json(Path(path))
        except LibraryError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        box = QMessageBox(QMessageBox.Icon.Question, "Importeren",
                          f"{len(labels)} labels gevonden. Samenvoegen met de huidige "
                          f"bibliotheek of de bibliotheek vervangen?", parent=self)
        merge = box.addButton("Samenvoegen", QMessageBox.ButtonRole.AcceptRole)
        replace = box.addButton("Vervangen", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is merge:
            added, updated = self.library.merge(labels)
            msg = f"{added} toegevoegd, {updated} bijgewerkt"
        elif box.clickedButton() is replace:
            self.library.replace_all(labels)
            msg = f"Bibliotheek vervangen ({len(labels)} labels)"
        else:
            return
        self._after_library_change()
        self.statusBar().showMessage(msg, 5000)

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Bibliotheek exporteren",
                                              "etiknivo-bibliotheek.json", "JSON (*.json)")
        if path:
            lio.export_json(self.library.labels, Path(path))
            self.statusBar().showMessage(f"{len(self.library)} labels geëxporteerd", 4000)

    def import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "CSV importeren", "", "CSV (*.csv *.txt)")
        if not path:
            return
        labels, errors = lio.import_csv(Path(path))
        for lbl in labels:
            self.library.add(lbl)
        self._after_library_change([lbl.id for lbl in labels])
        msg = f"{len(labels)} labels geïmporteerd."
        if errors:
            msg += "\n\nProblemen:\n" + "\n".join(errors[:20])
        QMessageBox.information(self, "CSV-import", msg)

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "CSV exporteren", "etiknivo-labels.csv",
                                              "CSV (*.csv)")
        if path:
            lio.export_csv(self._selected_or_all(), Path(path))
            self.statusBar().showMessage("CSV geëxporteerd", 4000)

    def export_png(self) -> None:
        labels = self._selected_or_all()
        directory = QFileDialog.getExistingDirectory(self, f"Map kiezen voor {len(labels)} PNG's")
        if not directory:
            return
        box = QMessageBox(QMessageBox.Icon.Question, "PNG-export",
                          "Welke weergave exporteren?", parent=self)
        design = box.addButton("Ontwerp (240×112, 4× vergroot)",
                               QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Printerraster (96×240, 1:1)", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        view, scale = ((ExportView.DESIGN, 4) if box.clickedButton() is design
                       else (ExportView.RASTER, 1))
        paths = export_pngs(self.engine, labels, Path(directory), view, scale)
        self.statusBar().showMessage(f"{len(paths)} PNG's opgeslagen in {directory}", 5000)

    def export_pdf(self) -> None:
        labels = self._selected_or_all()
        path, _ = QFileDialog.getSaveFileName(self, "PDF exporteren", "etiknivo-labels.pdf",
                                              "PDF (*.pdf)")
        if path:
            export_pdf(self.engine, labels, Path(path))
            self.statusBar().showMessage(f"PDF met {len(labels)} pagina's opgeslagen", 4000)

    def export_svg(self) -> None:
        if self.current is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "SVG exporteren",
                                              f"{safe_filename(self.current)}.svg", "SVG (*.svg)")
        if path:
            export_svg(self.engine, self.current, Path(path))

    def backup(self) -> None:
        self.save_library()
        self._save_settings()
        path, _ = QFileDialog.getSaveFileName(self, "Back-up maken", lio.default_backup_name(),
                                              "Zip (*.zip)")
        if path:
            files = lio.create_backup(data_dir(), Path(path))
            self.statusBar().showMessage(f"Back-up gemaakt ({', '.join(files)})", 5000)

    def restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Back-up herstellen", "", "Zip (*.zip)")
        if not path:
            return
        if QMessageBox.question(self, "Herstellen", "De huidige bibliotheek en instellingen "
                                "worden overschreven. Doorgaan?") != QMessageBox.StandardButton.Yes:
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
        self._after_library_change([])
        first = self.library_panel.visible_ids()
        if first:
            self.library_panel.select_ids([first[0]])
        self.statusBar().showMessage("Back-up hersteld", 5000)

    def about(self) -> None:
        QMessageBox.about(self, f"Over {APP_NAME}",
                          f"<h3>{APP_NAME} {__version__}</h3>"
                          "<p>Open-source Label Designer &amp; Printer Manager.</p>"
                          f"<p>Printer: {self.profile.display_name}<br>"
                          f"Printkop {self.profile.printhead_px} dots, {self.profile.dpi} dpi, "
                          f"label {self.profile.label_width_mm:g} × "
                          f"{self.profile.label_height_mm:g} mm.</p>"
                          "<p>Lettertype: DejaVu Sans.</p><p>MIT-licentie.</p>")

    # -- shutdown ------------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        snap = self.bridge.queue_snapshot()
        if snap.running or snap.pending and not snap.paused:
            if QMessageBox.question(self, APP_NAME, "Er wordt nog geprint. Toch afsluiten?") \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._save_timer.stop()
        self.save_library()
        self._save_view_settings()
        qs = self._qsettings()
        qs.setValue("geometry", self.saveGeometry())
        qs.setValue("windowState", self.saveState())
        self.bridge.shutdown()
        event.accept()
