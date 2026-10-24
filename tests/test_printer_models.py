"""Adding a printer model only takes a profile, a backend and a registration."""

from __future__ import annotations

import dataclasses

import pytest

from etiknivo.printing import registry
from etiknivo.printing.d11s_backend import D11sBackend
from etiknivo.printing.mock import MockPrinterBackend
from etiknivo.printing.profiles import FICHERO_5836, PrinterProfile
from etiknivo.rendering.engine import RenderEngine
from etiknivo.settings import Calibration, Settings

# A made-up wider printer: 12 mm head on 40 × 15 mm labels, two densities.
WIDE = PrinterProfile(
    key="test_wide", display_name="Testprinter 40×15", printhead_px=96, dpi=203,
    dots_per_mm=8, label_width_mm=40.0, label_height_mm=15.0, feed_margin_mm=1.0,
    densities=("Normaal", "Donker"), default_density=0,
)


class WideBackend(MockPrinterBackend):
    simulated = False
    display_name = "Testprinter (eigen protocol)"


@pytest.fixture
def wide_model(monkeypatch):  # noqa: ANN201
    monkeypatch.setattr(registry, "MODELS", dict(registry.MODELS))
    return registry.register(registry.PrinterModel(WIDE, lambda p: WideBackend(p)))


def test_builtin_model_and_fallback() -> None:
    assert registry.get_model("fichero_5836").profile is FICHERO_5836
    assert registry.get_model("bestaat-niet").key == registry.DEFAULT_MODEL
    real = registry.create_backend("fichero_5836")
    assert isinstance(real, D11sBackend) and real.profile is FICHERO_5836
    sim = registry.create_backend("fichero_5836", simulated=True)
    assert isinstance(sim, MockPrinterBackend) and sim.simulated


def test_registered_model_gets_its_own_backend_and_profile(wide_model) -> None:  # noqa: ANN001
    be = registry.create_backend("test_wide")
    assert isinstance(be, WideBackend) and be.profile is WIDE
    sim = registry.create_backend("test_wide", simulated=True)
    assert sim.simulated and sim.profile is WIDE


def test_rendering_follows_the_profile() -> None:
    eng = RenderEngine(WIDE, Calibration())
    assert eng.design_size == (320, 120)
    from etiknivo.model import make_label

    r = eng.render(make_label("A1", "Test", "Breed label", "40 mm"))
    assert r.raster.size == WIDE.native_raster_size == (96, 320)
    assert not r.has_overflow


async def test_simulated_wide_printer_accepts_its_raster() -> None:
    from etiknivo.model import make_label

    be = MockPrinterBackend(WIDE)
    await be.connect()
    r = RenderEngine(WIDE, Calibration()).render(make_label("A1", "", "x"))
    await be.print_raster(r.raster, density=1)
    assert be.printed[0].height == 320
    assert "Testprinter" in (await be.get_info()).model


def test_gui_uses_profile_of_selected_model(qtbot, wide_model) -> None:  # noqa: ANN001
    from etiknivo.gui import main_window as mw
    from etiknivo.settings import data_dir
    from etiknivo.storage.library import open_library

    lib, _ = open_library(data_dir() / "library.json")
    win = mw.MainWindow(lib, Settings(use_mock_printer=True, printer_model="test_wide",
                                      density=2), poll_interval=3600)
    qtbot.addWidget(win)
    assert win.profile is WIDE
    assert win.raster_view.result.raster.size == (96, 320)
    dens = win.printer_panel.density
    assert [dens.itemText(i) for i in range(dens.count())] == ["Normaal", "Donker"]
    assert dens.currentIndex() == 0  # stored level 2 does not exist: model default
    assert win.native.text() == "Native 96 × 320"
    assert win.printer_panel.model.isVisibleTo(win.printer_panel)  # two models: choice shown
    assert win.bridge.manager.backend.profile is WIDE


def test_profile_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        FICHERO_5836.dpi = 300  # type: ignore[misc]
