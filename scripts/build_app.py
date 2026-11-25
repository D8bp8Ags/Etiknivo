"""Build the app with PyInstaller (packaging/etiknivo.spec) and pack it into one file to download.

GitHub runs this on every push to main (.github/workflows/build.yml), on a Mac with
Apple Silicon, an Intel Mac and Windows.  The apps are made there, not on your own
computer, so they never carry details of it.

    uv run --group build python scripts/build_app.py

Result in dist/, for example:
    Etiknivo-0.2.0-macOS-AppleSilicon.zip   (Etiknivo.app)
    Etiknivo-0.2.0-macOS-Intel.zip
    Etiknivo-0.2.0-Windows.zip              (the Etiknivo folder with Etiknivo.exe)

The zip is then checked with scripts/privacy_check.py --build: the build stops when
the home folder, user name or host name of the build machine is in it.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
VERSION = re.search(r'__version__ = "([^"]+)"',
                    (ROOT / "src" / "etiknivo" / "__init__.py").read_text(encoding="utf-8")).group(1)


def download_name() -> str:
    """Name of the file people download, e.g. Etiknivo-0.2.0-macOS-AppleSilicon.zip."""
    if sys.platform == "darwin":
        kind = "macOS-AppleSilicon" if platform.machine() == "arm64" else "macOS-Intel"
    elif sys.platform == "win32":
        kind = "Windows"
    else:
        kind = "Linux"
    return f"Etiknivo-{VERSION}-{kind}.zip"


def main() -> int:
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(DIST, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / "etiknivo.spec"),
                    "--noconfirm", "--clean"], cwd=ROOT, check=True)
    out = DIST / download_name()
    if sys.platform == "darwin":
        # ditto keeps the symbolic links and the ad-hoc signature of the bundle; the options
        # leave out resource forks and extended attributes of the build machine's disk.
        subprocess.run(["ditto", "-c", "-k", "--norsrc", "--noextattr", "--noqtn", "--keepParent",
                        str(DIST / "Etiknivo.app"), str(out)], check=True)
    else:
        shutil.make_archive(str(out.with_suffix("")), "zip", DIST, "Etiknivo")
    print(f"download: {out.relative_to(ROOT)}", flush=True)

    sys.path.insert(0, str(ROOT / "scripts"))
    import privacy_check

    return privacy_check.main(["--build", str(out)])


if __name__ == "__main__":
    sys.exit(main())
