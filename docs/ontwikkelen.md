# Ontwikkelen

Technische informatie voor wie Etiknivo vanuit de broncode draait, aanpast of bouwt. Voor het gebruik van de app, zie de [handleiding](handleiding.md).

## Installeren per systeem

Etiknivo is ontwikkeld en getest op macOS (Apple Silicon). Windows 10/11 en Linux gebruiken dezelfde code. Installeer overal [uv](https://docs.astral.sh/uv/getting-started/installation/), clone de repository en start met `uv run etiknivo`; uv installeert Python 3.12+ en de afhankelijkheden uit `uv.lock`.

| Systeem | uv installeren | Bluetooth |
|---|---|---|
| macOS | `curl -LsSf https://astral.sh/uv/install.sh \| sh` of `brew install uv` | Toegang geldt voor de app waarin je `uv run` start (Terminal, iTerm, VS Code): **Systeeminstellingen → Privacy en beveiliging → Bluetooth**. Adressen zijn UUID's in plaats van MAC-adressen; dat is normaal. |
| Windows | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` | Bluetooth aan in *Instellingen → Bluetooth en apparaten*. Koppelen is niet nodig; Etiknivo zoekt de printer zelf. |
| Linux | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Via BlueZ. Controleer `bluetoothctl show` (*Powered: yes*); op sommige distributies moet je gebruiker in de groep `bluetooth`. Voor een menu-item kopieer je `packaging/etiknivo.desktop` naar `~/.local/share/applications/` en `src/etiknivo/gui/appicon/etiknivo.png` naar `~/.local/share/icons/`. |

Het afdrukken (protocol, raster, wachtrij) is op alle systemen dezelfde code. Met een echte printer is alleen macOS getest; Windows en Linux zijn getest met de automatische tests en de simulatieprinter.

### Opties

```bash
uv run etiknivo --mock     # simulatieprinter, geen hardware nodig
uv run etiknivo --debug    # uitgebreide logging
uv run etiknivo --version
```

Met `ETIKNIVO_DATA_DIR=/pad` gebruik je een andere datamap, handig voor testen.

## Architectuur

```
src/etiknivo/
├── app.py                 start (uv run etiknivo)
├── model.py               labeldatamodel (Label, TextLine, LabelStyle, layouts)
├── settings.py            instellingen, kalibratie, datamappen
├── logging_setup.py       app.log en print.log
├── storage/               bibliotheek (JSON), import/export (JSON, CSV, back-up)
├── rendering/             renderengine, lettertypen, codes, export (PNG/PDF/SVG), test- en kalibratiepatronen
├── printing/
│   ├── profiles.py        printerprofielen: geometrie, marges, dichtheden
│   ├── registry.py        ondersteunde modellen: welk profiel bij welke backend hoort
│   ├── backend.py         abstracte PrinterBackend en foutklassen
│   ├── d11s_protocol.py   opdrachten en antwoorden van de D11s (alleen bytes, geen I/O)
│   ├── ble_link.py        Bluetooth LE-verbinding (GATT-profiel kiezen, verzoek/antwoord, blokken)
│   ├── d11s_backend.py    printerbackend voor de Fichero 5836 / AiYin D11s
│   ├── mock.py            simulatieprinter
│   ├── queue.py           sequentiële printwachtrij
│   ├── runner.py          asyncio-loop in een achtergrondthread
│   └── manager.py         verbinding, status-polling en wachtrij (GUI-onafhankelijk)
├── locale/                vertalingen (en.py)
└── gui/                   PySide6: hoofdvenster, bibliotheek, editor, eigenschappen, printer, wachtrij
    └── theme.py           kleuren (licht/donker), stylesheet en pictogrammen
```

Belangrijke uitgangspunten:

- **Eén renderengine** voor voorbeeld en afdruk: supersampling (standaard 4×), box-filter, drempel naar 1-bit, kalibratie en rotatie naar het native raster. Ontbreekt een teken in het gekozen lettertype, dan valt Etiknivo terug op de meegeleverde DejaVu Sans.
- **Geometrie**: de printkop van de Fichero is 96 dots (12 mm bij 203 dpi), dus van een etiket van 14 mm hoog is 1 mm boven en onder niet bedrukbaar. Het ontwerp is liggend (240 × 112 bij 30 mm); het verstuurde raster is 96 × 240, 90° tegen de klok in gedraaid. Zie het [printerprotocol](printer-protocol.md).
- **Bluetooth-I/O** draait op een eigen asyncio-thread, zodat de interface nooit blokkeert.
- **QR- en barcode-encoders** zijn eigen code (`rendering/codes.py`).
- Een nieuwe printer is een profiel, een backend en een registratie; zie [Een printertype toevoegen](printertypes.md).

## Tests

```bash
uv run pytest
```

De tests draaien zonder printer en zonder scherm (Qt `offscreen`). Ze dekken de rendering (rasterafmetingen, oriëntatie, kalibratie, speciale tekens, overflow, alle voorbeeldlabels), JSON/CSV/back-up, de printwachtrij inclusief foutsituaties, het D11s-protocol byte voor byte via een nagebootste BLE-verbinding, het teruglezen van QR- en barcodes met zxing-cpp en GUI-scenario's met de simulatieprinter.

## Vertalingen

De interface is in het Nederlands geschreven; de Engelse teksten staan in `src/etiknivo/locale/en.py`. Met `uv run python scripts/i18n_strings.py --missing` zie je teksten zonder vertaling, en een test bewaakt dat er geen ontbreken.

Alles wat de gebruiker ziet volgt de gekozen taal, ook wat de app wegschrijft (labeloverzicht als PDF/PNG, PDF-export, standaard bestandsnamen, het log). De regels staan bovenaan `src/etiknivo/i18n.py`:

- Elke zichtbare tekst gaat door `tr()` op het moment dat hij getoond of geschreven wordt; constanten op moduleniveau markeer je met `N_()` en vertaal je waar ze gebruikt worden.
- Logberichten ook: `log.info(tr("Verbonden met %s"), naam)`. Een test faalt bij een logregel zonder `tr()`.
- Datums en tijden via `format_date()` / `format_datetime()`: 26-10-2026 in het Nederlands, 2026-10-26 in het Engels.
- Dataformaten vertaal je niet: JSON-sleutels, CSV-kolomnamen, layoutnamen en namen in de back-up zijn in beide talen gelijk, zodat een bestand uit de ene taal in de andere te lezen is. Teksten die de gebruiker zelf typte (labels, categorieën) worden nooit vertaald; alleen de voorbeeldbibliotheek bij de eerste start bestaat in beide talen (`data/raaco_seed*.csv`).

## De app bouwen

Hetzelfde spec-bestand werkt op macOS, Windows en Linux. PyInstaller bouwt alleen voor het systeem waarop het draait.

```bash
uv sync --group build
uv run pyinstaller packaging/etiknivo.spec --noconfirm
```

| Systeem | Resultaat |
|---|---|
| macOS | `dist/Etiknivo.app`, met app-icoon en de vereiste `NSBluetoothAlwaysUsageDescription` |
| Windows | `dist/Etiknivo/Etiknivo.exe`; zip de map `dist/Etiknivo` om hem te delen |
| Linux | `dist/Etiknivo/Etiknivo` |

De app is niet ondertekend. Op macOS start je hem de eerste keer met rechtermuisklik → **Open**; Windows SmartScreen vraagt eenmalig om **Meer info → Toch uitvoeren**.
