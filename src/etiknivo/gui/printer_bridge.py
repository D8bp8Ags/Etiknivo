"""Qt bridge for :class:`~etiknivo.printing.manager.PrinterManager`.

Callbacks from the asyncio thread are re-emitted as Qt signals, which Qt
delivers in the GUI thread (queued connection).
"""

from __future__ import annotations

import concurrent.futures
import copy
from typing import Any

from PySide6.QtCore import QObject, Signal

from etiknivo.printing.backend import PrinterBackend
from etiknivo.printing.manager import PrinterManager, PrinterState
from etiknivo.printing.queue import QueueSnapshot


class PrinterBridge(QObject):
    stateChanged = Signal(object)  # PrinterState (copy)
    queueChanged = Signal(object)  # QueueSnapshot
    taskFinished = Signal(str, object, object)  # tag, result, exception

    def __init__(self, backend: PrinterBackend, parent: QObject | None = None,
                 poll_interval: float = 30.0) -> None:
        super().__init__(parent)
        self.manager = PrinterManager(
            backend,
            on_state=lambda st: self.stateChanged.emit(copy.copy(st)),
            on_queue=lambda snap: self.queueChanged.emit(snap),
            poll_interval=poll_interval,
        )

    @property
    def state(self) -> PrinterState:
        return self.manager.state

    def track(self, tag: str, fut: concurrent.futures.Future[Any]) -> None:
        def done(f: concurrent.futures.Future[Any]) -> None:
            try:
                self.taskFinished.emit(tag, f.result(), None)
            except BaseException as exc:  # noqa: BLE001
                self.taskFinished.emit(tag, None, exc)
        fut.add_done_callback(done)

    def queue_snapshot(self) -> QueueSnapshot:
        return self.manager.runner.call(self.manager.queue.snapshot).result(2)

    def shutdown(self) -> None:
        self.manager.shutdown()
