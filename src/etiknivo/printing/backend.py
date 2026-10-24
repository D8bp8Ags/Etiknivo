"""Printer backend interface.

The GUI and the print queue only talk to :class:`PrinterBackend`.  Concrete
backends (the Fichero BLE backend, the mock printer) can be swapped without
touching the rest of the application.  See :mod:`etiknivo.printing.registry`
for how a printer model is tied to its backend.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from PIL import Image

from etiknivo.printing.profiles import FICHERO_5836, PrinterProfile

ProgressCallback = Callable[[int, int], None]  # (copies_done, copies_total)


class PrinterError(Exception):
    """Base class for printer problems.  Messages are user-facing (Dutch)."""


class PrinterConnectionError(PrinterError):
    """Connecting failed or the connection was lost."""


class PrinterNotConnected(PrinterConnectionError):
    """An operation needs a connected printer."""


class PrinterTimeoutError(PrinterError):
    """The printer did not answer in time."""


class PrinterNotReadyError(PrinterError):
    """The printer reports a condition that prevents printing."""

    def __init__(self, status: PrinterStatusInfo) -> None:
        super().__init__(f"Printer niet gereed: {status.describe()}")
        self.status = status


class PrintCancelled(PrinterError):
    """The job was stopped by the user."""


class ConnectionState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass(frozen=True)
class DiscoveredDevice:
    name: str
    address: str
    rssi: int = 0
    supported: bool = False


@dataclass(frozen=True)
class PrinterStatusInfo:
    """Printer condition, independent of how a model reports it.  Backends
    decode their own status format into this (see ``d11s_protocol``)."""

    raw: int = 0
    printing: bool = False
    cover_open: bool = False
    no_paper: bool = False
    low_battery: bool = False
    overheated: bool = False
    charging: bool = False
    unknown: bool = False

    @property
    def ok(self) -> bool:
        return not (self.cover_open or self.no_paper or self.overheated)

    def problems(self) -> list[str]:
        out = []
        if self.cover_open:
            out.append("deksel open")
        if self.no_paper:
            out.append("papier op / geen etiket gedetecteerd")
        if self.overheated:
            out.append("printkop oververhit")
        if self.low_battery:
            out.append("batterij bijna leeg")
        return out

    def describe(self) -> str:
        if self.unknown:
            return "onbekend (geen antwoord)"
        parts = self.problems()
        if self.printing:
            parts.append("bezig met printen")
        if self.charging:
            parts.append("laadt op")
        return ", ".join(parts) if parts else "gereed"


@dataclass
class PrinterInfo:
    model: str = "?"
    firmware: str = "?"
    serial: str = "?"
    battery: int | None = None
    status: PrinterStatusInfo = field(default_factory=PrinterStatusInfo)


class PrinterBackend(ABC):
    """Abstract printer backend.  All methods run on an asyncio loop."""

    #: Default model; a backend that drives several models gets the actual
    #: profile passed in.
    profile: PrinterProfile = FICHERO_5836
    #: Human-readable backend name shown in the GUI.
    display_name: str = "Printer"
    #: True for simulated backends; the GUI labels these clearly.
    simulated: bool = False

    def __init__(self, profile: PrinterProfile | None = None) -> None:
        if profile is not None:
            self.profile = profile
        self.on_disconnect: Callable[[], None] | None = None

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    @property
    def address(self) -> str | None:
        return None

    @abstractmethod
    async def scan(self, timeout: float = 8.0) -> list[DiscoveredDevice]: ...

    @abstractmethod
    async def connect(self, address: str | None = None) -> None:
        """Connect to *address*, or discover the first supported printer."""

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_status(self) -> PrinterStatusInfo: ...

    @abstractmethod
    async def get_battery(self) -> int | None: ...

    @abstractmethod
    async def get_info(self) -> PrinterInfo: ...

    @abstractmethod
    async def print_raster(
        self,
        raster: Image.Image,
        *,
        density: int = 1,
        copies: int = 1,
        progress: ProgressCallback | None = None,
        cancel: asyncio.Event | None = None,
    ) -> None:
        """Print a native-orientation 1-bit raster ``copies`` times.

        Each copy is positioned on its own label using gap detection (form
        feed).  Raises :class:`PrinterError` subclasses on failure.
        """


def check_raster(raster: Image.Image, profile: PrinterProfile) -> None:
    if raster.mode != "1":
        raise ValueError(f"Raster moet 1-bit zijn (mode '1'), niet '{raster.mode}'")
    if raster.width != profile.printhead_px:
        raise ValueError(f"Rasterbreedte {raster.width} ≠ printkopbreedte {profile.printhead_px}")
    if not 1 <= raster.height <= 0xFFFF:
        raise ValueError(f"Ongeldige rasterhoogte {raster.height}")
