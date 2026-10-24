"""Command set of AiYin D11s-class thermal label printers (Action Fichero 5836).

This module only builds and parses bytes; it does no I/O.  It is kept separate
from the Bluetooth transport so the protocol can be unit-tested byte for byte
and reused for other transports (e.g. a serial/SPP link).

Command families
----------------
* ``10 FF xx ...``  vendor commands: settings, queries and print-job control.
  Most of them answer with ASCII (``"OK"``, a version string) or a short binary
  value delivered through a BLE notification.
* ``1D 76 30 ...``  the standard ESC/POS *GS v 0* raster bitmap command
  (Epson ESC/POS reference): 1 bit per dot, MSB = leftmost dot, 1 = black.
* ``1D 0C``         ESC/POS form feed; on label stock the printer advances to
  the start of the next label using its gap sensor.

Job framing is model specific.  D11s-class (AiYin) firmware expects
``10 FF FE 01`` to start and ``10 FF FE 45`` to finish a job.  Other printers
built on the same vendor platform use ``10 FF F1 03`` / ``10 FF F1 45``; a
D11s silently ignores those, so they must never be sent to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

VENDOR = b"\x10\xff"


class PaperMode(IntEnum):
    GAP = 0  # die-cut labels with a gap between them
    BLACK_MARK = 1
    CONTINUOUS = 2


class Density(IntEnum):
    LIGHT = 0
    NORMAL = 1
    DARK = 2


# -- query commands (answer expected) ---------------------------------------------------

Q_MODEL = VENDOR + b"\x20\xf0"
Q_FIRMWARE = VENDOR + b"\x20\xf1"
Q_SERIAL = VENDOR + b"\x20\xf2"
Q_BATTERY = VENDOR + b"\x50\xf1"
Q_STATUS = VENDOR + b"\x40"

# -- job control ----------------------------------------------------------------------------

#: Some firmware ignores the first bytes after an idle period; a short run of
#: zero bytes wakes the receiver before the job starts.
WAKE = bytes(12)
JOB_BEGIN = VENDOR + b"\xfe\x01"
JOB_END = VENDOR + b"\xfe\x45"
FEED_TO_NEXT_LABEL = b"\x1d\x0c"

#: Job framing used by *other* models of the platform.  Listed only so tests
#: can assert they are never sent to a D11s.
FOREIGN_JOB_COMMANDS = (VENDOR + b"\xf1\x03", VENDOR + b"\xf1\x45")


def set_density(level: int) -> bytes:
    level = int(level)
    if level not in tuple(Density):
        raise ValueError(f"Dichtheid {level} ongeldig (0, 1 of 2)")
    return VENDOR + bytes([0x10, 0x00, level])


def set_paper_mode(mode: PaperMode = PaperMode.GAP) -> bytes:
    return VENDOR + bytes([0x84, int(PaperMode(mode))])


def raster_image(packed: bytes, width_dots: int) -> bytes:
    """ESC/POS ``GS v 0`` (normal scale) with header and bitmap.

    *packed* holds ``height`` rows of ``width_dots / 8`` bytes each.
    """
    if width_dots % 8:
        raise ValueError("Rasterbreedte moet een veelvoud van 8 zijn")
    row_bytes = width_dots // 8
    rows, rest = divmod(len(packed), row_bytes)
    if rest or not 0 < rows <= 0xFFFF:
        raise ValueError(f"Ongeldige rastergrootte: {len(packed)} bytes voor {row_bytes} bytes/rij")
    header = b"\x1d\x76\x30\x00" + row_bytes.to_bytes(2, "little") + rows.to_bytes(2, "little")
    return header + packed


# -- replies --------------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusBits:
    """Bit layout of the one-byte answer to :data:`Q_STATUS`."""

    PRINTING = 0x01
    COVER_OPEN = 0x02
    NO_PAPER = 0x04
    LOW_BATTERY = 0x08
    OVERHEAT_A = 0x10
    CHARGING = 0x20
    OVERHEAT_B = 0x40


def status_byte(reply: bytes) -> int:
    """Last byte of a status reply, or 0xFF when the printer did not answer."""
    return reply[-1] if reply else 0xFF


def battery_percent(reply: bytes) -> int | None:
    """Battery replies are ``[state, percent]``; returns None if implausible."""
    if len(reply) >= 2 and 0 <= reply[-1] <= 100:
        return reply[-1]
    return None


def text(reply: bytes) -> str:
    return reply.decode("ascii", errors="replace").strip("\x00 \r\n") or "?"


def is_ack(reply: bytes) -> bool:
    """Settings answer ``OK``; the end-of-job answer is ``0xAA`` or ``OK``."""
    return reply.startswith(b"OK") or reply[:1] == b"\xaa"
