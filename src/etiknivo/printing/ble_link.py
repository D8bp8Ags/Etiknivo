"""Bluetooth LE transport (request/response over a UART-style GATT service).

D11s-class printers expose several equivalent UART-style services.  Instead
of hard-coding one, :class:`BleLink` looks at the GATT table after connecting
and uses the first known write/notify pair it finds, so firmware variants that
drop a service keep working.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from etiknivo.i18n import tr

log = logging.getLogger(__name__)


def _uuid16(short: int) -> str:
    return f"0000{short:04x}-0000-1000-8000-00805f9b34fb"


#: (service, write characteristic, notify characteristic), in order of preference.
UART_PROFILES: tuple[tuple[str, str, str], ...] = (
    (_uuid16(0x18F0), _uuid16(0x2AF1), _uuid16(0x2AF0)),
    (_uuid16(0xFF00), _uuid16(0xFF02), _uuid16(0xFF01)),
    ("49535343-fe7d-4ae5-8fa9-9fafd205e455", "49535343-8841-43f4-a8d4-ecbe34729bb3",
     "49535343-1e4d-4bd9-ba61-23c647249616"),
)
ADVERTISED_SERVICES = frozenset(p[0] for p in UART_PROFILES)

DEFAULT_CHUNK = 180  # safe payload for a write-without-response on macOS/CoreBluetooth
QUIET_PERIOD = 0.04  # replies may arrive in several notifications; wait for silence


class LinkTimeout(Exception):
    """No reply within the timeout."""


class LinkError(Exception):
    """The GATT table does not contain a supported UART profile."""


class BleLink:
    """Owns a connected Bleak-compatible client and talks request/response."""

    def __init__(self, client: Any, chunk_pause: float = 0.02) -> None:
        self.client = client
        self.chunk_pause = chunk_pause
        self._write_uuid = ""
        self._notify_uuid = ""
        self._chunk = DEFAULT_CHUNK
        self._inbox = bytearray()
        self._arrived = asyncio.Event()
        self._io = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return bool(getattr(self.client, "is_connected", False))

    async def open(self) -> None:
        """Pick the UART profile and subscribe to notifications."""
        available = self._characteristics()
        for _service, write, notify in UART_PROFILES:
            if write in available and notify in available:
                self._write_uuid, self._notify_uuid = write, notify
                break
        else:
            raise LinkError(tr("Geen bekende printerdienst gevonden op dit Bluetooth-apparaat"))
        char = available[self._write_uuid]
        max_len = getattr(char, "max_write_without_response_size", None)
        if isinstance(max_len, int) and max_len >= 20:
            self._chunk = min(max_len, 512)
        await self.client.start_notify(self._notify_uuid, self._on_notify)
        log.info("BLE-profiel %s, blokgrootte %d", self._write_uuid, self._chunk)

    def _characteristics(self) -> dict[str, Any]:
        services = getattr(self.client, "services", None) or []
        found: dict[str, Any] = {}
        for svc in services:
            for ch in getattr(svc, "characteristics", []):
                found[str(ch.uuid).lower()] = ch
        return found

    def _on_notify(self, _sender: Any, data: bytearray) -> None:
        self._inbox.extend(data)
        self._arrived.set()

    async def _write(self, data: bytes) -> None:
        await self.client.write_gatt_char(self._write_uuid, data, response=False)

    async def send(self, data: bytes) -> None:
        """Fire-and-forget command."""
        async with self._io:
            await self._write(data)

    async def request(self, data: bytes, timeout: float = 2.0) -> bytes:
        """Send a command and return the complete reply."""
        async with self._io:
            self._inbox.clear()
            self._arrived.clear()
            await self._write(data)
            try:
                await asyncio.wait_for(self._arrived.wait(), timeout)
            except TimeoutError as exc:
                raise LinkTimeout(tr("Geen antwoord op {cmd} binnen {s} s", cmd=data[:4].hex(" "),
                                    s=f"{timeout:g}")) from exc
            # collect trailing fragments until the line goes quiet
            while True:
                self._arrived.clear()
                try:
                    await asyncio.wait_for(self._arrived.wait(), QUIET_PERIOD)
                except TimeoutError:
                    break
            return bytes(self._inbox)

    async def stream(self, data: bytes, progress: Callable[[int, int], None] | None = None) -> None:
        """Send a large payload in MTU-sized pieces with light pacing so the
        printer's receive buffer is not overrun."""
        async with self._io:
            total = len(data)
            for start in range(0, total, self._chunk):
                await self._write(data[start:start + self._chunk])
                if progress:
                    progress(min(total, start + self._chunk), total)
                if self.chunk_pause:
                    await asyncio.sleep(self.chunk_pause)

    async def close(self) -> None:
        try:
            await self.client.disconnect()
        except Exception as exc:  # noqa: BLE001 - already gone is fine
            log.debug("Disconnect: %s", exc)
