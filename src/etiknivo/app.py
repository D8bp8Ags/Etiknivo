"""Etiknivo entry point (``uv run etiknivo``)."""

from __future__ import annotations

import argparse
import logging
import sys

from etiknivo import APP_NAME, __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="etiknivo", description=f"{APP_NAME} – Label Designer "
                                     "& Printer Manager")
    parser.add_argument("--mock", action="store_true",
                        help="Start met de simulatieprinter (geen Bluetooth-hardware nodig) / "
                             "start with the simulated printer")
    parser.add_argument("--debug", action="store_true", help="Uitgebreide logging / verbose logging")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = parser.parse_args(argv)

    from PySide6.QtWidgets import QApplication, QMessageBox

    from etiknivo.logging_setup import setup_logging
    from etiknivo.settings import data_dir, load_settings
    from etiknivo.storage.library import LibraryError, open_library

    setup_logging(logging.DEBUG if args.debug else logging.INFO)
    log = logging.getLogger("etiknivo")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(__version__)
    from etiknivo import i18n
    from etiknivo.gui import theme

    app.setWindowIcon(theme.app_icon())
    settings = load_settings()
    log.info("Taal: %s", i18n.set_language(settings.language))
    i18n.install_qt_translations(app)

    try:
        library, seeded = open_library(data_dir() / "library.json")
    except LibraryError as exc:
        QMessageBox.critical(None, APP_NAME, i18n.tr(
            "{error}\n\nDe vorige versie staat in library.json.bak in {folder}.",
            error=exc, folder=data_dir()))
        return 1
    if seeded:
        log.info("Eerste start: %d voorbeeldlabels aangemaakt", len(library))

    if args.mock:
        settings.use_mock_printer = True

    from etiknivo.gui.main_window import MainWindow

    win = MainWindow(library, settings)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
