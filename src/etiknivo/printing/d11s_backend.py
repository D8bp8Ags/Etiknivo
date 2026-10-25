"""Bluetooth LE backend for AiYin D11s-class printers (Action Fichero 5836).

Print job, per copy::

    status query → paper mode (gap) → wake → job begin → raster → feed to next
    label → job end (printer answers 0xAA/"OK" once the label is out)

The density is set once per job.  The status is checked before every copy so
a cover opened halfway a batch stops the queue instead of wasting labels.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from PIL import Image

from etiknivo.i18n import tr
from etiknivo.printing import d11s_protocol as proto
from etiknivo.printing.backend import (
    DiscoveredDevice,
    PrintCancelled,
    PrinterBackend,
    PrinterConnectionError,
    PrinterInfo,
    PrinterNotConnected,
    PrinterNotReadyError,
    PrinterStatusInfo,
    PrinterTimeoutError,
    ProgressCallback,
    check_raster,
)
from etiknivo.printing.ble_link import ADVERTISED_SERVICES, BleLink, LinkError, LinkTimeout
from etiknivo.printing.profiles import FICHERO_5836, PrinterProfile
from etiknivo.rendering.engine import raster_to_bytes

log = logging.getLogger(__name__)

ClientFactory = Callable[[Any, Callable[[Any], None]], Any]


def _bleak_factory(device: Any, on_disconnect: Callable[[Any], None]) -> BleakClient:
    return BleakClient(device, disconnected_callback=on_disconnect)


class Timing:
    """Pauses (seconds) where the printer needs time but gives no answer.
    Tests replace this class with zeros."""

    after_settings = 0.1  # let a density/paper setting take effect
    between_commands = 0.05
    after_raster = 0.4  # printhead finishes burning the bitmap
    after_feed = 0.25  # label moved to the gap
    end_of_job_timeout = 45.0  # a long label at low battery can take a while
    reconnect_base = 1.0  # back-off between connection attempts, doubles each time
    chunk_pause = 0.02


class D11sBackend(PrinterBackend):
    """Persistent BLE connection to a D11s-class label printer."""

    profile = FICHERO_5836

    def __init__(self, client_factory: ClientFactory | None = None,
                 timing: type[Timing] = Timing, connect_attempts: int = 3,
                 profile: PrinterProfile | None = None) -> None:
        super().__init__(profile)
        self.display_name = f"{self.profile.display_name} (Bluetooth LE)"
        self._factory = client_factory or _bleak_factory
        self._t = timing
        self._attempts = connect_attempts
        self._link: BleLink | None = None
        self._address: str | None = None
        self._job_lock = asyncio.Lock()

    # -- connection ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._link is not None and self._link.is_connected

    @property
    def address(self) -> str | None:
        return self._address

    @property
    def busy(self) -> bool:
        return self._job_lock.locked()

    def _is_supported(self, name: str, services: list[str]) -> bool:
        return name.upper().startswith(tuple(p.upper() for p in self.profile.name_prefixes)) \
            or any(s.lower() in ADVERTISED_SERVICES for s in services)

    async def scan(self, timeout: float = 8.0) -> list[DiscoveredDevice]:
        try:
            found = await BleakScanner.discover(timeout=timeout, return_adv=True)
        except (BleakError, OSError) as exc:
            raise PrinterConnectionError(
                tr("Bluetooth-scan mislukt: {error}. Staat Bluetooth aan en heeft de app "
                   "Bluetooth-toestemming?", error=exc)) from exc
        devices = []
        for address, (dev, adv) in found.items():
            name = dev.name or adv.local_name or tr("(naamloos)")
            devices.append(DiscoveredDevice(name, address, int(adv.rssi or 0),
                                            self._is_supported(name, list(adv.service_uuids or []))))
        devices.sort(key=lambda d: (not d.supported, -d.rssi))
        return devices

    def _dropped(self, _client: Any) -> None:
        log.warning("Bluetooth-verbinding met %s verbroken", self._address)
        self._link = None
        if self.on_disconnect:
            self.on_disconnect()

    async def _open(self, address: str) -> BleLink:
        target: Any = address
        if self._factory is _bleak_factory:
            target = await BleakScanner.find_device_by_address(address, timeout=10.0)
            if target is None:
                raise PrinterConnectionError(tr("Printer {address} niet gevonden. Staat hij "
                                                "aan en binnen bereik?", address=address))
        client = self._factory(target, self._dropped)
        await client.connect()
        link = BleLink(client, chunk_pause=self._t.chunk_pause)
        try:
            await link.open()
            model = proto.text(await link.request(proto.Q_MODEL))
        except BaseException:
            await link.close()
            raise
        log.info("Verbonden met %s (%s)", address, model)
        return link

    async def connect(self, address: str | None = None) -> None:
        await self.disconnect()
        if not address:
            candidates = [d for d in await self.scan() if d.supported]
            if not candidates:
                raise PrinterConnectionError(tr("Geen ondersteunde labelprinter gevonden. Staat hij aan?"))
            address = candidates[0].address
        problem: Exception | None = None
        for attempt in range(self._attempts):
            try:
                self._link = await self._open(address)
                self._address = address
                return
            except (BleakError, OSError, TimeoutError, LinkError, LinkTimeout,
                    PrinterConnectionError) as exc:
                problem = exc
                log.warning("Verbindingspoging %d/%d mislukt: %s", attempt + 1, self._attempts, exc)
                if attempt + 1 < self._attempts:
                    await asyncio.sleep(self._t.reconnect_base * (2 ** attempt))
        raise PrinterConnectionError(tr("Verbinden mislukt na {n} pogingen: {error}",
                                        n=self._attempts, error=problem))

    async def disconnect(self) -> None:
        link, self._link = self._link, None
        if link is not None:
            await link.close()

    def _require(self) -> BleLink:
        if self._link is None or not self._link.is_connected:
            raise PrinterNotConnected(tr("Geen printer verbonden"))
        return self._link

    async def _call(self, coro):  # type: ignore[no-untyped-def]
        """Translate transport errors into user-facing printer errors."""
        try:
            return await coro
        except LinkTimeout as exc:
            raise PrinterTimeoutError(tr("Printer antwoordt niet (time-out)")) from exc
        except (BleakError, OSError) as exc:
            raise PrinterConnectionError(tr("Bluetooth-fout: {error}", error=exc)) from exc

    # -- queries ----------------------------------------------------------------------

    async def _status(self, link: BleLink) -> PrinterStatusInfo:
        reply = await self._call(link.request(proto.Q_STATUS))
        return proto.decode_status(proto.status_byte(reply))

    async def get_status(self) -> PrinterStatusInfo:
        link = self._require()
        async with self._job_lock:
            return await self._status(link)

    async def get_battery(self) -> int | None:
        link = self._require()
        async with self._job_lock:
            return proto.battery_percent(await self._call(link.request(proto.Q_BATTERY)))

    async def get_info(self) -> PrinterInfo:
        link = self._require()
        async with self._job_lock:
            status = await self._status(link)
            model = proto.text(await self._call(link.request(proto.Q_MODEL)))
            firmware = proto.text(await self._call(link.request(proto.Q_FIRMWARE)))
            serial = proto.text(await self._call(link.request(proto.Q_SERIAL)))
            battery = proto.battery_percent(await self._call(link.request(proto.Q_BATTERY)))
        return PrinterInfo(model, firmware, serial, battery, status)

    # -- printing ---------------------------------------------------------------------

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
        image_cmd = proto.raster_image(raster_to_bytes(raster), raster.width)
        density_cmd = proto.set_density(density)
        link = self._require()
        t = self._t
        async with self._job_lock:
            if not proto.is_ack(await self._call(link.request(density_cmd))):
                log.warning("Printer bevestigde de dichtheid niet")
            await asyncio.sleep(t.after_settings)
            for done in range(copies):
                if cancel is not None and cancel.is_set():
                    raise PrintCancelled(tr("Afdrukken gestopt"))
                status = await self._status(link)
                if not status.ok:
                    raise PrinterNotReadyError(status)
                await self._call(link.request(proto.set_paper_mode(proto.PaperMode.GAP)))
                await asyncio.sleep(t.between_commands)
                await self._call(link.send(proto.WAKE))
                await asyncio.sleep(t.between_commands)
                await self._call(link.send(proto.JOB_BEGIN))
                await asyncio.sleep(t.between_commands)
                await self._call(link.stream(image_cmd))
                await asyncio.sleep(t.after_raster)
                await self._call(link.send(proto.FEED_TO_NEXT_LABEL))
                await asyncio.sleep(t.after_feed)
                reply = await self._call(link.request(proto.JOB_END, timeout=t.end_of_job_timeout))
                if not proto.is_ack(reply):
                    after = await self._status(link)
                    if not after.ok:
                        raise PrinterNotReadyError(after)
                    log.warning("Onverwacht antwoord op einde opdracht: %s (%s)", reply.hex(" "),
                                after.describe())
                if progress:
                    progress(done + 1, copies)
