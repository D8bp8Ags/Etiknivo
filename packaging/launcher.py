"""Start of the built app (packaging/etiknivo.spec).

``--self-test`` is what the GitHub build runs on the packed app: it opens the
main window with the simulated printer in an empty data folder, renders every
sample label and loads the Bluetooth backend of this system.  Exit code 0 when
the app has everything it needs, 1 when something is missing.
"""

import sys


def self_test() -> int:
    import importlib
    import os
    import tempfile

    os.environ["ETIKNIVO_DATA_DIR"] = tempfile.mkdtemp(prefix="etiknivo-selftest-")
    from PySide6.QtWidgets import QApplication

    from etiknivo.gui.main_window import MainWindow
    from etiknivo.printing.mock import MockPrinterBackend
    from etiknivo.rendering.engine import RenderEngine
    from etiknivo.settings import Settings, data_dir
    from etiknivo.storage.library import open_library, seed_labels

    backend = {"darwin": "bleak.backends.corebluetooth.scanner",
               "win32": "bleak.backends.winrt.scanner"}.get(sys.platform, "bleak.backends.bluezdbus.scanner")
    importlib.import_module(backend)
    engine = RenderEngine()
    labels = seed_labels()
    for label in labels:
        engine.render(label)
    app = QApplication(sys.argv[:1])
    library, _ = open_library(data_dir() / "library.json")
    win = MainWindow(library, Settings(use_mock_printer=True), MockPrinterBackend(delay=0.01),
                     poll_interval=3600)
    win.show()
    for _ in range(20):
        app.processEvents()
    ok = len(library) > 0 and not win.grab().isNull()
    print(f"self-test: {len(labels)} labels rendered, {backend} loaded, window "
          f"{'ok' if ok else 'FAILED'}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    from etiknivo.app import main

    sys.exit(main())
