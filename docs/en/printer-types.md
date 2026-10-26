# Adding a printer type

*[Nederlandse versie](../nl/printertypes.md)*

Etiknivo separates *what* is printed (the profile) from *how* it gets to the
printer (the backend). Rendering, previews, calibration, the queue, the
simulated printer and the interface read everything from the profile. A new
model therefore only takes these three steps.

## 1. Profile (`printing/profiles.py`)

```python
MY_PRINTER = PrinterProfile(
    key="my_printer",                # stored in settings.json
    display_name="Brand Model",
    printhead_px=96,                 # dots across the print head
    dpi=203,
    dots_per_mm=8,
    label_width_mm=40.0,             # in the feed direction
    label_height_mm=12.0,            # across the print head
    feed_margin_mm=1.5,              # safe margin at the start and end
    feed_offset_px=0,                # fixed correction if the printer starts too early/late
    name_prefixes=("BRAND_",),       # Bluetooth names when searching
    densities=("Licht", "Normaal", "Donker"),  # Dutch source texts, translated in the interface
    default_density=1,
)
```

## 2. Backend (`printing/`)

If the printer speaks the same protocol as an existing model, reuse that
backend: it receives the profile. Otherwise write a subclass of
`PrinterBackend` with `scan`, `connect`, `disconnect`, `get_status`,
`get_battery`, `get_info` and `print_raster`. Convert the printer's own status
format to `PrinterStatusInfo` (like `d11s_protocol.decode_status`).
`print_raster` receives a 1-bit raster of `printhead_px` × length and the index
of the chosen density.

## 3. Registering (`printing/registry.py`)

```python
def _my_backend(profile):
    from etiknivo.printing.my_backend import MyBackend
    return MyBackend(profile=profile)

register(PrinterModel(MY_PRINTER, _my_backend))
```

As soon as there is more than one model, a drop-down list appears in the
printer panel. After choosing, restart Etiknivo. The simulated printer
automatically uses the profile of the chosen model.

`tests/test_printer_models.py` uses a made-up 40 × 15 mm printer to show that
the rest of the app works along without changes.
