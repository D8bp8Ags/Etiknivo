"""Print queue panel."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui import theme
from etiknivo.i18n import tr
from etiknivo.printing.queue import JOB_STATUS_NL, JobStatus, QueueSnapshot

STATUS_TONE = {
    JobStatus.PENDING: "muted",
    JobStatus.PRINTING: "warning",
    JobStatus.DONE: "success",
    JobStatus.FAILED: "danger",
    JobStatus.CANCELLED: "muted",
}


class QueuePanel(QWidget):
    pauseRequested = Signal()
    resumeRequested = Signal()
    retryRequested = Signal()
    cancelRequested = Signal()
    clearRequested = Signal()

    def __init__(self, densities: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.densities = densities
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("Label"), tr("Exemplaren"), tr("Dichtheid"),
                                              tr("Status"), tr("Melding")])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        h = self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumWidth(260)
        self.summary = QLabel(tr("Wachtrij leeg"))
        self.summary.setTextFormat(Qt.TextFormat.RichText)

        def tool(text: str, tip: str) -> QToolButton:
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            return b

        self.pause_btn = tool(tr("Stop"), tr("Printen stoppen na het huidige etiket"))
        self.resume_btn = tool(tr("Hervat"), tr("Wachtrij hervatten"))
        self.retry_btn = tool(tr("Opnieuw"),
                              tr("Mislukte en geannuleerde opdrachten opnieuw proberen"))
        self.cancel_btn = tool(tr("Annuleer"), tr("Wachtende opdrachten annuleren"))
        self.clear_btn = tool(tr("Wis klaar"), tr("Afgeronde opdrachten uit de lijst halen"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 10)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(4)
        top.addWidget(self.summary)
        top.addSpacing(10)
        top.addWidget(self.progress, 1)
        top.addStretch(1)
        for b in (self.pause_btn, self.resume_btn, self.retry_btn, self.cancel_btn,
                  self.clear_btn):
            top.addWidget(b)
        lay.addLayout(top)
        lay.addWidget(self.table)
        self.apply_theme()
        theme.manager().changed.connect(self.apply_theme)
        self.pause_btn.clicked.connect(self.pauseRequested)
        self.resume_btn.clicked.connect(self.resumeRequested)
        self.retry_btn.clicked.connect(self.retryRequested)
        self.cancel_btn.clicked.connect(self.cancelRequested)
        self.clear_btn.clicked.connect(self.clearRequested)
        self.set_snapshot(QueueSnapshot((), False, False))

    def apply_theme(self) -> None:
        for b, name in ((self.pause_btn, "pause"), (self.resume_btn, "play"),
                        (self.retry_btn, "rotate-ccw"), (self.cancel_btn, "x"),
                        (self.clear_btn, "eraser")):
            b.setIcon(theme.icon(name, size=16))
        if hasattr(self, "_snap"):
            self.set_snapshot(self._snap)

    def set_snapshot(self, snap: QueueSnapshot) -> None:
        self._snap = snap
        t = theme.tokens()
        jobs = snap.jobs
        self.table.setRowCount(len(jobs))
        for row, j in enumerate(jobs):
            cells = [j.title, f"{j.copies_done}/{j.copies}", self.densities[j.density]
                     if 0 <= j.density < len(self.densities) else str(j.density),
                     tr(JOB_STATUS_NL[j.status]), j.error]
            for col, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if col == 3:
                    it.setForeground(QColor(getattr(t, STATUS_TONE[j.status])))
                if col == 4 and j.error:
                    it.setToolTip(j.error)
                self.table.setItem(row, col, it)
        total = sum(j.copies for j in jobs if j.status != JobStatus.CANCELLED)
        done = sum(j.copies_done if j.status != JobStatus.DONE else j.copies for j in jobs
                   if j.status != JobStatus.CANCELLED)
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        pend, failed = snap.pending, snap.failed
        if not jobs:
            text = tr("Wachtrij leeg")
        elif snap.paused and (pend or failed):
            text = tr("<b style='color:{color}'>Gestopt</b> · {pending} wachtend · {failed} "
                      "mislukt", color=t.danger, pending=pend, failed=failed)
        elif snap.running:
            text = tr("Bezig met printen · {pending} wachtend", pending=pend)
        else:
            text = tr("{done}/{total} etiketten klaar", done=done, total=total)
            if failed:
                text += tr(" · {failed} mislukt", failed=failed)
        self.summary.setText(text)
        self.pause_btn.setEnabled(snap.running or (pend > 0 and not snap.paused))
        self.resume_btn.setEnabled(snap.paused)
        self.retry_btn.setEnabled(any(j.status in (JobStatus.FAILED, JobStatus.CANCELLED)
                                      for j in jobs))
        self.cancel_btn.setEnabled(pend > 0)
        self.clear_btn.setEnabled(any(j.status not in (JobStatus.PENDING, JobStatus.PRINTING)
                                      for j in jobs))
        if snap.running:
            for row, j in enumerate(jobs):
                if j.status == JobStatus.PRINTING:
                    self.table.scrollToItem(self.table.item(row, 0))

