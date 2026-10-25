<img src="src/etiknivo/gui/appicon/etiknivo.png" width="96" alt="Etiknivo-icoon">

# Etiknivo

**Etiketten ontwerpen, beheren en afdrukken vanaf je computer.**

Etiknivo is een open-source desktopapp voor kleine labelprinters. Je houdt een bibliotheek van etiketten bij, bijvoorbeeld voor een ladekast of werkplaats, ontwerpt ze met tekst, symbolen en codes, en drukt ze rechtstreeks via Bluetooth af. Alles staat lokaal, zonder account of cloud.

![Etiknivo hoofdvenster](docs/img/main-window.png)

## Functies

- **Labelbibliotheek** met categorieën, zoeken, sorteren en meervoudige selectie.
- **Ontwerpen wat je print**: het voorbeeld is exact de bitmap die naar de printer gaat.
- **Tekst, symbolen en codes**: meerdere tekstregels, 65 eigen pictogrammen of een eigen afbeelding, QR-codes en Code 128-barcodes.
- **Vrije layout**: sleep tekst, codes, lijnen en kaders precies op hun plek.
- **Gekoppelde velden** zoals `{Spanning}`, `{Datum}` en `{Nr}`, die per label of bij het afdrukken worden ingevuld.
- **Afdrukken in bulk**: een label, een selectie of een hele categorie, via een wachtrij met geschiedenis.
- **Import en export**: CSV, JSON, PNG, PDF op ware grootte en volledige back-ups.
- **Licht en donker thema**, Nederlands en Engels, voor macOS, Windows en Linux.

## Ondersteunde printers

| Printer | Etiketten | Status |
|---|---|---|
| Action Fichero 5836 (AiYin D11s) | 30 × 14 mm en andere rollen van 12 of 14 mm | Getest met echte hardware |

Zonder printer werkt de app ook, met een ingebouwde simulatieprinter. Nieuwe printers zijn toe te voegen via een profiel en een backend; zie [Een printertype toevoegen](docs/printertypes.md).

## Installatie

Etiknivo draait met [uv](https://docs.astral.sh/uv/getting-started/installation/), dat zelf de juiste Python-versie en alle afhankelijkheden installeert.

```bash
git clone https://github.com/D8bp8Ags/Etiknivo.git
cd Etiknivo
uv run etiknivo
```

Gebruik `uv run etiknivo --mock` om zonder printer te starten. Op macOS vraagt het systeem de eerste keer om Bluetooth-toegang voor de app waarin je het commando start.

## Aan de slag

1. Zet de printer aan, open het tabblad **Printer**, klik **Zoeken** en daarna **Verbinden**.
2. Druk een **Testlabel** af om de verbinding te controleren.
3. Maak of kies een label in de bibliotheek en klik **Afdrukken**.

Bij de eerste start staan er 23 voorbeeldlabels voor elektronicacomponenten klaar.

## Documentatie

- [Handleiding](docs/handleiding.md): alle functies, kalibreren, importeren en problemen oplossen.
- [Ontwikkelen](docs/ontwikkelen.md): architectuur, tests, vertalingen en de app bouwen.
- [Printerprotocol](docs/printer-protocol.md): het Bluetooth-protocol van de Fichero 5836.

## Licentie

MIT, zie [LICENSE](LICENSE). De meegeleverde DejaVu-lettertypen vallen onder hun eigen vrije licentie ([LICENSE-DejaVu.txt](src/etiknivo/fonts/LICENSE-DejaVu.txt)). Het app-icoon en alle pictogrammen zijn eigen ontwerpen.
