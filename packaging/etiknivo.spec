# PyInstaller spec for the macOS .app bundle.
#
#   uv sync --group build
#   uv run pyinstaller packaging/etiknivo.spec --noconfirm
#
# Result: dist/Etiknivo.app
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent  # noqa: F821 - provided by PyInstaller

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("etiknivo"),
    hiddenimports=["bleak.backends.corebluetooth"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Etiknivo",
    console=False,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Etiknivo")  # noqa: F821
app = BUNDLE(  # noqa: F821
    coll,
    name="Etiknivo.app",
    icon=None,
    bundle_identifier="io.github.etiknivo",
    info_plist={
        "CFBundleName": "Etiknivo",
        "CFBundleDisplayName": "Etiknivo",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
        # Required on macOS, otherwise the app is killed when it touches Bluetooth.
        "NSBluetoothAlwaysUsageDescription":
            "Etiknivo gebruikt Bluetooth om etiketten af te drukken op je labelprinter.",
        "NSBluetoothPeripheralUsageDescription":
            "Etiknivo gebruikt Bluetooth om etiketten af te drukken op je labelprinter.",
    },
)
