"""Generate documentation images (runs headless with the simulated printer).

    QT_QPA_PLATFORM=offscreen uv run python scripts/screenshots.py docs/img
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ETIKNIVO_DATA_DIR", tempfile.mkdtemp(prefix="etiknivo-shots-"))

from PIL import Image  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from etiknivo.gui import main_window as mw  # noqa: E402
from etiknivo.gui.dialogs import PrintPreviewDialog  # noqa: E402
from etiknivo.printing.mock import MockPrinterBackend  # noqa: E402
from etiknivo.rendering.engine import RenderEngine  # noqa: E402
from etiknivo.rendering.overview import overview_pages  # noqa: E402
from etiknivo.settings import Settings, data_dir  # noqa: E402
from etiknivo.storage.library import open_library, seed_labels  # noqa: E402


def label_sheet(out: Path) -> None:
    """All seed labels as the label overview (one long sheet, one pixel per dot)."""
    img = overview_pages(RenderEngine(), seed_labels(), paginate=False)[0]
    img.resize((img.width // 2, img.height // 2), Image.Resampling.BOX).save(out)


def window_shots(app: QApplication, out: Path, theme: str, suffix: str) -> None:
    lib, _ = open_library(data_dir() / "library.json")
    backend = MockPrinterBackend(delay=0.05)
    win = mw.MainWindow(lib, Settings(use_mock_printer=True, theme=theme), backend,
                        poll_interval=3600)
    win.resize(1500, 950)
    win.show()

    def pump(n: int) -> None:
        for _ in range(n):
            app.processEvents()
            time.sleep(0.02)

    pump(10)
    ids = win.library_panel.visible_ids()
    win.library_panel.select_ids([ids[3]])
    pump(5)
    win.grab().save(str(out / f"main-window{suffix}.png"))
    win._connect("")
    pump(40)
    PrintPreviewDialog.exec = lambda self: QDialog.DialogCode.Accepted  # type: ignore[method-assign]
    win.library_panel.select_ids(ids[:4])
    win.print_selected()
    pump(80)
    win.right_tabs.setCurrentWidget(win.printer_panel)
    pump(5)
    win.grab().save(str(out / f"printer-and-queue{suffix}.png"))
    win.show_overview()
    overview = win._overview_window
    overview.resize(960, 680)
    pump(10)
    overview.grab().save(str(out / f"labeloverzicht{suffix}.png"))
    overview.close()
    win.close()


def main(target: str) -> None:
    out = Path(target)
    out.mkdir(parents=True, exist_ok=True)
    label_sheet(out / "raaco-labels.png")
    app = QApplication(sys.argv)
    window_shots(app, out, "light", "")
    window_shots(app, out, "dark", "-dark")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/img")
