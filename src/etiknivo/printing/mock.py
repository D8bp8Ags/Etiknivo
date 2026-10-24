"""Simulated printer for development and tests.

The mock never pretends to be hardware: it is labelled "Simulatie" in the GUI
and its results must not be read as proof that a physical print works.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from PIL import Image

from etiknivo.printing.backend import (
    DiscoveredDevice,
    PrintCancelled,
    PrinterBackend,
    PrinterConnectionError,
    PrinterInfo,
    PrinterNotConnected,
    PrinterNotReadyError,
    PrinterStatusInfo,
    ProgressCallback,
    check_raster,
)
from etiknivo.printing.profiles import PrinterProfile
from etiknivo.rendering.engine import raster_to_bytes

MOCK_ADDRESS = "00:00:00:00:00:00"


@dataclass
class PrintedLabel:
    raster: bytes
    width: int
    height: int
    density: int


class MockPrinterBackend(PrinterBackend):
    """In-memory printer.  Failure modes can be injected by tests."""

    display_name = "Simulatie (geen echte printer)"
    simulated = True

    def __init__(self, profile: PrinterProfile | None = None, *, delay: float = 0.0) -> None:
        super().__init__(profile)
        self.delay = delay
        self._connected = False
        self.battery = 86
        self.status = PrinterStatusInfo()  # tests set e.g. PrinterStatusInfo(cover_open=True)
        self.printed: list[PrintedLabel] = []
        # failure injection
        self.fail_connect: Exception | None = None
        self.fail_after_labels: int | None = None  # raise after N successful labels
        self.fail_exception: Exception = PrinterConnectionError("Gesimuleerde Bluetooth-fout")
        self.calls: list[str] = []

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def address(self) -> str | None:
        return MOCK_ADDRESS if self._connected else None

    async def scan(self, timeout: float = 8.0) -> list[DiscoveredDevice]:
        self.calls.append("scan")
        await asyncio.sleep(min(self.delay, 0.2))
        return [DiscoveredDevice(f"{self.profile.display_name} (simulatie)", MOCK_ADDRESS,
                                 -40, True)]

    async def connect(self, address: str | None = None) -> None:
        self.calls.append("connect")
        await asyncio.sleep(self.delay)
        if self.fail_connect is not None:
            raise self.fail_connect
        self._connected = True

    async def disconnect(self) -> None:
        self.calls.append("disconnect")
        self._connected = False

    def simulate_disconnect(self) -> None:
        """Drop the link as if Bluetooth went away."""
        self._connected = False
        if self.on_disconnect:
            self.on_disconnect()

    def _require(self) -> None:
        if not self._connected:
            raise PrinterNotConnected("Geen printer verbonden")

    async def get_status(self) -> PrinterStatusInfo:
        self._require()
        return self.status

    async def get_battery(self) -> int | None:
        self._require()
        return self.battery

    async def get_info(self) -> PrinterInfo:
        self._require()
        return PrinterInfo(f"{self.profile.display_name} (simulatie)", "mock", "SIM-0001",
                           self.battery,
                           await self.get_status())

    async def print_raster(
        self,
        raster: Image.Image,
        *,
        density: int = 1,
        copies: int = 1,
        progress: ProgressCallback | None = None,
        cancel: asyncio.Event | None = None,
    ) -> None:
        check_raster(raster, self.profile)
        data = raster_to_bytes(raster)
        for n in range(copies):
            if cancel is not None and cancel.is_set():
                raise PrintCancelled("Afdrukken gestopt")
            self._require()
            status = self.status
            if not status.ok:
                raise PrinterNotReadyError(status)
            if self.fail_after_labels is not None and len(self.printed) >= self.fail_after_labels:
                raise self.fail_exception
            await asyncio.sleep(self.delay)
            self.printed.append(PrintedLabel(data, raster.width, raster.height, density))
            if progress:
                progress(n + 1, copies)
