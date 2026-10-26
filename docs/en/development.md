# Development

*[Nederlandse versie](../nl/ontwikkelen.md)*

Technical information for anyone who runs Etiknivo from source, changes it or builds it. For using the app, see the [user guide](user-guide.md).

## Installing per system

Etiknivo is developed and tested on macOS (Apple Silicon). Windows 10/11 and Linux use the same code. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) on any system, clone the repository and start with `uv run etiknivo`; uv installs Python 3.12+ and the dependencies from `uv.lock`.

| System | Installing uv | Bluetooth |
|---|---|---|
| macOS | `curl -LsSf https://astral.sh/uv/install.sh \| sh` or `brew install uv` | Access applies to the app you run `uv run` from (Terminal, iTerm, VS Code): **System Settings → Privacy & Security → Bluetooth**. Addresses are UUIDs instead of MAC addresses; that is normal. |
| Windows | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` | Bluetooth on in *Settings → Bluetooth & devices*. Pairing is not needed; Etiknivo finds the printer itself. |
| Linux | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Through BlueZ. Check `bluetoothctl show` (*Powered: yes*); on some distributions your user has to be in the `bluetooth` group. For a menu entry, copy `packaging/etiknivo.desktop` to `~/.local/share/applications/` and `src/etiknivo/gui/appicon/etiknivo.png` to `~/.local/share/icons/`. |

Printing (protocol, raster, queue) is the same code on every system. Only macOS has been tested with a real printer; Windows and Linux have been tested with the automated tests and the simulated printer.

### Options

```bash
uv run etiknivo --mock     # simulated printer, no hardware needed
uv run etiknivo --debug    # verbose logging
uv run etiknivo --version
```

With `ETIKNIVO_DATA_DIR=/path` you use a different data folder, handy for testing.

## Architecture

```
src/etiknivo/
├── app.py                 entry point (uv run etiknivo)
├── model.py               label data model (Label, TextLine, LabelStyle, layouts)
├── settings.py            settings, calibration, data folders
├── logging_setup.py       app.log and print.log
├── privacy.py             masks the home folder and Bluetooth address in logs and the interface
├── storage/               library (JSON), import/export (JSON, CSV, backup)
├── rendering/             render engine, fonts, codes, export (PNG/PDF/SVG), test and calibration patterns
├── printing/
│   ├── profiles.py        printer profiles: geometry, margins, densities
│   ├── registry.py        supported models: which profile goes with which backend
│   ├── backend.py         abstract PrinterBackend and error classes
│   ├── d11s_protocol.py   D11s commands and responses (bytes only, no I/O)
│   ├── ble_link.py        Bluetooth LE link (GATT profile choice, request/response, chunks)
│   ├── d11s_backend.py    printer backend for the Fichero 5836 / AiYin D11s
│   ├── mock.py            simulated printer
│   ├── queue.py           sequential print queue
│   ├── runner.py          asyncio loop in a background thread
│   └── manager.py         connection, status polling and queue (GUI-independent)
├── locale/                translations (en.py)
└── gui/                   PySide6: main window, library, editor, properties, printer, queue
    └── theme.py           colours (light/dark), stylesheet and icons
