"""Shared fixtures.  Every test gets its own data directory and only the
bundled fonts, so results do not depend on the machine's installed fonts."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from etiknivo.rendering import fonts  # noqa: E402
from etiknivo.rendering.engine import RenderEngine  # noqa: E402
from etiknivo.settings import Calibration  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ETIKNIVO_DATA_DIR", str(tmp_path / "data"))
    fonts.set_default_registry(fonts.FontRegistry(scan_system=False))
    yield


@pytest.fixture
def engine() -> RenderEngine:
    return RenderEngine(calibration=Calibration())
