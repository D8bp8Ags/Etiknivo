# AiYin D11s printer protocol (Action Fichero 5836)

*[Nederlandse versie](../nl/printer-protocol.md)*

Working notes for `src/etiknivo/printing/d11s_protocol.py` and `ble_link.py`. All values are hexadecimal.

## Hardware

| Property | Value |
|---|---|
| Print head | 96 dots = 12 bytes per raster line |
| Resolution | 203 dpi (8 dots/mm) |
| Label | 30 × 14 mm; 30 mm = 240 raster lines, across only the middle 12 mm is printable |
| Bluetooth name | `FICHERO_xxxx` or `D11s_xxxx` |

## Bluetooth LE

The printer offers several equivalent UART-like GATT services. After connecting, Etiknivo picks the first one that is present:

| Service | Write | Notify |
|---|---|---|
| `18F0` | `2AF1` | `2AF0` |
| `FF00` | `FF02` | `FF01` |
| `49535343-fe7d-…-9fafd205e455` (Microchip transparent UART) | `…9bb3` | `…9616` |

Commands are sent as *write without response*. Responses arrive as notifications and can be split over several packets; `BleLink` therefore waits briefly until the line goes quiet. Large rasters are split into chunks of the maximum write size the operating system reports (180 bytes by default), with a short pause in between.

## Queries

| Command | Meaning | Response |
|---|---|---|
| `10 FF 20 F0` | model | ASCII, e.g. `D11s` |
| `10 FF 20 F1` | firmware | ASCII |
| `10 FF 20 F2` | serial number | ASCII |
| `10 FF 50 F1` | battery | 2 bytes: state, percentage |
| `10 FF 40` | status | 1 byte bitmask (see below) |

Status bits: `01` printing · `02` cover open · `04` out of paper · `08` battery low · `10`/`40` overheated · `20` charging. `00` means ready.

## Settings

| Command | Meaning | Response |
|---|---|---|
| `10 FF 10 00 nn` | density: 0 light, 1 normal, 2 dark | `OK` |
| `10 FF 84 nn` | paper: 0 labels with gap, 1 black mark, 2 continuous | `OK` |

## Printing

Per label:

1. `10 FF 40`: status; stop on cover open, no paper or overheating.
2. `10 FF 84 00`: paper mode labels (the gap sensor determines the label position).
3. 12 × `00`: wake.
4. `10 FF FE 01`: start of job.
5. `1D 76 30 00 0C 00 yL yH` + bitmap: ESC/POS *GS v 0* (see the Epson ESC/POS reference). 12 bytes per line, `yL yH` = number of lines (240 = `F0 00`), MSB = leftmost dot, bit 1 = black.
6. `1D 0C`: form feed, the printer advances to the next gap.
7. `10 FF FE 45`: end of job; the printer answers `AA` or `OK` when the label is done.

The density is set once per job, before the first label.

The start and end commands differ per printer family. Other printers on the same platform use `10 FF F1 03` and `10 FF F1 45`. A D11s accepts those without an error but then prints nothing, so Etiknivo never sends them.

## Position on the label

There is no command for a margin or offset: the printer finds the start of the label with the gap sensor and prints the raster from there. On a Fichero 5836 the print starts about 1 mm too early, and the position varies by about a millimetre. Etiknivo therefore leaves 2 mm empty at both ends (safe area 26 × 12 mm) and shifts the image a fixed 8 dots (1 mm) along the roll (`feed_offset_px` in the printer profile). The user's calibration is added on top of that.

## Tested on hardware

The command sequence, orientation and centring have been confirmed on a real Fichero 5836. The pauses in `d11s_backend.Timing` are generous and could possibly be shorter.
