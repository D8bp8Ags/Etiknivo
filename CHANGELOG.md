# Changelog

All notable changes to Etiknivo are listed here. Version numbers follow [Semantic Versioning](https://semver.org/); before 1.0 a minor version may still change file formats or behaviour.

## [Unreleased]

### Designing labels
- **Restore defaults** in the Style section puts the label's style (line spacing, margins, vertical alignment, rotation, shrink to fit and the other switches) back to the defaults in one step; undo brings it back.
- The pictogram now has a size (Small, Medium, Large) just like the QR code.
- Pictogram and QR code can each go top left, middle left, bottom left, top right, middle right or bottom right. Existing labels keep their look (middle, medium).
- QR code and pictogram can stand below each other: put them on the same side at different heights (for example top left and bottom left) and they share one column, leaving the text more width.
- Same font size within a category: with auto-fit on, labels in the same category now get the same size per line instead of each its own, so a pictogram or QR code on some labels no longer makes the sizes differ. A label with much longer text still shrinks on its own. Switch it off per label under Opmaak (*Zelfde lettergrootte binnen de categorie*) to keep the old behaviour.
- The pictogram now has exactly the same size on every label with the same Size choice; it no longer shrinks when the text is long (the text gets smaller instead). Same font size within a category now also puts the text lines at the same height whatever letters they hold (a word with descenders no longer moves the text up).
- Text is kerned: letter pairs such as "To", "AV" and "We" now stand as close as the font intends. Pillow does not do this on macOS, so Etiknivo reads the pairs from the font itself.
- Auto-fit keeps the main line the largest: when a long main line has to shrink, the category and specification lines shrink along with it instead of ending up larger than the main line.
- Lines within a category now also keep exactly the same spacing on every label. Before, a word that reached a hair lower than the rest at a small size (such as "Transparant" next to "Zwart") could move another line one dot.
- A label with a single line (such as only "LED") now stands in the middle of the label again when another label in its category has letters below the line (g, p, q). The room for those letters now hangs below the text instead of pushing it up; lines still stand at the same height on every label of the category.
- Crisper small text: every line now starts on a whole printer dot, so the same letter prints equally thick on every line and every label (before, a stroke could print one dot wide on one label and two on the next).

### Reliability
- A damaged or hand-edited library no longer stops the app from starting: values of the wrong type or out of range fall back to their defaults, and if the library cannot be read at all the app says why and where the backup is, instead of crashing without a message.
- The same goes for settings: a wrong value falls back to its default instead of crashing at start-up.
- Unexpected errors now end up in the log with all details, and the app shows a short message pointing to Help → Show log.
- A library saved by a newer Etiknivo is recognised: the app warns, and keeps a copy of the original (`library.schema-N.json`) before it saves for the first time. The library format is now version 2.
- Bluetooth: a late "disconnected" message from an earlier connection can no longer drop a new one. Disconnect while printing asks first and waits for the current label. The status poll keeps running after an unexpected error.
- Embedded pictures larger than 4096 pixels per side are refused with a message instead of an error.
- The first font scan no longer blocks the window; labels are redrawn once the fonts are known.

### Printing
- Stop keeps the job in the queue: Resume continues with the next copy, and Retry continues from the copy that did not print, instead of printing every copy again. Cancel only removes waiting jobs; use Stop for the job that is printing. New labels sent while the queue is paused no longer resume it on their own.

### Designing labels
- After Save, the thumbnails of the other labels in the same category are refreshed too (with the same font size per category they can change).
- With the same font size per category, a category of only two labels no longer pulls one label down to the size of a much longer text. A label that keeps its own smaller size now keeps its lines at the same height as the other labels.
- At 180° rotation, the frames that show text not fitting now sit in the right place in the preview.
- Right-to-left text (Hebrew, Arabic) gives a warning: it is drawn left to right.
- Undo now also restores category pictograms, and uses much less memory with a large library.

### Import and export
- CSV: specifications containing `;` or `=` survive an export and import (they are escaped with `\`). A new `lines` column keeps which lines show.
- PNG export asks before overwriting files, treats names that only differ in case as the same, and avoids names Windows reserves (such as `CON`).

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
