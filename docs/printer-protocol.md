# AiYin D11s-printerprotocol (Action Fichero 5836)

Werkdocument bij `src/etiknivo/printing/d11s_protocol.py` en `ble_link.py`. Alle waarden zijn hexadecimaal.

## Hardware

| Eigenschap | Waarde |
|---|---|
| Printkop | 96 dots = 12 bytes per rasterregel |
| Resolutie | 203 dpi (8 dots/mm) |
| Etiket | 30 × 14 mm; 30 mm = 240 rasterregels, dwars zijn alleen de middelste 12 mm printbaar |
| Bluetooth-naam | `FICHERO_xxxx` of `D11s_xxxx` |

## Bluetooth LE

De printer biedt meerdere gelijkwaardige UART-achtige GATT-diensten. Etiknivo kiest na het verbinden de eerste die aanwezig is:

| Dienst | Schrijven | Notificaties |
|---|---|---|
| `18F0` | `2AF1` | `2AF0` |
| `FF00` | `FF02` | `FF01` |
| `49535343-fe7d-…-9fafd205e455` (Microchip transparent UART) | `…9bb3` | `…9616` |

Commando's gaan als *write without response*. Antwoorden komen als notificatie en kunnen over meerdere pakketten verdeeld zijn; `BleLink` wacht daarom kort tot het stil is. Grote rasters worden opgedeeld in blokken van de maximale schrijfgrootte die het besturingssysteem meldt (standaard 180 bytes), met een kleine pauze ertussen.

## Opvragen

| Commando | Betekenis | Antwoord |
|---|---|---|
| `10 FF 20 F0` | model | ASCII, bv. `D11s` |
| `10 FF 20 F1` | firmware | ASCII |
| `10 FF 20 F2` | serienummer | ASCII |
| `10 FF 50 F1` | batterij | 2 bytes: status, percentage |
| `10 FF 40` | status | 1 byte bitmasker (zie onder) |

Statusbits: `01` printen · `02` deksel open · `04` papier op · `08` batterij laag · `10`/`40` oververhit · `20` laden. `00` betekent gereed.

## Instellingen

| Commando | Betekenis | Antwoord |
|---|---|---|
| `10 FF 10 00 nn` | dichtheid: 0 licht, 1 normaal, 2 donker | `OK` |
| `10 FF 84 nn` | papier: 0 etiket met tussenruimte, 1 zwarte markering, 2 doorlopend | `OK` |

## Afdrukken

Per etiket:

1. `10 FF 40`: status; stop bij deksel open, geen papier of oververhitting.
2. `10 FF 84 00`: papiermodus etiketten (de gap-sensor bepaalt de labelpositie).
3. 12 × `00`: wake.
4. `10 FF FE 01`: begin opdracht.
5. `1D 76 30 00 0C 00 yL yH` + bitmap: ESC/POS *GS v 0* (zie de Epson ESC/POS-referentie). 12 bytes per regel, `yL yH` = aantal regels (240 = `F0 00`), MSB = meest linkse dot, bit 1 = zwart.
6. `1D 0C`: form feed, de printer schuift door tot de volgende tussenruimte.
7. `10 FF FE 45`: einde opdracht; de printer antwoordt `AA` of `OK` als het etiket klaar is.

De dichtheid wordt één keer per opdracht gezet, vóór het eerste etiket.

De begin- en eindcommando's verschillen per printerfamilie. Andere printers op hetzelfde platform gebruiken `10 FF F1 03` en `10 FF F1 45`. Een D11s accepteert die zonder foutmelding maar drukt dan niets af, dus Etiknivo stuurt ze nooit.

## Nog te bevestigen op hardware

De opdrachtvolgorde en de pauzes in `d11s_backend.Timing` zijn alleen tegen een gesimuleerde verbinding getest. Bij de eerste echte afdrukken moet blijken of de pauzes korter kunnen en of de oriëntatie klopt; die laatste is instelbaar via de kalibratie.
