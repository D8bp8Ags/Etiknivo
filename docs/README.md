# Etiknivo documentation

The documentation is available in English and Dutch. Both versions have the same content.

| | English | Nederlands |
|---|---|---|
| User guide | [user-guide.md](en/user-guide.md) | [handleiding.md](nl/handleiding.md) |
| Development | [development.md](en/development.md) | [ontwikkelen.md](nl/ontwikkelen.md) |
| Printer protocol | [printer-protocol.md](en/printer-protocol.md) | [printer-protocol.md](nl/printer-protocol.md) |
| Adding a printer type | [printer-types.md](en/printer-types.md) | [printertypes.md](nl/printertypes.md) |

Screenshots are in `img/en/` and `img/nl/`. They are generated with the simulated printer and an empty data folder:

```bash
QT_QPA_PLATFORM=offscreen uv run python scripts/screenshots.py en
QT_QPA_PLATFORM=offscreen uv run python scripts/screenshots.py nl
```

Back to the [README](../README.md).
