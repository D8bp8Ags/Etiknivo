"""Runs an asyncio event loop in a background thread.

Bluetooth I/O (Bleak) and the print queue live on this loop, so the Qt GUI
thread never blocks.  Results come back as :class:`concurrent.futures.Future`.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class AsyncRunner:
    def __init__(self, name: str = "etiknivo-async") -> None:
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._main, name=name, daemon=True)
        self._thread.start()
        self._ready.wait()

    def _main(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.call_soon(self._ready.set)
        self.loop.run_forever()

    def submit(self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """Schedule a coroutine on the loop."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call(self, fn: Callable[..., T], *args: Any) -> concurrent.futures.Future[T]:
        """Run a plain function on the loop thread and return its result."""
        fut: concurrent.futures.Future[T] = concurrent.futures.Future()

        def _run() -> None:
            try:
                fut.set_result(fn(*args))
            except BaseException as exc:  # noqa: BLE001
                fut.set_exception(exc)

        self.loop.call_soon_threadsafe(_run)
        return fut

    def stop(self, timeout: float = 3.0) -> None:
        if not self.loop.is_running():
            return

        async def _shutdown() -> None:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        try:
            self.submit(_shutdown()).result(timeout)
        except Exception:  # noqa: BLE001
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout)
