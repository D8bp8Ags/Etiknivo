# Een printertype toevoegen

Etiknivo scheidt *wat* er geprint wordt (het profiel) van *hoe* het naar de
printer gaat (de backend). Rendering, voorbeelden, kalibratie, de wachtrij, de
simulatieprinter en de interface lezen alles uit het profiel. Een nieuw model
vraagt daarom alleen deze drie stappen.

## 1. Profiel (`printing/profiles.py`)

```python
MIJN_PRINTER = PrinterProfile(
    key="mijn_printer",              # wordt opgeslagen in settings.json
    display_name="Merk Model",
    printhead_px=96,                 # dots over de printkop
    dpi=203,
    dots_per_mm=8,
    label_width_mm=40.0,             # in de transportrichting
    label_height_mm=12.0,            # over de printkop
    feed_margin_mm=1.5,              # veilige marge aan begin en eind
    feed_offset_px=0,                # vaste correctie als de printer te vroeg/laat begint
    name_prefixes=("MERK_",),        # Bluetooth-namen bij het zoeken
    densities=("Licht", "Normaal", "Donker"),
    default_density=1,
)
```

## 2. Backend (`printing/`)

Spreekt de printer hetzelfde protocol als een bestaand model, gebruik dan die
backend opnieuw: hij krijgt het profiel mee. Anders schrijf je een subklasse
van `PrinterBackend` met `scan`, `connect`, `disconnect`, `get_status`,
`get_battery`, `get_info` en `print_raster`. Zet het eigen statusformaat om naar
`PrinterStatusInfo` (zoals `d11s_protocol.decode_status`). `print_raster` krijgt
een 1-bit raster van `printhead_px` × lengte en de index van de gekozen dichtheid.

## 3. Registreren (`printing/registry.py`)

```python
def _mijn_backend(profile):
    from etiknivo.printing.mijn_backend import MijnBackend
    return MijnBackend(profile=profile)

register(PrinterModel(MIJN_PRINTER, _mijn_backend))
```

Zodra er meer dan één model is, verschijnt in het printerpaneel een keuzelijst.
Na het kiezen start je Etiknivo opnieuw. De simulatieprinter gebruikt
automatisch het profiel van het gekozen model.

`tests/test_printer_models.py` laat met een verzonnen printer van 40 × 15 mm
zien dat de rest van de app zonder aanpassingen meewerkt.
