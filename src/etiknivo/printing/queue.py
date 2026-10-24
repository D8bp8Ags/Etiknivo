"""Sequential print queue.

* Jobs run strictly one after another.
* When a job fails the queue pauses: the remaining jobs stay pending until the
  user resumes, and failed jobs can be retried.
* Identical jobs submitted within :attr:`PrintQueue.dedupe_window` seconds
  (e.g. an accidental double-click) are ignored.
* Every result is written to the print log.

The queue is asyncio-based and must only be touched from its event loop
(the GUI uses :class:`etiknivo.printing.runner.AsyncRunner`).
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum

from PIL import Image

from etiknivo.printing.backend import PrintCancelled, PrinterBackend, PrinterError
from etiknivo.rendering.engine import raster_to_bytes

log = logging.getLogger(__name__)
print_log = logging.getLogger("etiknivo.printlog")

_ids = itertools.count(1)


class JobStatus(StrEnum):
    PENDING = "pending"
    PRINTING = "printing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


JOB_STATUS_NL = {
    JobStatus.PENDING: "Wachtend",
    JobStatus.PRINTING: "Bezig",
    JobStatus.DONE: "Klaar",
    JobStatus.FAILED: "Mislukt",
    JobStatus.CANCELLED: "Geannuleerd",
}


@dataclass
class PrintJob:
    label_id: str
    title: str
    raster: Image.Image
    copies: int = 1
    density: int = 1
    id: int = field(default_factory=lambda: next(_ids))
    status: JobStatus = JobStatus.PENDING
    copies_done: int = 0
    error: str = ""
    submitted: float = field(default_factory=time.monotonic)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.copies < 1:
            raise ValueError("Aantal exemplaren moet minimaal 1 zijn")
        if not self.fingerprint:
            h = hashlib.sha1(raster_to_bytes(self.raster))
            h.update(f"|{self.copies}|{self.density}|{self.label_id}".encode())
            self.fingerprint = h.hexdigest()


@dataclass(frozen=True)
class JobSnapshot:
    """Immutable view of a job, safe to hand to another thread."""

    id: int
    label_id: str
    title: str
    copies: int
    copies_done: int
    density: int
    status: JobStatus
    error: str


@dataclass(frozen=True)
class QueueSnapshot:
    jobs: tuple[JobSnapshot, ...]
    paused: bool
    running: bool

    @property
    def pending(self) -> int:
        return sum(j.status == JobStatus.PENDING for j in self.jobs)

    @property
    def failed(self) -> int:
        return sum(j.status == JobStatus.FAILED for j in self.jobs)


class PrintQueue:
    def __init__(
        self,
        backend_getter: Callable[[], PrinterBackend | None],
        on_change: Callable[[QueueSnapshot], None] | None = None,
        dedupe_window: float = 2.0,
    ) -> None:
        self._backend_getter = backend_getter
        self._on_change = on_change
        self.dedupe_window = dedupe_window
        self.jobs: list[PrintJob] = []
        self.paused = False
        self._wakeup = asyncio.Event()
        self._cancel = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._current: PrintJob | None = None
        self._idle = asyncio.Event()
        self._idle.set()

    # -- lifecycle -----------------------------------------------------------------

    def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.get_running_loop().create_task(self._run(), name="print-queue")

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def wait_idle(self, timeout: float | None = None) -> None:
        """Wait until nothing is printing and nothing runnable is pending."""
        async def _wait() -> None:
            while True:
                await self._idle.wait()
                if self._current is None and (self.paused or not self._runnable()):
                    return
                await asyncio.sleep(0.01)
        await asyncio.wait_for(_wait(), timeout)

    # -- user actions ----------------------------------------------------------------

    def enqueue(self, jobs: list[PrintJob]) -> list[PrintJob]:
        """Add jobs; returns the jobs actually accepted (duplicates dropped)."""
        now = time.monotonic()
        accepted: list[PrintJob] = []
        for job in jobs:
            dup = next((j for j in self.jobs
                        if j.fingerprint == job.fingerprint
                        and j.status in (JobStatus.PENDING, JobStatus.PRINTING, JobStatus.DONE)
                        and now - j.submitted < self.dedupe_window), None)
            if dup is not None:
                log.info("Dubbele printopdracht genegeerd: %s", job.title)
                continue
            job.submitted = now
            self.jobs.append(job)
            accepted.append(job)
        if accepted:
            self._kick()
        return accepted

    def pause(self) -> None:
        """Stop after the current label; pending jobs stay in the queue."""
        self.paused = True
        self._cancel.set()
        self._changed()

    def resume(self) -> None:
        self.paused = False
        self._cancel.clear()
        self._kick()

    def retry_failed(self) -> int:
        n = 0
        for j in self.jobs:
            if j.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                j.status, j.error, j.copies_done = JobStatus.PENDING, "", 0
                j.submitted = time.monotonic() - self.dedupe_window
                n += 1
        self.resume()
        return n

    def retry_job(self, job_id: int) -> bool:
        for j in self.jobs:
            if j.id == job_id and j.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                j.status, j.error, j.copies_done = JobStatus.PENDING, "", 0
                self.resume()
                return True
        return False

    def cancel_pending(self) -> int:
        n = 0
        for j in self.jobs:
            if j.status == JobStatus.PENDING:
                j.status = JobStatus.CANCELLED
                n += 1
        self._cancel.set()
        self._changed()
        return n

    def clear_finished(self) -> None:
        self.jobs = [j for j in self.jobs if j.status in (JobStatus.PENDING, JobStatus.PRINTING)]
        self._changed()

    def snapshot(self) -> QueueSnapshot:
        return QueueSnapshot(
            tuple(JobSnapshot(j.id, j.label_id, j.title, j.copies, j.copies_done, j.density,
                              j.status, j.error) for j in self.jobs),
            self.paused,
            self._current is not None,
        )

    # -- worker ----------------------------------------------------------------------

    def _runnable(self) -> PrintJob | None:
        return next((j for j in self.jobs if j.status == JobStatus.PENDING), None)

    def _kick(self) -> None:
        self._wakeup.set()
        self._changed()

    def _changed(self) -> None:
        if self._on_change:
            try:
                self._on_change(self.snapshot())
            except Exception:  # noqa: BLE001 - a broken listener must not kill the queue
                log.exception("Wachtrij-listener faalde")

    async def _run(self) -> None:
        while True:
            job = None if self.paused else self._runnable()
            if job is None:
                self._idle.set()
                self._wakeup.clear()
                await self._wakeup.wait()
                continue
            self._idle.clear()
            await self._print(job)

    async def _print(self, job: PrintJob) -> None:
        backend = self._backend_getter()
        self._current = job
        job.status, job.error, job.copies_done = JobStatus.PRINTING, "", 0
        self._cancel.clear()
        self._changed()

        def progress(done: int, total: int) -> None:
            job.copies_done = done
            self._changed()

        try:
            if backend is None or not backend.connected:
                raise PrinterError("Geen printer verbonden")
            await backend.print_raster(job.raster, density=job.density, copies=job.copies,
                                       progress=progress, cancel=self._cancel)
        except PrintCancelled as exc:
            job.status, job.error = JobStatus.CANCELLED, str(exc)
            print_log.info("GESTOPT  %s  (%d/%d)", job.title, job.copies_done, job.copies)
        except (PrinterError, ValueError, OSError) as exc:
            job.status, job.error = JobStatus.FAILED, str(exc) or type(exc).__name__
            self.paused = True  # stop the queue on error
            print_log.error("FOUT    %s  (%d/%d): %s", job.title, job.copies_done, job.copies,
                            job.error)
        except asyncio.CancelledError:
            job.status, job.error = JobStatus.CANCELLED, "Afgebroken"
            raise
        except Exception as exc:  # noqa: BLE001 - unexpected, but keep the app alive
            log.exception("Onverwachte fout tijdens printen")
            job.status, job.error = JobStatus.FAILED, f"Onverwachte fout: {exc}"
            self.paused = True
            print_log.error("FOUT    %s: %s", job.title, job.error)
        else:
            job.status = JobStatus.DONE
            sim = " [SIMULATIE]" if backend is not None and backend.simulated else ""
            print_log.info("OK      %s  ×%d  dichtheid=%d%s", job.title, job.copies, job.density,
                           sim)
        finally:
            self._current = None
            self._changed()


def clone_job(job: PrintJob) -> PrintJob:
    return replace(job, id=next(_ids), status=JobStatus.PENDING, copies_done=0, error="")
