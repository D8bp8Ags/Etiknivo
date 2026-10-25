"""Label preview widgets.

* :class:`DesignView` – the editing view: smooth, antialiased rendering of the
  full 30 × 14 mm label, with the printable band, margins and overflow marked.
* :class:`RasterView` – the exact 1-bit bitmap that is sent to the printer
  (calibration applied), drawn pixel for pixel.

Both are painted from the same :class:`~etiknivo.rendering.engine.RenderResult`.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from etiknivo.gui import theme
from etiknivo.gui.qt_util import pil_to_qimage
from etiknivo.model import Label, LabelElement
from etiknivo.rendering.engine import RenderEngine, RenderResult

PAD = 18
HANDLE = 7  # size of the resize handle in screen pixels


class _BaseView(QWidget):
    def __init__(self, engine: RenderEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.result: RenderResult | None = None
        self.zoom = 14.0  # screen px per mm
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_result(self, result: RenderResult | None) -> None:
        self.result = result
        self._image_cache()
        self.updateGeometry()
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = zoom
        self.updateGeometry()
        self.update()

    def _image_cache(self) -> None:  # pragma: no cover - overridden
        pass

    def label_rect(self) -> QRectF:
        p = self.engine.profile
        w, h = p.label_width_mm * self.zoom, p.label_height_mm * self.zoom
        x = max(PAD, (self.width() - w) / 2)
        return QRectF(x, PAD, w, h)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        p = self.engine.profile
        return QSize(int(p.label_width_mm * self.zoom + 2 * PAD),
                     int(p.label_height_mm * self.zoom + 2 * PAD))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()


def _paper_shadow(p: QPainter, r: QRectF, radius: float) -> None:
    """Soft drop shadow under a piece of paper."""
    dark = theme.tokens().dark
    p.setPen(Qt.PenStyle.NoPen)
    for i, alpha in enumerate((10, 14, 18, 26) if not dark else (30, 40, 55, 70)):
        grow = 4 - i
        p.setBrush(QColor(0, 0, 0, alpha))
        p.drawRoundedRect(r.adjusted(-grow, -grow + 2, grow, grow + 3), radius + grow,
                          radius + grow)


class DesignView(_BaseView):
    """Antialiased editing view of the whole label.

    In the free layout the elements can be selected, dragged and resized
    here; changes are made to the label directly and announced with
    :attr:`elementChanged`.
    """

    elementSelected = Signal(str)  # element id, "" for none
    elementChanged = Signal()  # moved, resized or deleted

    def __init__(self, engine: RenderEngine, parent: QWidget | None = None) -> None:
        super().__init__(engine, parent)
        self.show_guides = True
        self._qimg = None
        self.label: Label | None = None
        self.selected = ""
        self._drag: tuple[str, QPointF, tuple[float, float, float, float]] | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    # -- free layout ---------------------------------------------------------------

    def set_label(self, label: Label | None) -> None:
        self.label = label
        if not self._free() or not any(e.id == self.selected for e in label.elements):
            self.selected = ""
        self.update()

    def select(self, element_id: str) -> None:
        self.selected = element_id
        self.update()

    def _free(self) -> bool:
        return self.label is not None and self.label.is_free

    def _scale(self) -> float:
        """Screen pixels per design dot."""
        return self.label_rect().width() / self.engine.design_size[0]

    def element_rect(self, el: LabelElement) -> QRectF:
        r, s = self.label_rect(), self._scale()
        x0, y0, x1, y1 = self.engine.element_box(el)
        return QRectF(r.left() + x0 * s, r.top() + y0 * s, (x1 - x0) * s, (y1 - y0) * s)

    def _handle_rect(self, el: LabelElement) -> QRectF:
        br = self.element_rect(el).bottomRight()
        return QRectF(br.x() - HANDLE / 2, br.y() - HANDLE / 2, HANDLE, HANDLE)

    def _current(self) -> LabelElement | None:
        if not self._free():
            return None
        return next((e for e in self.label.elements if e.id == self.selected), None)

    def element_at(self, pos: QPointF) -> LabelElement | None:
        """Topmost element under *pos* (thin elements get a few pixels of slack)."""
        if not self._free():
            return None
        for el in reversed(self.label.elements):
            if self.element_rect(el).adjusted(-3, -3, 3, 3).contains(pos):
                return el
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if not self._free() or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        pos = event.position()
        cur = self._current()
        if cur is not None and self._handle_rect(cur).adjusted(-3, -3, 3, 3).contains(pos):
            self._drag = ("resize", pos, (cur.x_mm, cur.y_mm, cur.w_mm, cur.h_mm))
            return None
        el = self.element_at(pos)
        new_id = el.id if el is not None else ""
        if new_id != self.selected:
            self.selected = new_id
            self.elementSelected.emit(new_id)
            self.update()
        if el is not None:
            self._drag = ("move", pos, (el.x_mm, el.y_mm, el.w_mm, el.h_mm))
        return None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        cur = self._current()
        if self._drag is None or cur is None:
            if self._free():
                over = cur is not None and self._handle_rect(cur).adjusted(-3, -3, 3, 3) \
                    .contains(pos)
                self.setCursor(Qt.CursorShape.SizeFDiagCursor if over else
                               Qt.CursorShape.SizeAllCursor if self.element_at(pos) else
                               Qt.CursorShape.ArrowCursor)
            return super().mouseMoveEvent(event)
        mode, start, (x, y, w, h) = self._drag
        dpm = self.engine.profile.dots_per_mm
        s = self._scale()
        # whole dots: what you place is exactly what prints
        dx = round((pos.x() - start.x()) / s) / dpm
        dy = round((pos.y() - start.y()) / s) / dpm
        if mode == "move":
            cur.move_to(x + dx, y + dy)
        else:
            cur.resize(w + dx, h + dy)
        self.elementChanged.emit()
        self.update()
        return None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag = None
        return super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        cur = self._current()
        if cur is None:
            return super().keyPressEvent(event)
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.label.elements.remove(cur)
            self.selected = ""
            self.elementSelected.emit("")
            self.elementChanged.emit()
            self.update()
            return None
        dpm = self.engine.profile.dots_per_mm
        step = 1.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1 / dpm
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                 Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if key not in moves:
            return super().keyPressEvent(event)
        dx, dy = moves[key]
        cur.move_to(cur.x_mm + dx, cur.y_mm + dy)
        self.elementChanged.emit()
        self.update()
        return None

    def _paint_elements(self, p: QPainter) -> None:
        accent = QColor(theme.tokens().accent)
        faint = QColor(accent)
        faint.setAlpha(90)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for el in self.label.elements:
            rect = self.element_rect(el)
            if el.id == self.selected:
                p.setPen(QPen(accent, 1.5))
                p.drawRect(rect)
                p.setBrush(accent)
                p.setPen(QPen(QColor("white"), 1))
                p.drawRect(self._handle_rect(el))
                p.setBrush(Qt.BrushStyle.NoBrush)
            else:
                p.setPen(QPen(faint, 1, Qt.PenStyle.DotLine))
                p.drawRect(rect)

    def _image_cache(self) -> None:
        self._qimg = pil_to_qimage(self.result.hires) if self.result else None

    def set_show_guides(self, on: bool) -> None:
        self.show_guides = on
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802, ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self.label_rect()
        _paper_shadow(p, r, self.zoom)
        p.setBrush(QColor("white"))
        p.drawRoundedRect(r, self.zoom, self.zoom)
        if self._qimg is not None:
            p.save()
            p.setClipRect(r)
            p.drawImage(r, self._qimg)
            p.restore()
        res = self.result
        if self.show_guides and res is not None:
            sx = r.width() / self.engine.design_size[0]
            sy = r.height() / self.engine.design_size[1]
            x0, y0, x1, y1 = self.engine.printable_box
            hatch = QBrush(QColor(220, 60, 60, 60), Qt.BrushStyle.BDiagPattern)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(hatch)
            p.drawRect(QRectF(r.left(), r.top(), r.width(), y0 * sy))
            p.drawRect(QRectF(r.left(), r.top() + y1 * sy, r.width(), r.height() - y1 * sy))
            p.drawRect(QRectF(r.left(), r.top() + y0 * sy, x0 * sx, (y1 - y0) * sy))
            p.drawRect(QRectF(r.left() + x1 * sx, r.top() + y0 * sy, r.width() - x1 * sx,
                              (y1 - y0) * sy))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(40, 120, 220, 160), 1, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(r.left() + x0 * sx, r.top() + y0 * sy, (x1 - x0) * sx,
                              (y1 - y0) * sy))
            cx0, cy0, cx1, cy1 = res.content_box
            p.setPen(QPen(QColor(40, 170, 90, 150), 1, Qt.PenStyle.DotLine))
            p.drawRect(QRectF(r.left() + cx0 * sx, r.top() + cy0 * sy, (cx1 - cx0) * sx,
                              (cy1 - cy0) * sy))
        if res is not None and res.has_overflow:
            sx = r.width() / self.engine.design_size[0]
            sy = r.height() / self.engine.design_size[1]
            p.setPen(QPen(QColor(220, 30, 30), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for lb in res.lines:
                if lb.overflow:
                    p.drawRect(QRectF(r.left() + lb.x0 * sx, r.top() + lb.y0 * sy,
                                      (lb.x1 - lb.x0) * sx, (lb.y1 - lb.y0) * sy))
        if self._free():
            self._paint_elements(p)
        p.setPen(QPen(QColor(0, 0, 0, 30), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, self.zoom, self.zoom)
        p.end()


class RasterView(_BaseView):
    """Pixel-exact 1-bit printer raster (what the printhead will burn)."""

    def __init__(self, engine: RenderEngine, parent: QWidget | None = None) -> None:
        super().__init__(engine, parent)
        self.native = False
        self._qimg = None

    def set_native(self, native: bool) -> None:
        self.native = native
        self._image_cache()
        self.updateGeometry()
        self.update()

    def _image_cache(self) -> None:
        if self.result is None:
            self._qimg = None
            return
        img = self.result.raster if self.native else self.engine.raster_on_label(
            self.result.raster)
        self._qimg = pil_to_qimage(img)

    def _target(self) -> QRectF:
        dpm = self.engine.profile.dots_per_mm
        s = self.zoom / dpm  # screen px per dot
        rw, rh = self.engine.profile.native_raster_size
        w, h = (rw * s, rh * s) if self.native else (rh * s, rw * s)
        x = max(PAD, (self.width() - w) / 2)
        return QRectF(x, PAD, w, h)

    def sizeHint(self) -> QSize:  # noqa: N802
        t = self._target()
        return QSize(int(t.width() + 2 * PAD), int(t.height() + 2 * PAD))

    def paintEvent(self, _event) -> None:  # noqa: N802, ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._target()
        _paper_shadow(p, t, 2)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(t, QColor("white"))
        if self._qimg is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            p.drawImage(t, self._qimg)
            s = t.width() / self._qimg.width()
            if s >= 6:  # dot grid at high zoom
                p.setPen(QPen(QColor(0, 0, 0, 25), 1))
                for i in range(self._qimg.width() + 1):
                    x = t.left() + i * s
                    p.drawLine(int(x), int(t.top()), int(x), int(t.bottom()))
                for j in range(self._qimg.height() + 1):
                    y = t.top() + j * s
                    p.drawLine(int(t.left()), int(y), int(t.right()), int(y))
        p.end()
