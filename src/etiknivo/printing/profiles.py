"""Printer model descriptions.

A :class:`PrinterProfile` describes the raster geometry of a printer model.
The render engine only depends on the profile, never on a concrete backend,
so adding another label printer means adding a profile plus a backend.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrinterProfile:
    key: str
    display_name: str
    printhead_px: int  # dots across the printhead (fixed by hardware)
    dpi: int
    dots_per_mm: int  # integer dot pitch used by the protocol
    label_width_mm: float  # along the feed direction
    label_height_mm: float  # across the printhead
    name_prefixes: tuple[str, ...] = ()
    densities: tuple[str, ...] = ("Licht", "Normaal", "Donker")

    @property
    def label_length_px(self) -> int:
        """Raster rows per label (feed direction)."""
        return round(self.label_width_mm * self.dots_per_mm)

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
    name_prefixes=("FICHERO", "D11s_"),
)

PROFILES: dict[str, PrinterProfile] = {FICHERO_5836.key: FICHERO_5836}


def get_profile(key: str) -> PrinterProfile:
    return PROFILES.get(key, FICHERO_5836)
