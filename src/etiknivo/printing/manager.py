"""Printer manager: owns the backend, the print queue and the async loop.

This layer is GUI-independent.  It reports changes through plain callbacks
(called on the asyncio thread); :mod:`etiknivo.gui.printer_bridge` turns them
into Qt signals.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from etiknivo.i18n import tr
from etiknivo.printing.backend import (
    ConnectionState,
    DiscoveredDevice,
    PrinterBackend,
    PrinterError,
    PrinterInfo,
)
from etiknivo.printing.queue import PrintJob, PrintQueue, QueueSnapshot
from etiknivo.printing.runner import AsyncRunner

log = logging.getLogger(__name__)

STATUS_POLL_SECONDS = 30.0


@dataclass
class PrinterState:
    connection: ConnectionState = ConnectionState.DISCONNECTED
    address: str | None = None
    backend_name: str = ""
    simulated: bool = False
    info: PrinterInfo | None = None
    message: str = ""
    devices: list[DiscoveredDevice] = field(default_factory=list)


class PrinterManager:
    def __init__(
        self,
        backend: PrinterBackend,
        runner: AsyncRunner | None = None,
        on_state: Callable[[PrinterState], None] | None = None,
        on_queue: Callable[[QueueSnapshot], None] | None = None,
        poll_interval: float = STATUS_POLL_SECONDS,
    ) -> None:
        self.runner = runner or AsyncRunner()
        self._on_state = on_state
        self.state = PrinterState()
        self._backend = backend
        self._poll_interval = poll_interval
        self._attach(backend)
        self.queue: PrintQueue = self.runner.call(
            lambda: PrintQueue(lambda: self._backend, on_queue)).result()
        self.runner.call(self.queue.start).result()
        self._poll_task: concurrent.futures.Future[None] | None = self.runner.submit(self._poll())

    # -- helpers -----------------------------------------------------------------

    @property
    def backend(self) -> PrinterBackend:
        return self._backend

    def _attach(self, backend: PrinterBackend) -> None:
        backend.on_disconnect = self._lost
        self.state.backend_name = backend.display_name
        self.state.simulated = backend.simulated

    def _emit(self, **changes: object) -> None:
        for k, v in changes.items():
            setattr(self.state, k, v)
        if self._on_state:
            try:
                self._on_state(self.state)
            except Exception:  # noqa: BLE001
                log.exception(tr("State-listener faalde"))

    def _lost(self) -> None:
        self._emit(connection=ConnectionState.DISCONNECTED,
                   message=tr("Verbinding verbroken. Je kunt opnieuw verbinden."))

    # -- public (thread-safe, return futures) ------------------------------------------

    def set_backend(self, backend: PrinterBackend) -> concurrent.futures.Future[None]:
        async def _swap() -> None:
            if self._backend.connected:
                await self._backend.disconnect()
            self._backend = backend
            self._attach(backend)
            self._emit(connection=ConnectionState.DISCONNECTED, address=None, info=None,
                       devices=[], message=tr("Backend: {name}", name=backend.display_name))
        return self.runner.submit(_swap())

    def scan(self, timeout: float = 8.0) -> concurrent.futures.Future[list[DiscoveredDevice]]:
        async def _scan() -> list[DiscoveredDevice]:
            self._emit(message=tr("Zoeken naar Bluetooth-apparaten…"))
            try:
                devices = await self._backend.scan(timeout)
            except PrinterError as exc:
                self._emit(message=str(exc))
                raise
            n = sum(d.supported for d in devices)
            self._emit(devices=devices, message=tr(
                "{found} apparaten gevonden, {n} ondersteunde printer(s)",
                found=len(devices), n=n))
            return devices
        return self.runner.submit(_scan())

    def connect(self, address: str | None) -> concurrent.futures.Future[None]:
        async def _connect() -> None:
            self._emit(connection=ConnectionState.CONNECTING, message=tr("Verbinden…"))
            try:
                await self._backend.connect(address)
                info = await self._backend.get_info()
            except PrinterError as exc:
                self._emit(connection=ConnectionState.ERROR, message=str(exc), info=None)
                raise
            except Exception as exc:  # noqa: BLE001 - keep reconnect possible
                log.exception(tr("Verbinden mislukt"))
                self._emit(connection=ConnectionState.ERROR,
                           message=tr("Verbinden mislukt: {error}", error=exc))
                raise PrinterError(str(exc)) from exc
            self._emit(connection=ConnectionState.CONNECTED, address=self._backend.address,
                       info=info, message=tr("Verbonden"))
        return self.runner.submit(_connect())

    def disconnect(self) -> concurrent.futures.Future[None]:
        async def _disc() -> None:
            await self._backend.disconnect()
            self._emit(connection=ConnectionState.DISCONNECTED, info=None, message=tr("Verbroken"))
        return self.runner.submit(_disc())

    def refresh(self) -> concurrent.futures.Future[PrinterInfo | None]:
        async def _refresh() -> PrinterInfo | None:
            if not self._backend.connected:
                return None
            try:
                info = await self._backend.get_info()
            except PrinterError as exc:
                self._emit(message=tr("Status opvragen mislukt: {error}", error=exc))
                if not self._backend.connected:
                    self._lost()
                raise
            self._emit(info=info, message=tr("Status bijgewerkt"))
            return info
        return self.runner.submit(_refresh())

    def enqueue(self, jobs: list[PrintJob]) -> concurrent.futures.Future[list[PrintJob]]:
        return self.runner.call(self.queue.enqueue, jobs)

    def queue_call(self, method: str, *args: object) -> concurrent.futures.Future[object]:
        return self.runner.call(getattr(self.queue, method), *args)

    def shutdown(self) -> None:
        async def _bye() -> None:
            await self.queue.stop()
            try:
                await self._backend.disconnect()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.runner.submit(_bye()).result(5)
        except Exception:  # noqa: BLE001
            pass
        self.runner.stop()

    # -- background status polling ------------------------------------------------------

    async def _poll(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            b = self._backend
            if not b.connected or getattr(b, "busy", False) or self.queue.snapshot().running:
                continue
            try:
                status = await b.get_status()
                battery = await b.get_battery()
            except PrinterError as exc:
                log.info(tr("Statuspoll mislukt: %s"), exc)
                if not b.connected:
                    self._lost()
                continue
            # a new object: the GUI thread may still be reading the old one
            info = replace(self.state.info or PrinterInfo(), status=status, battery=battery)
            self._emit(info=info)
