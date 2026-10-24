"""Print queue and printer backends, tested WITHOUT hardware.

``MockPrinterBackend`` simulates a printer; ``FakeBleak`` simulates the BLE
link underneath the D11s backend so we can verify the exact
bytes Etiknivo would send.  None of this proves a physical print works.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from PIL import Image

from etiknivo.model import make_label
from etiknivo.printing import d11s_protocol as proto
from etiknivo.printing.backend import (
    PrinterConnectionError,
    PrinterNotConnected,
    PrinterNotReadyError,
    PrinterStatusInfo,
    PrinterTimeoutError,
)
from etiknivo.printing.ble_link import UART_PROFILES, BleLink, LinkError
from etiknivo.printing.d11s_backend import D11sBackend
from etiknivo.printing.manager import PrinterManager
from etiknivo.printing.mock import MockPrinterBackend
from etiknivo.printing.queue import JobStatus, PrintJob, PrintQueue
from etiknivo.rendering.engine import RenderEngine


def raster(engine: RenderEngine, text: str = "10 kΩ") -> Image.Image:
    return engine.render(make_label("", "", text)).raster


async def run_queue(backend, jobs, **kw) -> PrintQueue:  # noqa: ANN001
    q = PrintQueue(lambda: backend, **kw)
    q.start()
    q.enqueue(jobs)
    await q.wait_idle(5)
    return q


# -- mock printer + queue -------------------------------------------------------------------


async def test_jobs_print_sequentially_with_copies(engine: RenderEngine) -> None:
    b = MockPrinterBackend()
    await b.connect()
    jobs = [PrintJob(f"id{i}", f"L{i}", raster(engine, f"T{i}"), copies=i + 1) for i in range(3)]
    q = await run_queue(b, jobs)
    assert [j.status for j in q.jobs] == [JobStatus.DONE] * 3
    assert len(b.printed) == 1 + 2 + 3
    assert [p.raster for p in b.printed[:1]] == [engine.render(make_label("", "", "T0"))
                                                 .raster_bytes()]
    assert all((p.width, p.height) == (96, 240) for p in b.printed)
    await q.stop()


async def test_double_submission_is_ignored(engine: RenderEngine) -> None:
    b = MockPrinterBackend()
    await b.connect()
    r = raster(engine)
    q = PrintQueue(lambda: b)
    q.start()
    first = q.enqueue([PrintJob("a", "A", r)])
    second = q.enqueue([PrintJob("a", "A", r)])  # double-click
    third = q.enqueue([PrintJob("a", "A", r, copies=2)])  # different job → accepted
    await q.wait_idle(5)
    assert len(first) == 1 and second == [] and len(third) == 1
    assert len(b.printed) == 3
    await q.stop()


async def test_error_stops_queue_and_retry_works(engine: RenderEngine, caplog) -> None:  # noqa: ANN001
    caplog.set_level(logging.INFO, logger="etiknivo.printlog")
    b = MockPrinterBackend()
    await b.connect()
    b.fail_after_labels = 1  # second label raises a Bluetooth error
    jobs = [PrintJob(f"id{i}", f"L{i}", raster(engine, f"T{i}")) for i in range(3)]
    q = await run_queue(b, jobs)
    assert [j.status for j in q.jobs] == [JobStatus.DONE, JobStatus.FAILED, JobStatus.PENDING]
    assert q.paused and "Bluetooth" in q.jobs[1].error
    assert len(b.printed) == 1
    assert "FOUT" in caplog.text and "OK" in caplog.text

    b.fail_after_labels = None
    assert q.retry_failed() == 1
    await q.wait_idle(5)
    assert [j.status for j in q.jobs] == [JobStatus.DONE] * 3
    assert len(b.printed) == 3
    await q.stop()


async def test_printer_not_ready_cover_open(engine: RenderEngine) -> None:
    b = MockPrinterBackend()
    await b.connect()
    b.status_byte = 0x02  # cover open
    q = await run_queue(b, [PrintJob("a", "A", raster(engine))])
    assert q.jobs[0].status == JobStatus.FAILED
    assert "deksel open" in q.jobs[0].error
    b.status_byte = 0x04
    q.retry_failed()
    await q.wait_idle(5)
    assert "papier" in q.jobs[0].error
    await q.stop()


async def test_disconnect_then_reconnect_without_restart(engine: RenderEngine) -> None:
    b = MockPrinterBackend()
    await b.connect()
    b.simulate_disconnect()
    q = await run_queue(b, [PrintJob("a", "A", raster(engine))])
    assert q.jobs[0].status == JobStatus.FAILED and "verbonden" in q.jobs[0].error
    await b.connect()  # reconnect
    q.retry_failed()
    await q.wait_idle(5)
    assert q.jobs[0].status == JobStatus.DONE
    await q.stop()


async def test_pause_cancels_between_copies(engine: RenderEngine) -> None:
    b = MockPrinterBackend(delay=0.05)
    await b.connect()
    q = PrintQueue(lambda: b)
    q.start()
    q.enqueue([PrintJob("a", "A", raster(engine), copies=10),
               PrintJob("b", "B", raster(engine, "x"))])
    await asyncio.sleep(0.12)
    q.pause()
    await q.wait_idle(5)
    assert q.jobs[0].status == JobStatus.CANCELLED
    assert 0 < len(b.printed) < 10
    assert q.jobs[1].status == JobStatus.PENDING  # stays queued until resumed
    q.cancel_pending()
    assert q.jobs[1].status == JobStatus.CANCELLED
    q.clear_finished()
    assert q.jobs == []
    await q.stop()


async def test_invalid_raster_rejected(engine: RenderEngine) -> None:
    b = MockPrinterBackend()
    await b.connect()
    q = await run_queue(b, [PrintJob("a", "A", Image.new("1", (112, 240), 1))])
    assert q.jobs[0].status == JobStatus.FAILED and "printkopbreedte" in q.jobs[0].error


def test_status_flags() -> None:
    assert PrinterStatusInfo.from_byte(0).ok
    s = PrinterStatusInfo.from_byte(0x02 | 0x04 | 0x40 | 0x20)
    assert not s.ok and s.cover_open and s.no_paper and s.overheated and s.charging
    assert "deksel open" in s.describe()
    assert PrinterStatusInfo.from_byte(0xFF).unknown


def test_manager_thread_bridge(engine: RenderEngine) -> None:
    """The manager runs Bluetooth work on a background loop (GUI never blocks)."""
    states, snaps = [], []
    m = PrinterManager(MockPrinterBackend(), on_state=lambda s: states.append(s.connection),
                       on_queue=snaps.append, poll_interval=0.05)
    try:
        assert m.scan().result(5)[0].supported
        m.connect(None).result(5)
        assert states[-1] == "connected"
        m.enqueue([PrintJob("a", "A", raster(engine))]).result(5)
        m.runner.submit(m.queue.wait_idle(5)).result(6)
        assert snaps[-1].jobs[0].status == JobStatus.DONE
        m.backend.simulate_disconnect()
        assert states[-1] == "disconnected"
        m.connect(None).result(5)  # reconnect works
        assert states[-1] == "connected"
    finally:
        m.shutdown()


# -- D11s protocol (pure bytes) --------------------------------------------------------------


def test_protocol_command_bytes() -> None:
    assert proto.set_density(2) == b"\x10\xff\x10\x00\x02"
    assert proto.set_paper_mode(proto.PaperMode.GAP) == b"\x10\xff\x84\x00"
    assert proto.JOB_BEGIN == b"\x10\xff\xfe\x01" and proto.JOB_END == b"\x10\xff\xfe\x45"
    assert proto.JOB_BEGIN not in proto.FOREIGN_JOB_COMMANDS
    img = proto.raster_image(bytes(12 * 240), 96)
    assert img[:8] == b"\x1d\x76\x30\x00\x0c\x00\xf0\x00" and len(img) == 8 + 2880
    with pytest.raises(ValueError):
        proto.set_density(3)
    with pytest.raises(ValueError):
        proto.raster_image(bytes(13), 96)


def test_protocol_reply_parsing() -> None:
    assert proto.battery_percent(b"\x00\x56") == 86
    assert proto.battery_percent(b"\x00\xff") is None and proto.battery_percent(b"") is None
    assert proto.status_byte(b"") == 0xFF and proto.status_byte(b"\x04") == 4
    assert proto.is_ack(b"OK") and proto.is_ack(b"\xaa") and not proto.is_ack(b"\x00")
    assert proto.text(b"D11s\x00") == "D11s" and proto.text(b"") == "?"


# -- D11s backend over a fake BLE link ---------------------------------------------------------


class FakeChar:
    def __init__(self, uuid: str, max_len: int | None = None) -> None:
        self.uuid = uuid
        if max_len is not None:
            self.max_write_without_response_size = max_len


class FakeService:
    def __init__(self, uuid: str, chars: list[FakeChar]) -> None:
        self.uuid = uuid
        self.characteristics = chars


def gatt(profile_index: int = 0, max_len: int | None = 180) -> list[FakeService]:
    svc, write, notify = UART_PROFILES[profile_index]
    return [FakeService("00001800-0000-1000-8000-00805f9b34fb", []),
            FakeService(svc, [FakeChar(write, max_len), FakeChar(notify)])]


class FakeBleak:
    """Stands in for ``bleak.BleakClient`` and answers like a D11s."""

    def __init__(self, device, on_disconnect, *, status: int = 0x00, end_reply: bytes = b"\xaa",
                 silent: bool = False, services=None, fragment: bool = False) -> None:  # noqa: ANN001
        self.device = device
        self.on_disconnect = on_disconnect
        self.is_connected = False
        self.writes: list[bytes] = []
        self.uuids: list[str] = []
        self.status = status
        self.end_reply = end_reply
        self.silent = silent
        self.fragment = fragment
        self.services = gatt() if services is None else services
        self._cb = None

    async def connect(self) -> None:
        self.is_connected = True

    async def disconnect(self) -> None:
        self.is_connected = False

    async def start_notify(self, _uuid, cb) -> None:  # noqa: ANN001
        self._cb = cb

    def drop(self) -> None:
        self.is_connected = False
        self.on_disconnect(self)

    async def write_gatt_char(self, uuid, data, response=False) -> None:  # noqa: ANN001
        data = bytes(data)
        self.writes.append(data)
        self.uuids.append(uuid)
        if self.silent:
            return
        reply = {
            proto.Q_MODEL: b"D11s",
            proto.Q_FIRMWARE: b"2.4.6",
            proto.Q_SERIAL: b"SN123",
            proto.Q_BATTERY: b"\x00\x56",
            proto.Q_STATUS: bytes([self.status]),
            proto.JOB_END: self.end_reply,
        }.get(data)
        if reply is None and data[:3] in (b"\x10\xff\x10", b"\x10\xff\x84"):
            reply = b"OK"
        if reply is None:
            return
        loop = asyncio.get_running_loop()
        if self.fragment and len(reply) > 1:  # reply split over two notifications
            loop.call_soon(self._cb, None, bytearray(reply[:1]))
            loop.call_later(0.01, self._cb, None, bytearray(reply[1:]))
        else:
            loop.call_soon(self._cb, None, bytearray(reply))


class NoDelay:
    after_settings = between_commands = after_raster = after_feed = reconnect_base = 0.0
    chunk_pause = 0.0
    end_of_job_timeout = 1.0


def make_backend(**fake_kw):  # noqa: ANN201
    holder: dict = {}

    def factory(device, cb):  # noqa: ANN001, ANN202
        holder["ble"] = FakeBleak(device, cb, **fake_kw)
        return holder["ble"]

    return D11sBackend(client_factory=factory, timing=NoDelay), holder


async def test_print_sequence_uses_d11s_job_commands(engine: RenderEngine) -> None:
    be, h = make_backend()
    await be.connect("AA:BB")
    assert be.connected
    info = await be.get_info()
    assert info.model == "D11s" and info.firmware == "2.4.6" and info.battery == 86
    assert info.status.ok
    r = engine.render(make_label("A09", "Weerstand", "150 Ω", "¼ W"))
    h["ble"].writes.clear()
    progress = []
    await be.print_raster(r.raster, density=2, copies=2, progress=lambda d, t: progress.append(d))
    w = h["ble"].writes
    image = bytes([0x1D, 0x76, 0x30, 0x00, 0x0C, 0x00, 0xF0, 0x00]) + r.raster_bytes()
    one_copy = [
        b"\x10\xff\x40",  # status check
        b"\x10\xff\x84\x00",  # paper mode: gap labels
        b"\x00" * 12,  # wake
        b"\x10\xff\xfe\x01",  # job begin (D11s)
        *[image[i:i + 180] for i in range(0, len(image), 180)],
        b"\x1d\x0c",  # feed to next label gap
        b"\x10\xff\xfe\x45",  # job end (D11s)
    ]
    assert w == [b"\x10\xff\x10\x00\x02", *one_copy, *one_copy]
    assert not set(proto.FOREIGN_JOB_COMMANDS) & set(w)
    assert progress == [1, 2]
    assert set(h["ble"].uuids) == {UART_PROFILES[0][1]}


async def test_link_picks_available_profile_and_chunk_size(engine: RenderEngine) -> None:
    be, h = make_backend(services=gatt(profile_index=1, max_len=100), fragment=True)
    await be.connect("AA")
    assert (await be.get_info()).model == "D11s"  # fragmented reply reassembled
    h["ble"].writes.clear()
    await be.print_raster(raster(engine))
    assert set(h["ble"].uuids) == {UART_PROFILES[1][1]}
    assert max(len(x) for x in h["ble"].writes) == 100


async def test_link_rejects_unknown_device() -> None:
    link = BleLink(FakeBleak(None, lambda c: None, services=[FakeService("abcd", [])]))
    with pytest.raises(LinkError):
        await link.open()


async def test_not_ready_and_timeout(engine: RenderEngine) -> None:
    be, h = make_backend(status=0x04)
    await be.connect("AA")
    with pytest.raises(PrinterNotReadyError, match="papier"):
        await be.print_raster(raster(engine))
    h["ble"].silent = True
    with pytest.raises(PrinterTimeoutError):
        await be.get_status()


async def test_job_end_without_ack_checks_status(engine: RenderEngine) -> None:
    be, h = make_backend(end_reply=b"\x00")
    await be.connect("AA")
    await be.print_raster(raster(engine))  # no ack but status fine → warning only

    ble = h["ble"]
    orig = ble.write_gatt_char

    async def paper_runs_out(uuid, data, response=False):  # noqa: ANN001, ANN202
        if bytes(data) == proto.JOB_END:
            ble.status = 0x04
        await orig(uuid, data, response)

    ble.write_gatt_char = paper_runs_out
    with pytest.raises(PrinterNotReadyError, match="papier"):
        await be.print_raster(raster(engine))


async def test_disconnect_and_reconnect(engine: RenderEngine) -> None:
    be, h = make_backend()
    lost = []
    be.on_disconnect = lambda: lost.append(True)
    await be.connect("AA")
    h["ble"].drop()
    assert lost and not be.connected
    with pytest.raises(PrinterNotConnected):
        await be.print_raster(raster(engine))
    await be.connect("AA")
    assert be.connected
    await be.print_raster(raster(engine))


async def test_connect_retries_then_fails() -> None:
    attempts = []

    class Broken(FakeBleak):
        async def connect(self) -> None:
            attempts.append(1)
            raise OSError("radio off")

    be = D11sBackend(client_factory=lambda d, cb: Broken(d, cb), timing=NoDelay, connect_attempts=3)
    with pytest.raises(PrinterConnectionError, match="3 pogingen"):
        await be.connect("AA")
    assert len(attempts) == 3 and not be.connected
