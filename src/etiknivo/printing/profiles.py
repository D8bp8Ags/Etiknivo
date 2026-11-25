"""Printer model descriptions.

A :class:`PrinterProfile` describes the raster geometry of a printer model.
The render engine only depends on the profile, never on a concrete backend,
so adding another label printer means adding a profile plus a backend and
registering them in :mod:`etiknivo.printing.registry`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from etiknivo.i18n import N_, tr

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
    #: Margin at the end of the label (the right in the design) when it differs
    #: from the start; ``None`` uses :attr:`feed_margin_mm` at both ends.
    feed_margin_end_mm: float | None = None
    #: Built-in correction along the feed (dots, positive = later on the label),
    #: for printers that consistently start printing a little early or late.
    #: The user's calibration offset is applied on top of this.
    feed_offset_px: int = 0
    #: Bluetooth names that identify this model when scanning.
    name_prefixes: tuple[str, ...] = ()
    #: Print density levels (untranslated, see :meth:`density_names`); the
    #: index is passed to the backend (``print_raster(density=i)``).
    densities: tuple[str, ...] = (N_("Licht"), N_("Normaal"), N_("Donker"))
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

    def density_names(self) -> tuple[str, ...]:
        """The density levels as shown to the user, in the active language."""
        return tuple(tr(name) for name in self.densities)

    @property
    def label_size(self) -> tuple[float, float]:
        return self.label_width_mm, self.label_height_mm

    @property
    def label_length_px(self) -> int:
        """Raster rows per label (feed direction)."""
        return round(self.label_width_mm * self.dots_per_mm)

    @property
    def feed_margin_px(self) -> int:
        """Margin at the start of the label (left in the design), in dots."""
        return round(self.feed_margin_mm * self.dots_per_mm)

    @property
    def feed_margin_end_px(self) -> int:
        """Margin at the end of the label (right in the design), in dots."""
        end = self.feed_margin_mm if self.feed_margin_end_mm is None else self.feed_margin_end_mm
        return round(end * self.dots_per_mm)

    @property
    def safe_length_mm(self) -> float:
        """Length of the safe printable area along the feed."""
        return (self.label_length_px - self.feed_margin_px - self.feed_margin_end_px) / self.dots_per_mm

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
    # Measured with the edge tests (2026-11-25): the printer ends every raster at
    # the same place, 0.8-1.5 mm (on average 1.25 mm) before the end of the
    # label, whatever its length; the whole print wanders ~0.5 mm from label to
    # label.  The offset of 10 dots (1.25 mm) puts the design on the label on
    # average and cuts the last 1.25 mm of the design, so a margin of 1.25 mm at
    # both ends is the largest centred safe area: 27.5 × 12 mm.
    feed_margin_mm=1.25,
    feed_offset_px=10,
    name_prefixes=("FICHERO", "D11s_"),
    label_sizes=((30.0, 14.0), (40.0, 14.0), (50.0, 14.0), (22.0, 14.0), (40.0, 12.0),
                 (30.0, 12.0)),
)
