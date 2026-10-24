"""Supported printer models: which profile goes with which backend.

Adding a label printer takes three steps:

1. Describe its geometry in a :class:`~etiknivo.printing.profiles.PrinterProfile`
   (printhead width, dpi, label size, safe margins, density names).
2. Write a :class:`~etiknivo.printing.backend.PrinterBackend` for its protocol
   (scan, connect, status, ``print_raster``), or reuse an existing one when the
   printer speaks the same protocol.
3. Register both below with :func:`register`.

Everything else (rendering, previews, calibration, print queue, simulation and
the GUI) is driven by the profile and needs no changes.  The model in use is
``Settings.printer_model``; the GUI offers a choice once more than one model
is registered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from etiknivo.printing.backend import PrinterBackend
from etiknivo.printing.profiles import FICHERO_5836, PrinterProfile


@dataclass(frozen=True)
class PrinterModel:
    profile: PrinterProfile
    #: Creates the backend for the real printer.  Imported lazily, so the
    #: Bluetooth stack is only loaded when a real printer is used.
    create_backend: Callable[[PrinterProfile], PrinterBackend]

    @property
    def key(self) -> str:
        return self.profile.key

    @property
    def display_name(self) -> str:
        return self.profile.display_name


MODELS: dict[str, PrinterModel] = {}
DEFAULT_MODEL = FICHERO_5836.key


def register(model: PrinterModel) -> PrinterModel:
    MODELS[model.key] = model
    return model


def get_model(key: str) -> PrinterModel:
    """The registered model *key*, or the default for unknown keys."""
    return MODELS.get(key) or MODELS[DEFAULT_MODEL]


def create_backend(key: str, *, simulated: bool = False, delay: float = 0.4) -> PrinterBackend:
    """Backend for model *key*: the real printer, or a simulation of it."""
    model = get_model(key)
    if simulated:
        from etiknivo.printing.mock import MockPrinterBackend

        return MockPrinterBackend(model.profile, delay=delay)
    return model.create_backend(model.profile)


# -- built-in models -----------------------------------------------------------------


def _d11s(profile: PrinterProfile) -> PrinterBackend:
    from etiknivo.printing.d11s_backend import D11sBackend

    return D11sBackend(profile=profile)


register(PrinterModel(FICHERO_5836, _d11s))
