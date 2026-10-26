"""Keeping personal details out of what Etiknivo shows, logs and writes.

People share screenshots, ``app.log`` and copied log text in bug reports, so
those never carry the user's home folder (which holds the account name) or the
full Bluetooth address of their printer.
"""

from __future__ import annotations

import logging
import re
from functools import cache
from pathlib import Path

# 6 hex pairs (MAC on Windows/Linux) or a CoreBluetooth UUID (macOS)
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")


@cache
def _home_forms() -> tuple[str, ...]:
    """The ways the home folder can appear in text, longest first."""
    home = Path.home()
    forms = {str(home), home.as_posix()}
    try:
        forms |= {str(home.resolve()), home.resolve().as_posix()}
    except OSError:
        pass
    # a home of "/" or "C:\" would turn every path into "~"
    return tuple(sorted((f.rstrip("/\\") for f in forms if len(f.rstrip("/\\")) > 3),
                        key=len, reverse=True))


def short_path(path: Path | str) -> str:
    """*path* with the home folder as ``~``, so screenshots don't show the user name."""
    path = Path(path)
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def short_address(address: str | None) -> str:
    """A Bluetooth address with only its last part visible: enough to tell two
    printers apart, not enough to identify the device.  ``…:9B:3C`` or ``…A1F2``."""
    if not address:
        return ""
    if _MAC.fullmatch(address):
        return "…" + address[-6:].upper()
    tail = address.replace("-", "")[-4:]
    return "…" + tail.upper() if len(address) > 8 else address


def redact(text: str) -> str:
    """*text* with the home folder replaced by ``~`` and MAC addresses shortened.
    Meant for log output; it leaves everything else alone."""
    for form in _home_forms():
        if form.lower() in text.lower():
            # Windows paths ignore case; the home ".../an" must not eat ".../anna"
            flags = re.IGNORECASE if "\\" in form or ":" in form else 0
            text = re.sub(re.escape(form) + r"(?![\w.-])", "~", text, flags=flags)
    if _MAC.search(text):
        text = _MAC.sub(lambda m: short_address(m.group(0)) if set(m.group(0)) - set("0:-")
                        else m.group(0), text)
    return text


class RedactingFormatter(logging.Formatter):
    """A :class:`logging.Formatter` whose output (tracebacks included) goes
    through :func:`redact`."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))
