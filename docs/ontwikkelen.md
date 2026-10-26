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
├── privacy.py             thuismap en Bluetooth-adres afschermen in log en interface
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

## Privacy

Etiknivo is open source, dus alles in de repository is openbaar, ook de geschiedenis. Er mag niets in staan dat naar een persoon of apparaat te herleiden is: thuismappen met een gebruikersnaam (`/Users/naam`, `C:\Users\naam`), e-mailadressen, het Bluetooth-adres of serienummer van een printer, tokens of sleutels, of metadata (EXIF, XMP, PNG-tekst) in afbeeldingen.

**Automatische controle.** `tests/test_privacy.py` draait `scripts/privacy_check.py` over alle bestanden die git volgt, dus `uv run pytest` faalt zodra er zoiets in staat. Los draaien kan ook:

```bash
uv run python scripts/privacy_check.py                         # alle bestanden
uv run python scripts/privacy_check.py --commits origin/main..  # plus auteur/committer van je nieuwe commits
```

Een regel die bewust zo is (bijvoorbeeld een testgeval), krijgt `privacy: ok` in een commentaar.

**Git-hooks.** Er is geen GitHub Actions; de controle draait lokaal. Zet de hooks één keer aan per clone:

```bash
git config core.hooksPath scripts/hooks
```

- `pre-commit` draait de privacycontrole op wat je gaat committen (minder dan een seconde).
- `pre-push` controleert de bestanden en of elke nieuwe commit een GitHub no-reply-adres gebruikt (`…@users.noreply.github.com`), zodat je echte e-mailadres niet in de geschiedenis belandt. Bij een push naar `main` draait daarna ook de hele testsuite. Eenmalig overslaan kan met `git push --no-verify`.

Stel je git-identiteit in op het no-reply-adres dat GitHub onder *Settings → Emails* toont:

```bash
git config user.email "<id>+<gebruikersnaam>@users.noreply.github.com"
```

**In de app.** Wat Etiknivo laat zien of wegschrijft is ook bedoeld om te delen (schermafbeeldingen, het log bij een foutmelding), dus `src/etiknivo/privacy.py` haalt daar persoonlijke gegevens uit:

- `app.log`, `print.log` en het logvenster tonen de thuismap als `~`, ook in foutmeldingen en tracebacks (`RedactingFormatter`, `redact()`).
- Bluetooth-adressen staan in het log, de apparatenlijst en het afdrukvenster alleen verkort (`…:9B:3C`, `short_address()`). Het volledige adres staat alleen lokaal in `settings.json`.
- Paden in het venster Over Etiknivo beginnen met `~` (`short_path()`).
- Schermafbeeldingen voor de documentatie maak je met `scripts/screenshots.py`: die gebruikt een lege tijdelijke datamap en de simulatieprinter, dus er komt geen eigen printer, pad of label in beeld.

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
