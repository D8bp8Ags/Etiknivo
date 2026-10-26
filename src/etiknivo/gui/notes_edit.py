"""Notes field: grows with its text, shows links underlined and opens them
with Cmd-click (Ctrl-click on Windows and Linux), like Notes and TextEdit."""

from __future__ import annotations

import re

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QKeySequence,
    QMouseEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import QPlainTextEdit, QWidget

from etiknivo.gui import theme
from etiknivo.i18n import tr

#: web links and mail addresses; a trailing full stop or bracket is not part of it
LINK_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"]+[^\s<>\".,;:!?)\]}'»]"
                     r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
MIN_LINES, MAX_LINES = 3, 12


def link_url(text: str) -> QUrl:
    """The URL to open for a link found in the notes."""
    if "@" in text and "://" not in text:
        return QUrl("mailto:" + text)
    return QUrl(text if "://" in text else "https://" + text)


def find_links(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(0) for m in LINK_RE.finditer(text)))


class _LinkHighlighter(QSyntaxHighlighter):
    def __init__(self, doc: QTextDocument) -> None:
        super().__init__(doc)
        self.fmt = QTextCharFormat()
        self.fmt.setFontUnderline(True)
        self.refresh_colour()

    def refresh_colour(self) -> None:
        self.fmt.setForeground(QColor(theme.tokens().accent))
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for m in LINK_RE.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.fmt)


class NotesEdit(QPlainTextEdit):
    """Plain-text notes that grow from 3 to 12 lines and open links."""

    linkActivated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._highlighter = _LinkHighlighter(self.document())
        self.document().contentsChanged.connect(self.updateGeometry)
        mod = QKeySequence(Qt.KeyboardModifier.ControlModifier.value).toString(
            QKeySequence.SequenceFormat.NativeText)
        self._open_hint = tr("{mod}klik om de link te openen", mod=mod)

    # -- size: as tall as the text, within limits ---------------------------------------

    def _line_height(self) -> int:
        return self.fontMetrics().lineSpacing()

    def sizeHint(self) -> QSize:  # noqa: N802
        lines = 0
        block = self.document().begin()
        while block.isValid():
            layout = block.layout()
            lines += max(1, layout.lineCount() if layout is not None else 1)
            block = block.next()
        lines = min(MAX_LINES, max(MIN_LINES, lines))
        frame = self.frameWidth() * 2 + int(self.document().documentMargin() * 2)
        return QSize(super().sizeHint().width(), lines * self._line_height() + frame + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(super().minimumSizeHint().width(), self.sizeHint().height())

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().resizeEvent(event)
        self.updateGeometry()  # a new width can change the number of wrapped lines

    # -- links --------------------------------------------------------------------------

    def link_at(self, pos) -> str | None:  # type: ignore[no-untyped-def]
        cursor = self.cursorForPosition(pos)
        block, col = cursor.block(), cursor.positionInBlock()
        for m in LINK_RE.finditer(block.text()):
            if m.start() <= col <= m.end():
                return m.group(0)
        return None

    def _wants_link(self, event: QMouseEvent) -> str | None:
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return None
        return self.link_at(event.position().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        over = self.link_at(event.position().toPoint())
        open_now = over and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if open_now
                                  else Qt.CursorShape.IBeamCursor)
        self.viewport().setToolTip(self._open_hint if over else "")
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        link = self._wants_link(event)
        if link and event.button() == Qt.MouseButton.LeftButton:
            self.open_link(link)
            event.accept()
            return
        super().mousePressEvent(event)

    def open_link(self, link: str) -> None:
        self.linkActivated.emit(link)
        QDesktopServices.openUrl(link_url(link))

    def refresh_theme(self) -> None:
        self._highlighter.refresh_colour()
