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

from PIL import Image, ImageDraw  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from etiknivo.gui import main_window as mw  # noqa: E402
from etiknivo.gui.dialogs import PrintPreviewDialog  # noqa: E402
from etiknivo.printing.mock import MockPrinterBackend  # noqa: E402
from etiknivo.rendering.engine import RenderEngine  # noqa: E402
from etiknivo.rendering.fonts import FontRegistry, pil_font  # noqa: E402
from etiknivo.settings import Settings, data_dir  # noqa: E402
from etiknivo.storage.library import open_library, seed_labels  # noqa: E402


def label_sheet(out: Path) -> None:
    """All seed labels as 1-bit printer output (design orientation, 3× enlarged)."""
    eng = RenderEngine()
    labels = seed_labels()
    cols, scale, pad = 4, 3, 14
    w, h = eng.design_size
    cell_w, cell_h = w * scale + pad, h * scale + pad + 18
    rows = (len(labels) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w + pad, rows * cell_h + pad), (225, 225, 225))
    d = ImageDraw.Draw(sheet)
    font = pil_font(FontRegistry.fallback().path, 0, 13)
    for i, lbl in enumerate(labels):
        x, y = pad + (i % cols) * cell_w, pad + (i // cols) * cell_h
        img = eng.render(lbl).mono.convert("RGB").resize((w * scale, h * scale), Image.NEAREST)
        sheet.paste(img, (x, y + 18))
        d.text((x, y), f"{lbl.tray_id}", font=font, fill=(60, 60, 60))
    sheet.save(out)


def main(target: str) -> None:
    out = Path(target)
    out.mkdir(parents=True, exist_ok=True)
    label_sheet(out / "raaco-labels.png")
    app = QApplication(sys.argv)
    lib, _ = open_library(data_dir() / "library.json")
    backend = MockPrinterBackend(delay=0.05)
    win = mw.MainWindow(lib, Settings(use_mock_printer=True), backend, poll_interval=3600)
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
    win.grab().save(str(out / "main-window.png"))
    win._connect("")
    pump(40)
    PrintPreviewDialog.exec = lambda self: QDialog.DialogCode.Accepted  # type: ignore[method-assign]
    win.library_panel.select_ids(ids[:4])
    win.print_selected()
    pump(80)
    win.right_tabs.setCurrentWidget(win.printer_panel)
    pump(5)
    win.grab().save(str(out / "printer-and-queue.png"))
    win.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/img")
