# PyInstaller spec for macOS, Windows and Linux.
#
#   uv sync --group build
#   uv run pyinstaller packaging/etiknivo.spec --noconfirm
#
# Result:
#   macOS    dist/Etiknivo.app
#   Windows  dist/Etiknivo/Etiknivo.exe (zip the folder to share it)
#   Linux    dist/Etiknivo/Etiknivo
#
# PyInstaller does not cross-compile: build on the system you build for.
# -*- mode: python ; coding: utf-8 -*-
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 - provided by PyInstaller
VERSION = re.search(r'__version__ = "([^"]+)"',
                    (ROOT / "src" / "etiknivo" / "__init__.py").read_text()).group(1)

if sys.platform == "darwin":
    ble = ["bleak.backends.corebluetooth"]
elif sys.platform == "win32":
    ble = ["bleak.backends.winrt", *collect_submodules("winrt")]
else:
    ble = ["bleak.backends.bluezdbus", *collect_submodules("dbus_fast")]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("etiknivo"),
    hiddenimports=collect_submodules(ble[0]) + ble[1:],
    excludes=["tkinter"],
)

# A Python installed by uv records its install folder, inside the home folder,
# in _sysconfigdata*.py.  Ship a copy with the home folder replaced so the app
# does not carry the builder's user name.
HOME = str(Path.home())
pure = []
for name, src, kind in a.pure:
    if name.startswith("_sysconfigdata") and src and src.endswith(".py"):
        text = Path(src).read_text(encoding="utf-8")
        if HOME in text:
            clean = Path(workpath) / f"{name}.py"  # noqa: F821 - provided by PyInstaller
            clean.write_text(text.replace(HOME, "~"), encoding="utf-8")
            src = str(clean)
    pure.append((name, src, kind))
a.pure = pure

pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Etiknivo",
    console=False,
    argv_emulation=False,
    icon=str(ROOT / "packaging" / "etiknivo.ico") if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Etiknivo")  # noqa: F821

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="Etiknivo.app",
        icon=str(ROOT / "packaging" / "etiknivo.icns"),
        bundle_identifier="io.github.etiknivo",
        info_plist={
            "CFBundleName": "Etiknivo",
            "CFBundleDisplayName": "Etiknivo",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            # Required on macOS, otherwise the app is killed when it touches Bluetooth.
            "NSBluetoothAlwaysUsageDescription":
                "Etiknivo gebruikt Bluetooth om etiketten af te drukken op je labelprinter.",
            "NSBluetoothPeripheralUsageDescription":
                "Etiknivo gebruikt Bluetooth om etiketten af te drukken op je labelprinter.",
        },
    )
