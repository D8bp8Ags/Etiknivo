"""Overview window: every label as a small piece of paper, grouped by category.

A click opens the label in the main window.  The same overview can be saved
as an A4 PDF (labels at real size, to hang next to the drawers) or as a PNG.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui import theme
from etiknivo.gui.qt_util import pil_to_pixmap
from etiknivo.i18n import tr
from etiknivo.model import Label
from etiknivo.rendering import overview
from etiknivo.rendering.engine import RenderEngine

ZOOM_RANGE = (4, 12)  # screen pixels per millimetre
DEFAULT_ZOOM = 6
#: spacing on screen in pixels, whatever the zoom
MARGIN_PX, GAP_PX, HEADING_PX, CAPTION_PX = 18, 18, 30, 38


def matches(lbl: Label, needle: str) -> bool:
    """Search in what the overview shows: name, tray, category and the label text."""
    if not needle:
        return True
    hay = " ".join([lbl.name, lbl.tray_id, lbl.category,
                    *(lbl.display_text(ln) for _, ln in lbl.visible_lines()),
                    *(lbl.resolve(e.text)[0] for e in lbl.elements)]).casefold()
    return all(part in hay for part in needle.casefold().split())


class OverviewCanvas(QWidget):
    """Paints the overview and reports clicks on a label."""

    labelClicked = Signal(str)

    def __init__(self, engine: RenderEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.labels: list[Label] = []
        self.zoom = float(DEFAULT_ZOOM)
        self.current = ""
        self._hover = ""
        self._items: list[tuple] = []
        self._hits: list[tuple[QRectF, str]] = []
        self._pixmaps: dict[str, tuple[str, QPixmap]] = {}
        self.setMouseTracking(True)
        self._grid = self._layout()

    def set_labels(self, labels: list[Label]) -> None:
        self.labels = labels
        self._relayout()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = zoom
        self._relayout()

    def invalidate(self) -> None:
        self._pixmaps.clear()
        self._relayout()

    def _layout(self) -> overview.OverviewLayout:
        z = self.zoom
        width_mm = max(60.0, self.width() / z)
        return overview.OverviewLayout(self.engine, width_mm, None, margin_mm=MARGIN_PX / z,
                                       gap_mm=GAP_PX / z, heading_mm=HEADING_PX / z,
                                       caption_mm=CAPTION_PX / z, title_mm=0.0)

    def _relayout(self) -> None:
        layout = self._layout()
        pages = layout.pages(overview.overview_order(self.labels))
        self._items = [it for it in pages[0] if it[0] != "title"]
        self._grid = layout
        z = self.zoom
        w, h = layout.label_w * z, layout.label_h * z
        self._hits = [(QRectF(layout.x_mm(col) * z - 4, y_mm * z - 4, w + 8, h + CAPTION_PX),
                       lbl.id) for kind, y_mm, lbl, col, _span in self._items if kind == "label"]
        self.setMinimumHeight(round(layout.end_mm * self.zoom) + MARGIN_PX)
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt API
        super().resizeEvent(event)
        self._relayout()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(round(4 * 30 * self.zoom + 3 * GAP_PX + 2 * MARGIN_PX), self.minimumHeight())

    def _pixmap(self, lbl: Label, size: QSize) -> QPixmap:
        key = f"{lbl.render_key()}|{size.width()}x{size.height()}"
        hit = self._pixmaps.get(lbl.id)
        if hit and hit[0] == key:
            return hit[1]
        img = self.engine.render(lbl).mono.convert("L")
        pm = pil_to_pixmap(img).scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
        self._pixmaps[lbl.id] = (key, pm)
        return pm

    def paintEvent(self, _event) -> None:  # noqa: N802, ANN001
        t = theme.tokens()
        z = self.zoom
        g = self._grid
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        head_f = QFont(self.font())
        head_f.setWeight(QFont.Weight.DemiBold)
        name_f = QFont(self.font())
        name_f.setWeight(QFont.Weight.DemiBold)
        sub_f = QFont(self.font())
        if not self.labels:
            p.setPen(QColor(t.muted))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("Geen labels gevonden"))
            p.end()
            return
        for kind, y_mm, payload, col, span in self._items:
            x = g.x_mm(col) * z
            y = y_mm * z
            if kind == "heading":
                w = g.span_mm(span) * z
                p.setFont(head_f)
                p.setPen(QColor(t.text))
                text = p.fontMetrics().elidedText(payload, Qt.TextElideMode.ElideRight, int(w))
                p.drawText(QRectF(x, y, w, HEADING_PX - 6),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, text)
                p.setPen(QPen(QColor(t.border), 1))
                p.drawLine(QPointF(x, y + HEADING_PX - 3),
                           QPointF(x + w, y + HEADING_PX - 3))
                continue
            lbl: Label = payload
            w, h = g.label_w * z, g.label_h * z
            card = QRectF(x, y, w, h)
            if lbl.id in (self._hover, self.current):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.selection if lbl.id == self.current else t.hover))
                p.drawRoundedRect(QRectF(x - 6, y - 6, w + 12, h + CAPTION_PX), 8, 8)
            p.setPen(QPen(QColor(t.border_strong), 1))
            p.setBrush(QColor("white"))
            p.drawRoundedRect(card, 4, 4)
            p.save()
            p.setClipRect(card.adjusted(1, 1, -1, -1))
            p.drawPixmap(card.toRect(), self._pixmap(lbl, card.toRect().size()))
            p.restore()
            p.setFont(name_f)
            p.setPen(QColor(t.text))
            fm = p.fontMetrics()
            p.drawText(QPointF(x, y + h + fm.ascent() + 4),
                       fm.elidedText(lbl.name, Qt.TextElideMode.ElideRight, int(w)))
            if lbl.tray_id:
                line = fm.height()
                p.setFont(sub_f)
                p.setPen(QColor(t.muted))
                p.drawText(QPointF(x, y + h + line + p.fontMetrics().ascent() + 5),
                           p.fontMetrics().elidedText(lbl.tray_id, Qt.TextElideMode.ElideRight,
                                                      int(w)))
        p.end()

    def label_at(self, pos: QPointF) -> str:
        return next((lid for rect, lid in self._hits if rect.contains(pos)), "")

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        hover = self.label_at(event.position())
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if hover
                           else Qt.CursorShape.ArrowCursor)
            self.update()
        lbl = next((x for x in self.labels if x.id == hover), None)
        self.setToolTip(lbl.name if lbl else "")

    def leaveEvent(self, event) -> None:  # noqa: N802, ANN001
        self._hover = ""
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        lid = self.label_at(event.position())
        if lid and event.button() == Qt.MouseButton.LeftButton:
            self.current = lid
            self.update()
            self.labelClicked.emit(lid)


class OverviewWindow(QDialog):
    """All labels at a glance.  *labels* gives the current library on demand."""

    labelActivated = Signal(str)

    def __init__(self, engine: RenderEngine, labels: Callable[[], list[Label]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Labeloverzicht"))
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.resize(900, 640)
        self.engine = engine
        self._labels = labels

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Zoeken op naam, tekst, lade-ID…"))
        self.search.setClearButtonEnabled(True)
        self.count = QLabel()
        self.count.setObjectName("muted")
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(*ZOOM_RANGE)
        self.zoom.setValue(DEFAULT_ZOOM)
        self.zoom.setMaximumWidth(120)
        self.zoom.setToolTip(tr("Grootte van de etiketjes"))
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.count)
        top.addSpacing(8)
        top.addWidget(self.zoom)

        self.canvas = OverviewCanvas(engine)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.canvas)

        hint = QLabel(tr("Klik op een label om het te openen."))
        hint.setObjectName("hint")
        self.pdf_btn = QPushButton(tr("Opslaan als PDF…"))
        self.pdf_btn.setToolTip(tr("A4-pagina's met de labels op ware grootte, om af te drukken "
                                   "en bij je ladekast te hangen"))
        self.png_btn = QPushButton(tr("Opslaan als PNG…"))
        self.png_btn.setToolTip(tr("Eén afbeelding met alle labels"))
        close = QPushButton(tr("Sluiten"))
        bottom = QHBoxLayout()
        bottom.addWidget(hint, 1)
        bottom.addWidget(self.pdf_btn)
        bottom.addWidget(self.png_btn)
        bottom.addWidget(close)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(scroll, 1)
        lay.addLayout(bottom)

        self.search.textChanged.connect(self.reload)
        self.zoom.valueChanged.connect(lambda v: self.canvas.set_zoom(float(v)))
        self.canvas.labelClicked.connect(self.labelActivated)
        self.pdf_btn.clicked.connect(lambda: self.export("pdf"))
        self.png_btn.clicked.connect(lambda: self.export("png"))
        close.clicked.connect(self.close)
        theme.manager().changed.connect(self.canvas.update)
        self.reload()

    def shown_labels(self) -> list[Label]:
        needle = self.search.text().strip()
        return [lbl for lbl in self._labels() if matches(lbl, needle)]

    def reload(self) -> None:
        """Show the library as it is now (after an edit, import or new roll)."""
        everything = self._labels()
        shown = self.shown_labels()
        self.canvas.set_labels(shown)
        self.count.setText(tr("{n} van {total}", n=len(shown), total=len(everything))
                           if len(shown) != len(everything)
                           else tr("{n} labels", n=len(shown)))
        for b in (self.pdf_btn, self.png_btn):
            b.setEnabled(bool(shown))

    def set_current(self, label_id: str) -> None:
        self.canvas.current = label_id
        self.canvas.update()

    def export(self, kind: str) -> Path | None:
        """Save the labels shown (respecting the search) as PDF or PNG."""
        pattern, write = overview.EXPORTS[kind]
        path, _ = QFileDialog.getSaveFileName(self, tr("Labeloverzicht opslaan"),
                                              f"etiknivo-overzicht.{kind}", pattern)
        if not path:
            return None
        try:
            write(self.engine, self.shown_labels(), Path(path))
        except OSError as exc:
            QMessageBox.critical(self, tr("Labeloverzicht"), tr(
                "Het bestand kon niet worden gelezen of geschreven:\n{error}", error=exc))
            return None
        return Path(path)
