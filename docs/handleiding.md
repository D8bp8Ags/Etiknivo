# Handleiding Etiknivo

Etiknivo maakt en print etiketten op de Action Fichero 5836, standaard 30 × 14 mm en ook andere maten. Deze handleiding legt uit hoe je de app gebruikt. Technische details (installatie, protocol, architectuur) staan in de [README](../README.md).

- [Het venster](#het-venster)
- [De printer verbinden](#de-printer-verbinden)
- [Een label maken en bewerken](#een-label-maken-en-bewerken)
- [Specificaties en gekoppelde velden](#specificaties-en-gekoppelde-velden)
- [Pictogrammen en afbeeldingen](#pictogrammen-en-afbeeldingen)
- [QR-code en barcode](#qr-code-en-barcode)
- [Afdrukken](#afdrukken)
- [Een andere etiketrol](#een-andere-etiketrol)
- [Kalibreren](#kalibreren)
- [De bibliotheek beheren](#de-bibliotheek-beheren)
- [Importeren, exporteren en back-up](#importeren-exporteren-en-back-up)
- [Taal en thema](#taal-en-thema)
- [Problemen oplossen](#problemen-oplossen)
- [Sneltoetsen](#sneltoetsen)

## Het venster

![Het hoofdvenster](img/main-window.png)

Het venster heeft drie delen:

- **Links de bibliotheek**: al je labels als kaartjes met een echt printvoorbeeld. Bovenaan zoek je, kies je een categorie en hoe er gesorteerd wordt.
- **In het midden de voorbeelden**. *Ontwerp* toont het label zoals je het ontwerpt; de gearceerde randen kan de printer niet bedrukken en de stippellijn is de veilige marge. *Printerraster* toont exact de zwarte en witte puntjes die naar de printer gaan. Daaronder staat of alle tekst past.
- **Rechts de inspector** met twee tabbladen: *Ontwerp* (tekst, lettertype, layout) en *Printer* (verbinden, dichtheid, kalibratie).

Bovenaan staat de werkbalk met nieuw, dupliceren, hernoemen, verwijderen, ongedaan maken en opnieuw. Rechts daarvan zie je de printerstatus, de knop **Wachtrij** en de blauwe knop **Afdrukken**.

## De printer verbinden

![Het tabblad Printer met de wachtrij](img/printer-and-queue.png)

1. Zet de Fichero aan.
2. Open rechts het tabblad **Printer** en klik **Zoeken**. Met *Alleen labelprinters tonen* aan zie je alleen printers die Etiknivo kent.
3. Kies `FICHERO_5836` in de lijst en klik **Verbinden**, of dubbelklik erop. Etiknivo onthoudt de printer, zodat je hem de volgende keer meteen terugziet.

Onder *Status* zie je de batterij en of de printer klaar is. Is het deksel open of het papier op, dan staat dat daar ook, en stopt het afdrukken tot het opgelost is.

De eerste keer vraagt macOS om toestemming voor Bluetooth. Geef die aan de app waarmee je Etiknivo start (de app zelf, of Terminal als je `uv run` gebruikt).

**Zonder printer werken.** Zet *Simulatieprinter gebruiken* aan. De app doet dan alles alsof er een printer is, maar drukt niets af. Overal staat "(simulatie)" bij, zodat je het niet vergeet.

## Een label maken en bewerken

Klik **+** in de werkbalk (⌘N). Je kiest een categorie en het label opent in de inspector.

### Gegevens

- **Naam**: hoe het label in de bibliotheek heet.
- **Lade-ID**: bijvoorbeeld `A14`, om op te sorteren. Komt niet op het etiket, tenzij je `{Lade}` in een tekstregel zet.
- **Categorie**: groepeert labels in de bibliotheek. Kies een bestaande of typ een nieuwe.
- **Layout**: welke regels er op het etiket staan.

| Layout | Regels |
|---|---|
| 1 · Alleen naam | één grote regel |
| 2 · Naam + specificatie | grote regel met een kleinere eronder |
| 3 · Categorie + naam + specificatie | kleine bovenregel, grote hoofdregel, kleine onderregel |
| Aangepast | wat je zelf instelt |

Wisselen van layout gooit geen tekst weg: zet je hem terug, dan staat alles er weer. Zodra je zelf een lettergrootte of uitlijning verandert, wordt de layout *Aangepast*.

### Tekstregels

Per regel (Bovenregel, Hoofdregel, Onderregel) stel je in: de tekst, het lettertype, de grootte, vet en cursief, en de uitlijning. Met het vinkje zet je een regel aan of uit.

Onder de regels vind je instellingen voor het hele label: verticale uitlijning, regelafstand, marges, *Tekst automatisch passend maken* (verkleint de tekst tot alles past), 180° draaien, een rand en wit-op-zwart.

Speciale tekens zoals Ω, µ, °, ×, ¼ en ″ werken gewoon. Heeft het gekozen lettertype een teken niet, dan gebruikt Etiknivo DejaVu Sans voor dat teken en meldt dat onder het voorbeeld.

### Opslaan en herstellen

Wat je verandert is eerst een concept. In de bibliotheek krijgt het label een blauwe stip, en onderaan de inspector staat dat er niet-opgeslagen wijzigingen zijn.

- **Opslaan** (⌘S) bewaart het label in de bibliotheek.
- **Herstellen** zet het label terug naar de laatst opgeslagen versie.

Kies je een ander label of sluit je de app terwijl er een concept is, dan vraagt Etiknivo of je wilt opslaan, weggooien of annuleren. **Ongedaan maken** (⌘Z) en **Opnieuw** (⇧⌘Z) werken op alle wijzigingen, ook op verwijderen en importeren.

Je kunt een concept ook afdrukken zonder het eerst op te slaan; er wordt dan gedrukt wat je op het scherm ziet.

## Specificaties en gekoppelde velden

Onderaan het tabblad *Ontwerp* staan **Specificaties** en **Notities**.

Specificaties zet je één per regel, als `naam: waarde`:

```
Spanning: 50 V
Tolerantie: 10%
Behuizing: 0805
```

Typ in een tekstregel `{Spanning}` en op het etiket verschijnt `50 V`. Je kunt ook op de knop **{ }** naast een tekstveld klikken en het veld uit de lijst kiezen. Pas je later de specificatie aan, dan verandert het etiket vanzelf mee. Hoofdletters maken niet uit.

Naast je eigen specificaties werken altijd `{Naam}`, `{Lade}` en `{Categorie}`. Een veld dat niet bestaat blijft als tekst staan en geeft een waarschuwing onder het voorbeeld, zodat je een tikfout meteen ziet.

**Notities** zijn alleen voor jezelf, bijvoorbeeld waar je iets besteld hebt. Ze komen niet op het etiket. Specificaties en notities zijn wel doorzoekbaar en verschijnen als tooltip als je met de muis boven een label in de bibliotheek hangt.

## Pictogrammen en afbeeldingen

Onder *QR-code of barcode* staat **Pictogram**. Bij *Soort* kies je:

- **Symbool**: een van de ingebouwde elektronica-symbolen. Er zijn er 18: weerstand, potmeter, condensator, elco, diode, LED, transistor, IC, zekering, schakelaar, connector, batterij, spoel, kristal, aarde, schroef, moer en kabel.
- **Eigen afbeelding**: klik **Afbeelding kiezen…** en kies een PNG, JPG of SVG, bijvoorbeeld je logo. Etiknivo maakt hem zwart-wit, haalt witte randen weg en bewaart hem in het label zelf. Het originele bestand heb je daarna niet meer nodig, en de afbeelding gaat mee in exports en back-ups.

Met *Plaats* zet je het pictogram links of rechts van de tekst. De tekst schuift opzij en wordt zo nodig kleiner. Staan een QR-code en een pictogram aan dezelfde kant, dan komt de QR-code aan de buitenkant en het pictogram ernaast.

Afbeeldingen met veel kleine details of zachte kleurverlopen worden op 12 mm vaak onduidelijk. Eenvoudige vormen met dikke lijnen werken het best.

## QR-code en barcode

Onder de tekstregels staat **QR-code of barcode**. Bij *Soort* kies je:

- **QR-code links** of **QR-code rechts**: een vierkante code naast de tekst, om met je telefoon te scannen. De tekst schuift opzij en wordt zo nodig kleiner.
- **Barcode (Code 128) i.p.v. onderregel**: een streepjescode onderaan, voor een handscanner. De onderregel verdwijnt van het etiket, maar de tekst blijft bewaard; kies je weer *Geen*, dan komt hij terug.

Bij *Inhoud* zet je wat de code bevat. Standaard is dat `{Lade}`, de lade-ID. Velden werken net als in de tekstregels, dus met een specificatie `Datasheet: https://…` en als inhoud `{Datasheet}` opent de QR-code die link. Een onbekend veld geeft een waarschuwing en dan wordt er geen code gedrukt, zodat je nooit een code met `{…}` erin print.

Hoe korter de inhoud, hoe groter de blokjes of streepjes en hoe makkelijker het scant. Een QR-code past tot 134 tekens, maar tot ongeveer 40 tekens scant hij het best. Een barcode past tot ongeveer 15 tekens (cijfers het dubbele) en kan alleen letters, cijfers en leestekens zonder accenten bevatten; Ω of µ geven een waarschuwing.

Etiknivo maakt QR-codes en barcodes zelf, zonder externe bibliotheek of internet.

## Afdrukken

Er zijn vier manieren om af te drukken, allemaal in het menu **Afdrukken**:

- **Huidig label** (⌘P), ook via de blauwe knop rechtsboven.
- **Geselecteerde labels** (⇧⌘P). Selecteer meerdere labels met ⌘-klik of ⇧-klik.
- **Alle labels uit categorie**.
- **Alle labels**.

![Het afdrukvoorbeeld](img/handleiding/afdrukvoorbeeld.png)

Je ziet eerst een voorbeeld met precies wat er geprint wordt. Per label stel je het aantal exemplaren in, en onderaan de printdichtheid (licht, normaal of donker). Bij *Let op* staat het als tekst niet past of een veld onbekend is.

Na **Afdrukken** gaan de labels naar de **wachtrij** (knop *Wachtrij* rechtsboven, of Weergave → Printwachtrij). De wachtrij drukt ze één voor één af en toont per opdracht de voortgang:

- **Stop** pauzeert na het huidige etiket; **Hervat** gaat verder.
- Gaat er iets mis (deksel open, papier op, verbinding weg), dan stopt de wachtrij. Los het op en klik **Opnieuw**.
- **Annuleer** haalt wachtende opdrachten weg; **Wis klaar** ruimt afgeronde op.

Het standaard aantal exemplaren en de standaarddichtheid stel je in op het tabblad *Printer*. Kleine tekst is vaak beter leesbaar op *Licht* of *Normaal* dan op *Donker*.

## Een andere etiketrol

Zit er een rol met een andere maat in de printer, kies die dan op het tabblad *Printer* bij **Etiketrol**. In de lijst staan de gangbare maten, bijvoorbeeld 30 × 14, 40 × 14, 50 × 14 en 40 × 12 mm. Staat jouw maat er niet bij, kies dan **Aangepast…** en vul de lengte en hoogte van één etiket in, zonder de tussenruimte. De lengte is de richting waarin het papier uit de printer komt.

De keuze geldt voor alle labels. Het ontwerp, de voorbeelden, de kaartjes in de bibliotheek en het afdrukken passen zich meteen aan. De tekst van je labels blijft gewoon staan; met *Tekst automatisch passend maken* aan wordt hij vanzelf groter of kleiner. Etiknivo onthoudt de rol.

De printkop drukt maximaal 12 mm hoog. Is een etiket hoger, dan blijft er boven en onder een strook leeg; die is gearceerd in het ontwerp. Druk na het wisselen van rol een **Kalibratietest** af om te zien of alles goed staat.

## Kalibreren

Gebruik dit als de afdruk niet mooi in het midden van het etiket staat.

1. Kies op het tabblad *Printer* **Kalibratietest afdrukken**. Het etiket toont een kader rond het veilige gebied, middellijnen en een millimeterliniaal.
2. Kijk of de witruimte links en rechts, en boven en onder, gelijk is.
3. Open **Kalibratie-instellingen…** en verschuif de afdruk.

![Het kalibratievenster](img/handleiding/kalibratie.png)

- **Links / rechts**: positief schuift de afdruk naar rechts, negatief naar links. 8 dots is 1 mm; het venster rekent het voor je om.
- **Omhoog / omlaag**: positief schuift naar beneden, negatief naar boven.
- **Zwartdrempel**: hoger maakt letters dikker en zwarter, lager dunner. Standaard 140.
- **Gladde randen**: hoe nauwkeurig letters naar printerdots worden omgezet. 4× is meestal goed.
- **Etiket ondersteboven afdrukken**: zet dit aan als labels ondersteboven uit de printer komen.

Druk daarna opnieuw een kalibratietest af om te controleren. De Fichero begint uit zichzelf ongeveer 1 mm te vroeg; daar corrigeert Etiknivo al voor, dus meestal is geen kalibratie nodig.

## De bibliotheek beheren

- **Zoeken** doorzoekt naam, tekst op het etiket, lade-ID, specificaties en notities.
- **Categorie** toont alleen labels uit één categorie.
- **Sorteren** op lade-ID, naam, categorie of laatst gewijzigd.
- Via de knop met schuifjes zet je **Groeperen per categorie** aan of uit.
- **Dupliceren** (⌘D) maakt een kopie om snel een vergelijkbaar label te maken.
- **Hernoemen** (F2) en **Verwijderen** werken ook op meerdere geselecteerde labels; verwijderen kun je ongedaan maken.

### Opmaak overnemen

Wil je dat een hele categorie er hetzelfde uitziet, maak dan één label mooi en kies **Label → Opmaak overnemen…** (of rechtsklik in de bibliotheek). Vink aan wat er mee moet:

- **Layout en lettertypen**: welke regels zichtbaar zijn, lettertype, grootte, vet, cursief en uitlijning per regel.
- **Opmaak**: verticale uitlijning, regelafstand, marges, automatisch passend maken, rotatie, rand en wit-op-zwart.
- **QR-code of barcode**: soort, plaats en inhoud. Velden zoals `{Lade}` vullen zich per label in.
- **Pictogram**: symbool of afbeelding en de plaats.

Kies daarna op welke labels het moet: de geselecteerde labels, alle labels in een categorie, of alle labels. De knop laat zien hoeveel labels er veranderen. De tekst, specificaties en notities van die labels blijven zoals ze waren. Klopt het resultaat niet, dan zet ⌘Z alles in één keer terug.

Bij de eerste start staan er 23 voorbeeldlabels voor Raaco-laden met elektronicaonderdelen in. Die kun je gewoon aanpassen of verwijderen.

## Importeren, exporteren en back-up

Alles staat in het menu **Bestand**.

| Wat | Waarvoor |
|---|---|
| Bibliotheek importeren/exporteren (JSON) | Volledige labels uitwisselen tussen computers. Bij importeren kies je samenvoegen of vervangen. |
| Labels importeren/exporteren (CSV) | Labels maken of bijwerken in Excel, Numbers of Google Sheets. Het formaat staat in de [README](../README.md#csv-formaat). |
| Selectie exporteren als PNG, PDF of SVG | Een afbeelding van het etiket, bijvoorbeeld om te delen of op een andere printer te gebruiken. PDF is op ware grootte. |
| Back-up maken / herstellen | Eén zip-bestand met bibliotheek en instellingen. |
| Datamap openen | De map waar Etiknivo alles bewaart. |

Etiknivo bewaart alles lokaal op je eigen computer, zonder account. Bij elke keer opslaan blijft de vorige versie bewaard als `library.json.bak`.

## Taal en thema

- **Weergave → Taal / Language**: Nederlands, English, of de taal van je systeem. Herstart de app om te wisselen.
- **Weergave → Thema**: licht, donker, of volgen wat macOS gebruikt.
- **Weergave → Hulplijnen** toont of verbergt de marges in het ontwerpvoorbeeld.

## Problemen oplossen

**De printer wordt niet gevonden.** Controleer of de printer aan staat en niet al met je telefoon verbonden is; een Bluetooth-printer praat meestal maar met één apparaat tegelijk. Kijk in Systeeminstellingen → Privacy en beveiliging → Bluetooth of Etiknivo (of je terminal) toegang heeft. Zet even *Alleen labelprinters tonen* uit om te zien of de printer überhaupt zichtbaar is.

**De verbinding valt weg.** Klik **Verbinden** opnieuw; een onderbroken wachtrij hervat je met **Opnieuw**. Zet je de printer uit en aan, verbind dan opnieuw.

**De afdruk staat scheef of te ver naar één kant.** Zie [Kalibreren](#kalibreren).

**Tekst is te vaag of te vet.** Probeer een andere printdichtheid, of pas de zwartdrempel aan in de kalibratie-instellingen. Kies voor kleine tekst een groter of vet lettertype.

**Er staat "Tekst valt buiten het printbare gebied".** Maak de tekst korter of kleiner, of zet *Tekst automatisch passend maken* aan.

**Iets anders gaat mis.** Open **Help → Log tonen** (⌘L). Met het filter *Problemen* zie je alleen waarschuwingen en fouten. **Kopiëren** zet de zichtbare regels op het klembord, zodat je ze kunt doorsturen. Via **Help → Over Etiknivo** kopieer je ook de systeeminformatie.

## Sneltoetsen

Op Windows en Linux gebruik je Ctrl in plaats van ⌘.

| Toets | Actie |
|---|---|
| ⌘N | Nieuw label |
| ⌘S | Label opslaan |
| ⌘D | Dupliceren |
| F2 | Hernoemen |
| ⌘Z / ⇧⌘Z | Ongedaan maken / opnieuw |
| ⌘P | Huidig label afdrukken |
| ⇧⌘P | Geselecteerde labels afdrukken |
| ⌘L | Log tonen |
| ⌘Q | Afsluiten |
