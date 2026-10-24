"""Printer model descriptions.

A :class:`PrinterProfile` describes the raster geometry of a printer model.
The render engine only depends on the profile, never on a concrete backend,
so adding another label printer means adding a profile plus a backend and
registering them in :mod:`etiknivo.printing.registry`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Label sizes Etiknivo accepts (mm): length along the feed, height across the head.
LABEL_LENGTH_RANGE = (15.0, 100.0)
LABEL_HEIGHT_RANGE = (6.0, 20.0)


@dataclass(frozen=True)
class PrinterProfile:
    key: str
    display_name: str
    printhead_px: int  # dots across the printhead (fixed by hardware)
    dpi: int
    dots_per_mm: int  # integer dot pitch used by the protocol
    label_width_mm: float  # along the feed direction
    label_height_mm: float  # across the printhead
    #: Unprinted margin at both ends of the label (feed direction).  The printer
    #: positions labels with a gap sensor, which is only accurate to about a
    #: millimetre, so content closer to the ends can be cut off.
    feed_margin_mm: float = 0.0
    #: Built-in correction along the feed (dots, positive = later on the label),
    #: for printers that consistently start printing a little early or late.
    #: The user's calibration offset is applied on top of this.
    feed_offset_px: int = 0
    #: Bluetooth names that identify this model when scanning.
    name_prefixes: tuple[str, ...] = ()
    #: Print density levels as shown to the user; the index is passed to the
    #: backend (``print_raster(density=i)``).
    densities: tuple[str, ...] = ("Licht", "Normaal", "Donker")
    default_density: int = 1
    #: Label rolls offered in the printer settings: (length, height) in mm.  The
    #: first is the default; any other size within the ranges above can be typed in.
    label_sizes: tuple[tuple[float, float], ...] = ()

    def with_label(self, length_mm: float, height_mm: float) -> PrinterProfile:
        """This profile for another label roll; sizes outside the accepted range
        are clamped."""
        lo, hi = LABEL_LENGTH_RANGE
        length = min(hi, max(lo, float(length_mm)))
        lo, hi = LABEL_HEIGHT_RANGE
        height = min(hi, max(lo, float(height_mm)))
        return replace(self, label_width_mm=length, label_height_mm=height)

    @property
    def label_size(self) -> tuple[float, float]:
        return self.label_width_mm, self.label_height_mm

    @property
    def label_length_px(self) -> int:
        """Raster rows per label (feed direction)."""
        return round(self.label_width_mm * self.dots_per_mm)

    @property
    def feed_margin_px(self) -> int:
        return round(self.feed_margin_mm * self.dots_per_mm)

    @property
    def label_across_px(self) -> int:
        """Physical label height across the head, in dots (may exceed the head)."""
        return round(self.label_height_mm * self.dots_per_mm)

    @property
    def printable_offset_px(self) -> int:
        """First printable dot row across the label (head is centred on the label)."""
        return max(0, (self.label_across_px - self.printhead_px) // 2)

    @property
    def printable_across_px(self) -> int:
        return min(self.printhead_px, self.label_across_px)

    @property
    def native_raster_size(self) -> tuple[int, int]:
        """(width, height) of the image sent to the printer: head width × label length."""
        return self.printhead_px, self.label_length_px


FICHERO_5836 = PrinterProfile(
    key="fichero_5836",
    display_name="Action Fichero 5836 (AiYin D11s)",
    printhead_px=96,
    dpi=203,
    dots_per_mm=8,
    label_width_mm=30.0,
    label_height_mm=14.0,
    feed_margin_mm=2.0,  # same safe area as the vendor app: 26 × 12 mm
    feed_offset_px=8,  # measured: the print starts ~1 mm early on the label
    name_prefixes=("FICHERO", "D11s_"),
    label_sizes=((30.0, 14.0), (40.0, 14.0), (50.0, 14.0), (22.0, 14.0), (40.0, 12.0),
                 (30.0, 12.0)),
)