```

Key principles:

- **One render engine** for preview and print: supersampling (4× by default), box filter, threshold to 1-bit, calibration and rotation to the native raster. If a character is missing from the chosen font, Etiknivo falls back to the bundled DejaVu Sans.
- **Geometry**: the Fichero's print head is 96 dots (12 mm at 203 dpi), so on a 14 mm high label 1 mm at the top and bottom can't be printed. The design is landscape (240 × 112 for 30 mm); the raster that is sent is 96 × 240, rotated 90° counter-clockwise. See the [printer protocol](printer-protocol.md).
- **Bluetooth I/O** runs on its own asyncio thread, so the interface never blocks.
- **QR and barcode encoders** are Etiknivo's own code (`rendering/codes.py`).
- A new printer is a profile, a backend and a registration; see [Adding a printer type](printer-types.md).

## Tests

```bash
uv run pytest
```

The tests run without a printer and without a screen (Qt `offscreen`). They cover rendering (raster size, orientation, calibration, special characters, overflow, all sample labels), JSON/CSV/backup, the print queue including error cases, the D11s protocol byte by byte through a simulated BLE link, reading QR codes and barcodes back with zxing-cpp, and GUI scenarios with the simulated printer.

## Privacy

Etiknivo is open source, so everything in the repository is public, including its history. Nothing in it may be traceable to a person or device: home folders with a user name (`/Users/name`, `C:\Users\name`), email addresses, a printer's Bluetooth address or serial number, tokens or keys, or metadata (EXIF, XMP, PNG text) in images.

**Automatic check.** `tests/test_privacy.py` runs `scripts/privacy_check.py` over every file git tracks, so `uv run pytest` fails as soon as something like that is in there. You can also run it on its own:

```bash
uv run python scripts/privacy_check.py                         # all files
uv run python scripts/privacy_check.py --commits origin/main..  # plus author/committer of your new commits
```

A line that is like this on purpose (a test case, for example) gets `privacy: ok` in a comment.

**Built app.** A build can contain details of the computer it was built on. A Python installed by uv, for example, writes its installation folder (in your home folder, so with your user name) into `_sysconfigdata*.py`, and PyInstaller bundles that module. `packaging/etiknivo.spec` replaces the home folder in it with `~`. Always check a build before you share it:

```bash
uv run python scripts/privacy_check.py --build dist/Etiknivo.app   # or the zip
```

It looks for your own home folder, user name and computer name, including inside the Python modules in the program. Paths to other people's build servers, which appear in bundled libraries, don't count.

**Git hooks.** There are no GitHub Actions; the check runs locally. Switch the hooks on once per clone:

```bash
git config core.hooksPath scripts/hooks
```

- `pre-commit` runs the privacy check on what you are about to commit (less than a second).
- `pre-push` checks the files and whether every new commit uses a GitHub no-reply address (`…@users.noreply.github.com`), so your real email address doesn't end up in the history. On a push to `main` it then runs the whole test suite as well. Skip it once with `git push --no-verify`.

Set your git identity to the no-reply address GitHub shows under *Settings → Emails*:

```bash
git config user.email "<id>+<username>@users.noreply.github.com"
```

**In the app.** What Etiknivo shows or writes is also meant to be shared (screenshots, the log with a bug report), so `src/etiknivo/privacy.py` removes personal data from it:

- `app.log`, `print.log` and the log window show the home folder as `~`, also in error messages and tracebacks (`RedactingFormatter`, `redact()`).
- Bluetooth addresses are only shown shortened in the log, the device list and the print dialog (`…:9B:3C`, `short_address()`). The full address is only stored locally in `settings.json`.
- Paths in the About Etiknivo window start with `~` (`short_path()`).
- Make screenshots for the documentation with `scripts/screenshots.py nl` and `scripts/screenshots.py en` (into `docs/img/nl` and `docs/img/en`): the script uses an empty temporary data folder and the simulated printer, so no printer, path or label of your own shows up.

## Translations

The interface is written in Dutch; the English texts are in `src/etiknivo/locale/en.py`. `uv run python scripts/i18n_strings.py --missing` lists texts without a translation, and a test makes sure none are missing.

Everything the user sees follows the chosen language, including what the app writes (label overview as PDF/PNG, PDF export, default file names, the log). The rules are at the top of `src/etiknivo/i18n.py`:

- Every visible text goes through `tr()` at the moment it is shown or written; mark module-level constants with `N_()` and translate them where they are used.
- Log messages too: `log.info(tr("Verbonden met %s"), naam)`. A test fails on a log line without `tr()`.
- Dates and times through `format_date()` / `format_datetime()`: 26-10-2026 in Dutch, 2026-10-26 in English.
- Data formats are not translated: JSON keys, CSV column names, layout names and names in the backup are the same in both languages, so a file from one language can be read in the other. Text the user typed (labels, categories) is never translated; only the sample library on first start exists in both languages (`data/raaco_seed*.csv`).

The documentation exists in both languages as well: `docs/nl/` and `docs/en/`. When you change one, change the other too.

## Building the app

The same spec file works on macOS, Windows and Linux. PyInstaller only builds for the system it runs on.

```bash
uv sync --group build
uv run pyinstaller packaging/etiknivo.spec --noconfirm
```

| System | Result |
|---|---|
| macOS | `dist/Etiknivo.app`, with the app icon and the required `NSBluetoothAlwaysUsageDescription` |
| Windows | `dist/Etiknivo/Etiknivo.exe`; zip the `dist/Etiknivo` folder to share it |
| Linux | `dist/Etiknivo/Etiknivo` |

The app is not signed. On macOS 14 and earlier, start it the first time with right-click → **Open**. From macOS 15 that no longer works: open the app once, close the warning and then click **Open Anyway** in **System Settings → Privacy & Security**. Windows SmartScreen asks once for **More info → Run anyway**.

PyInstaller builds for the processor of the Mac you build on: on Apple Silicon the app is for Apple Silicon only.

## Making a release

1. Set the same version number in `src/etiknivo/__init__.py` and `pyproject.toml` (for example `0.2.0`) and run `uv lock`.
2. Add a new section with the date to `CHANGELOG.md`.
3. Run `uv run pytest` and `uvx ruff check .`, commit and push to `main`.
4. Build the app on a Mac from that commit:

   ```bash
   git pull
   rm -rf build dist
   uv sync --group build
   uv run pyinstaller packaging/etiknivo.spec --noconfirm
   ditto -c -k --norsrc --noextattr --noqtn --keepParent dist/Etiknivo.app dist/Etiknivo-0.2.0-macOS.zip
   uv run python scripts/privacy_check.py --build dist/Etiknivo-0.2.0-macOS.zip
   ```

   Use `ditto`, not `zip`: it keeps the symbolic links and the ad-hoc signature in the bundle. The extra options leave out the macOS attributes of your own disk (such as `com.apple.provenance`). The privacy check looks inside the zip, including the Python modules PyInstaller packs into the program, for your home folder, user name or computer name. Start the app from `dist` once and print a test label before you share it.
5. Create a release on GitHub: **Releases → Draft a new release**, type `v0.2.0` under *Choose a tag* (the tag is then created on `main` when you publish), paste the section from `CHANGELOG.md` as the text and drag the zip file in.

The update check in the app reads the latest release through the GitHub API and compares the tag number with `__version__`; so keep the tag in the form `vX.Y.Z`.
