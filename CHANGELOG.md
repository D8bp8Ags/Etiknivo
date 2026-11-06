# Changelog

All notable changes to Etiknivo are listed here. Version numbers follow [Semantic Versioning](https://semver.org/); before 1.0 a minor version may still change file formats or behaviour.

## [Unreleased]

### Designing labels
- The pictogram now has a size (Small, Medium, Large) just like the QR code.
- Pictogram and QR code can each go top left, middle left, bottom left, top right, middle right or bottom right. Existing labels keep their look (middle, medium).
- QR code and pictogram can stand below each other: put them on the same side at different heights (for example top left and bottom left) and they share one column, leaving the text more width.
- Same font size within a category: with auto-fit on, labels in the same category now get the same size per line instead of each its own, so a pictogram or QR code on some labels no longer makes the sizes differ. A label with much longer text still shrinks on its own. Switch it off per label under Opmaak (*Zelfde lettergrootte binnen de categorie*) to keep the old behaviour.

### Look
- New themes under View → Theme: Paper (warm cream), Night (pure black) and High contrast, next to System, Light and Dark.
- View → Accent colour: Blue, Green, Orange or Purple for buttons, selections and check boxes, on any theme.

## [0.1.0] - 2026-10-26

First public release.

### Printing
- Prints directly over Bluetooth to the Action Fichero 5836 (AiYin D11s), with Etiknivo's own implementation of the printer protocol. Tested on macOS with a real printer.
- What you see is what prints: the preview is the exact bitmap that goes to the printer.
- Print queue with a print history; print one label, a selection or a whole category.
- Calibration for offset, direction, density and black threshold, with a test label and a calibration test.
- 30 × 14 mm labels by default, plus other 12 and 14 mm rolls.
- A built-in simulated printer, so the app also works without hardware (`--mock`).

### Designing labels
- Several lines of text with automatic fitting, turned text and separators.
- 70 original pictograms, category symbols, or your own image.
- QR codes (three sizes) and Code 128 barcodes, with Etiknivo's own encoders.
- Free layout: drag text, codes, lines and frames anywhere on the label.
- Linked fields such as `{Voltage}`, `{Date}` and `{No}`, filled in per label or at print time.
- Per-label drafts with save, restore and undo.

### Library
- Label library with categories, search, sorting and multi-select; 23 sample labels for electronic components.
- Edit many labels at once in a table (Edit labels…, ⌘E).
- Label overview of all labels, also saved as PDF or PNG.
- Import and export: CSV, JSON, PNG, true-size PDF and full backups.
- Notes per label with clickable links.

### App
- Light and dark theme, English and Dutch.
- In-app log window and an About dialog with copyable system information.
- Optional check for new versions on GitHub; Etiknivo never downloads or installs anything itself.
- No personal data in logs: the home folder is shown as `~` and Bluetooth addresses are shortened.

### Known limitations
- The macOS app is not signed or notarised; see the README for how to open it the first time.
- Only the Fichero 5836 is supported. Windows and Linux use the same code but have only been tested with the simulated printer.

[0.1.0]: https://github.com/D8bp8Ags/Etiknivo/releases/tag/v0.1.0
