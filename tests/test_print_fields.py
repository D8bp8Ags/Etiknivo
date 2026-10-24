"""{Datum}, {Nr} and {Aantal}: fields filled in per printed copy."""

from __future__ import annotations

import asyncio
from datetime import date

from etiknivo import i18n
from etiknivo.model import make_label, today_text
from etiknivo.printing.mock import MockPrinterBackend
from etiknivo.printing.queue import JobStatus, PrintJob, PrintQueue
from tests.test_gui import connect, window  # noqa: F401 - fixture


def label(text: str):  # noqa: ANN201
    return make_label("A1", "Weerstanden", text)


def test_print_fields_resolve(monkeypatch) -> None:  # noqa: ANN001
    day = date(2026, 3, 7)
    lbl = label("{Nr}/{aantal} {Datum}")
    assert lbl.for_copy(2, 5, day).lines[1].text == "2/5 07-03-2026"
    assert lbl.resolve("{Nr} van {Aantal}")[0] == "1 van 1"  # preview: copy 1 of 1
    assert lbl.uses_copy_number() and not label("{Aantal} {Datum}").uses_copy_number()
    assert {"Datum", "Nr", "Aantal"} <= set(lbl.field_names())
    monkeypatch.setattr(i18n, "_language", "en")
    assert today_text(day) == "2026-03-07"
    assert lbl.for_copy(1, 2, day).lines[1].text == "1/2 2026-03-07"


def test_own_specification_wins() -> None:
    lbl = label("{Aantal} st. #{Nr}")
    lbl.specs["Aantal"] = "100"
    copy = lbl.for_copy(3, 4)
    assert copy.lines[1].text == "{Aantal} st. #3"  # the specification is filled in later
    assert copy.display_text(copy.lines[1]) == "100 st. #3"
    assert lbl.resolve("{Aantal}")[0] == "100"


def test_code_text_gets_copy_number() -> None:
    lbl = label("x")
    lbl.code.text = "{Lade}-{Nr}"
    assert lbl.uses_copy_number()
    assert lbl.for_copy(4, 9).code.text == "{Lade}-4"


def test_queue_prints_each_copy_raster(engine) -> None:  # noqa: ANN001
    lbl = label("Nr {Nr}")
    rasters = [engine.render(lbl.for_copy(n, 3)).raster for n in (1, 2, 3)]
    assert len({r.tobytes() for r in rasters}) == 3

    async def run() -> tuple[MockPrinterBackend, PrintJob]:
        backend = MockPrinterBackend(delay=0)
        await backend.connect("")
        q = PrintQueue(lambda: backend)
        q.start()
        job = PrintJob(lbl.id, "A1", rasters[0], 1, 1, copy_rasters=rasters)
        q.enqueue([job])
        await q.wait_idle(5)
        await q.stop()
        return backend, job

    backend, job = asyncio.run(run())
    assert job.status == JobStatus.DONE and job.copies == job.copies_done == 3
    assert [p.raster for p in backend.printed] == [
        engine.render(lbl.for_copy(n, 3)).raster_bytes() for n in (1, 2, 3)]


def test_main_window_numbers_copies(qtbot, window) -> None:  # noqa: ANN001, F811
    lbl = window.current
    lbl.lines[1].text = "{Nr}"
    job = window.make_job(lbl, 2, 1)
    assert job.copies == 2 and job.copy_rasters is not None
    lbl.lines[1].text = "{Aantal}"
    job = window.make_job(lbl, 2, 1)
    assert job.copies == 2 and job.copy_rasters is None
    assert job.raster.tobytes() == window.engine.render(lbl.for_copy(1, 2)).raster.tobytes()
