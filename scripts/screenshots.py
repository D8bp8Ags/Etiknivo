"""Generate documentation images (runs headless with the simulated printer).

    QT_QPA_PLATFORM=offscreen uv run python scripts/screenshots.py nl
    QT_QPA_PLATFORM=offscreen uv run python scripts/screenshots.py en
    QT_QPA_PLATFORM=offscreen uv run python scripts/screenshots.py nl templates  # only those

Writes to docs/img/<language>/; the Dutch manual uses docs/img/nl, the English
manual and the README use docs/img/en.
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

from etiknivo import i18n  # noqa: E402
from etiknivo.gui import main_window as mw  # noqa: E402
from etiknivo.gui.dialogs import CalibrationDialog, PrintPreviewDialog  # noqa: E402
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
    if theme == "light":
        lib_labels = [lib.get(i) for i in ids[:3]]
        preview = PrintPreviewDialog(win.engine, lib_labels, 1, 1,
                                     win.bridge.state.backend_name, True, win)
        preview.show()
        pump(10)
        preview.grab().save(str(out / "print-preview.png"))
        preview.close()
        cal = CalibrationDialog(win.engine.calibration, win, win.profile.dots_per_mm)
        cal.show()
        pump(10)
        cal.grab().save(str(out / "calibration.png"))
        cal.close()
    win.show_overview()
    overview = win._overview_window
    overview.resize(960, 680)
    pump(10)
    overview.grab().save(str(out / f"label-overview{suffix}.png"))
    overview.close()
    win.close()


def template_shots(app: QApplication, out: Path, names: tuple[str, str, str]) -> None:
    """The template chooser opened beside the inspector, and one label of each
    template as it prints."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPainter

    from etiknivo.model import LabelTemplate, PictureKind, make_label
    from etiknivo.rendering.templates import apply_template

    lib, _ = open_library(data_dir() / "library.json")
    win = mw.MainWindow(lib, Settings(use_mock_printer=True, theme="light"),
                        MockPrinterBackend(delay=0.05), poll_interval=3600)
    win.resize(1500, 950)
    win.show()

    def pump(n: int) -> None:
        for _ in range(n):
            app.processEvents()
            time.sleep(0.02)

    pump(10)
    win.library_panel.select_ids([win.library_panel.visible_ids()[3]])
    pump(5)
    props = win.properties
    box = props.template
    box.setCurrentIndex(box.findData(LabelTemplate.HEADER.value))
    box.activated.emit(box.currentIndex())
    pump(10)
    box.showPopup()
    pump(10)
    shot = win.grab()
    popup = box.view().window()
    pos = popup.mapToGlobal(QPoint(0, 0)) - win.mapToGlobal(QPoint(0, 0))
    painter = QPainter(shot)
    painter.drawPixmap(pos, popup.grab())
    painter.end()
    box.hidePopup()
    shot.save(str(out / names[0]))
    editor_shot(app, win, out / names[2])
    win._ask_unsaved = lambda _lbl: "discard"  # type: ignore[method-assign]
    win.close()

    engine = RenderEngine()
    long_engine = RenderEngine(engine.profile.with_label(50.0, 14.0))
    lbl = make_label("A17", i18n.tr("Halfgeleiders"), i18n.tr("Rood"), "")
    lbl.top.text, lbl.top.enabled = "LED", True
    lbl.picture.kind, lbl.picture.symbol = PictureKind.SYMBOL, "led"
    tiles = []
    for tpl in LabelTemplate:
        if tpl == LabelTemplate.CUSTOM:  # the user's own: none in the sheet
            continue
        apply_template(lbl, tpl)
        # only the grid splits the bottom line into cells at |
        lbl.bottom.text = "Ø 3 mm | THT | 20 mA | 2,0 V" if tpl == LabelTemplate.GRID \
            else "Ø 3 mm THT"
        eng = long_engine if tpl == LabelTemplate.ZONES else engine
        img = eng.render(lbl).mono.crop(eng.printable_box).convert("L")
        tiles.append(img.resize((img.width * 3, img.height * 3), Image.Resampling.NEAREST))
    gap, cols = 24, 3
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("L", (cols * (tiles[0].width + gap) + gap,
                            rows * (tiles[0].height + gap) + gap), 235)
    for n, tile in enumerate(tiles[:-1]):
        x = gap + (n % cols) * (tiles[0].width + gap)
        y = gap + (n // cols) * (tiles[0].height + gap)
        sheet.paste(tile, (x, y))
    last = tiles[-1]
    y = gap + (len(tiles) - 1) // cols * (tiles[0].height + gap)
    x = gap + ((len(tiles) - 1) % cols) * (tiles[0].width + gap)
    if x + last.width > sheet.width - gap:  # the long label gets its own row
        sheet2 = Image.new("L", (max(sheet.width, last.width + 2 * gap),
                                 sheet.height + last.height + gap), 235)
        sheet2.paste(sheet, (0, 0))
        sheet, x, y = sheet2, gap, sheet.height
    sheet.paste(last, (x, y))
    sheet.save(out / names[1])


def editor_shot(app: QApplication, win: mw.MainWindow, path: Path) -> None:
    """The window for own templates, with a copy of Header bar being changed."""
    from etiknivo.gui.template_editor import TemplateEditor
    from etiknivo.model import LabelTemplate

    dlg = TemplateEditor(win.library, win.engine, ["DejaVu Sans"], win)
    dlg.resize(1250, 640)
    dlg.show()
    dlg.new_from(LabelTemplate.ICON)
    dlg.save()
    dlg.new_from(LabelTemplate.HEADER)
    dlg.save()
    dlg.add_part(6)  # the label's pictogram
    el = dlg.work.elements[-1]
    el.move_to(0.0, 3.25)
    el.resize(6.0, 8.5)
    for other in dlg.work.elements[:-1]:
        if other.y_mm > 2.5 and other.kind.value == "text":
            other.move_to(other.x_mm + 6.5, other.y_mm)
            other.resize(max(4.0, other.w_mm - 6.5), other.h_mm)
    dlg.elements.set_label(dlg.sample)
    dlg.elements.select(el.id)
    dlg.view.select(el.id)
    dlg._changed()
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)
    dlg.grab().save(str(path))
    dlg.ask_unsaved = lambda _name: "discard"
    dlg.close()
    win.library.set_templates([])  # the shots after this show the ready-made ones


def main(lang: str = "nl", only: str = "") -> None:
    i18n.set_language(lang)
    out = Path(__file__).resolve().parent.parent / "docs" / "img" / lang
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    i18n.install_qt_translations(app)
    if only != "templates":
        label_sheet(out / "raaco-labels.png")
        window_shots(app, out, "light", "")
        window_shots(app, out, "dark", "-dark")
    template_shots(app, out,
                   ("sjablonen.png", "sjabloon-resultaat.png", "sjablooneditor.png")
                   if lang == "nl" else
                   ("templates.png", "template-result.png", "template-editor.png"))


if __name__ == "__main__":
    main(*sys.argv[1:3])
