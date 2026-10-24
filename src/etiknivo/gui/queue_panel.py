"""Print queue panel."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from etiknivo.gui.printer_panel import DENSITIES
from etiknivo.printing.queue import JOB_STATUS_NL, JobStatus, QueueSnapshot

STATUS_COLOR = {
    JobStatus.PENDING: QColor("#777"),
    JobStatus.PRINTING: QColor("#c80"),
    JobStatus.DONE: QColor("#2a2"),
    JobStatus.FAILED: QColor("#d22"),
    JobStatus.CANCELLED: QColor("#777"),
}


class QueuePanel(QWidget):
    pauseRequested = Signal()
    resumeRequested = Signal()
    retryRequested = Signal()
    cancelRequested = Signal()
    clearRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Label", "Exemplaren", "Dichtheid", "Status",
                                              "Melding"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.progress = QProgressBar()
        self.summary = QLabel("Wachtrij leeg")
        self.pause_btn = QPushButton("Stoppen")
        self.resume_btn = QPushButton("Hervatten")
        self.retry_btn = QPushButton("Mislukte opnieuw")
        self.cancel_btn = QPushButton("Wachtende annuleren")
        self.clear_btn = QPushButton("Afgeronde wissen")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        top = QHBoxLayout()
        top.addWidget(self.summary, 1)
        top.addWidget(self.progress, 1)
        for b in (self.pause_btn, self.resume_btn, self.retry_btn, self.cancel_btn,
                  self.clear_btn):
            top.addWidget(b)
        lay.addLayout(top)
        lay.addWidget(self.table)
        self.pause_btn.clicked.connect(self.pauseRequested)
        self.resume_btn.clicked.connect(self.resumeRequested)
        self.retry_btn.clicked.connect(self.retryRequested)
        self.cancel_btn.clicked.connect(self.cancelRequested)
        self.clear_btn.clicked.connect(self.clearRequested)
        self.set_snapshot(QueueSnapshot((), False, False))

    def set_snapshot(self, snap: QueueSnapshot) -> None:
        jobs = snap.jobs
        self.table.setRowCount(len(jobs))
        for row, j in enumerate(jobs):
            cells = [j.title, f"{j.copies_done}/{j.copies}", DENSITIES[j.density]
                     if 0 <= j.density < 3 else str(j.density), JOB_STATUS_NL[j.status], j.error]
            for col, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if col == 3:
                    it.setForeground(STATUS_COLOR[j.status])
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
            text = "Wachtrij leeg"
        elif snap.paused and (pend or failed):
            text = f"<b style='color:#d22'>Gestopt</b> · {pend} wachtend · {failed} mislukt"
        elif snap.running:
            text = f"Bezig met printen · {pend} wachtend"
        else:
            text = f"{done}/{total} etiketten klaar" + (f" · {failed} mislukt" if failed else "")
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

