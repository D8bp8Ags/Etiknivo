"""English interface texts, keyed by the Dutch original.

Keep ``{names}`` identical to the Dutch text; ``tests/test_i18n.py`` checks that
every text in the code has a translation here.  List what is missing with
``uv run python scripts/i18n_strings.py --missing``.
"""

EN: dict[str, str] = {
    # -- main window: toolbar, menus, status ------------------------------------------
    "Ontwerp": "Design",
    "Printer": "Printer",
    "Printwachtrij": "Print queue",
    "Werkbalk": "Toolbar",
    "Nieuw label": "New label",
    "Dupliceren": "Duplicate",
    "Hernoemen": "Rename",
    "Hernoemen (F2)": "Rename (F2)",
    "Hernoemen…": "Rename…",
    "Verwijderen": "Delete",
    "Ongedaan maken": "Undo",
    "Opnieuw": "Redo",
    "Printer beheren": "Manage printer",
    "Printwachtrij tonen of verbergen": "Show or hide the print queue",
    " Afdrukken": " Print",
    "Meer afdrukopties": "More print options",
    "Geselecteerde labels…": "Selected labels…",
    "Alle labels uit categorie…": "All labels in category…",
    "Alle labels…": "All labels…",
    "Testlabel": "Test label",
    "Kalibratietest": "Calibration test",
    "Herstellen": "Revert",
    "Wijzigingen aan dit label ongedaan maken": "Discard the changes to this label",
    "Opslaan": "Save",
    "ONTWERP": "DESIGN",
    "Bewerken met antialiasing. Gearceerd = wordt niet geprint (buiten de printkop of in de "
    "veilige marge); blauw = printbaar; groen = marges.":
        "Editing view with antialiasing. Hatched = not printed (outside the printhead or in "
        "the safe margin); blue = printable; green = margins.",
    "PRINTERRASTER  ·  {w} × {h} DOTS": "PRINTER RASTER  ·  {w} × {h} DOTS",
    "1-bit: exact de dots die geprint worden, op de plek waar ze op het etiket komen "
    "(inclusief je kalibratie).":
        "1-bit: exactly the dots that are printed, where they land on the label (including "
        "your calibration).",
    "Hulplijnen": "Guides",
    "Printbaar gebied en marges tonen": "Show printable area and margins",
    "Native {w} × {h}": "Native {w} × {h}",
    "Printerraster in de oriëntatie van de printkop tonen":
        "Show the printer raster in printhead orientation",
    "Uitzoomen": "Zoom out",
    "Inzoomen": "Zoom in",
    "&Bestand": "&File",
    "Label opslaan": "Save label",
    "Wijzigingen herstellen": "Revert changes",
    "Bibliotheek importeren (JSON)…": "Import library (JSON)…",
    "Bibliotheek exporteren (JSON)…": "Export library (JSON)…",
    "Labels importeren (CSV)…": "Import labels (CSV)…",
    "Labels exporteren (CSV)…": "Export labels (CSV)…",
    "Selectie exporteren als PNG…": "Export selection as PNG…",
    "Selectie exporteren als PDF…": "Export selection as PDF…",
    "Huidig label exporteren als SVG…": "Export current label as SVG…",
    "Back-up maken…": "Create backup…",
    "Back-up herstellen…": "Restore backup…",
    "Datamap openen": "Open data folder",
    "Afsluiten": "Quit",
    "Be&werken": "&Edit",
    "&Label": "&Label",
    "Nieuw": "New",
    "&Afdrukken": "&Print",
    "Huidig label…": "Current label…",
    "&Printer": "P&rinter",
    "Zoeken naar printers": "Search for printers",
    "Verbinden": "Connect",
    "Verbreken": "Disconnect",
    "Status vernieuwen": "Refresh status",
    "Kalibratie-instellingen…": "Calibration settings…",
    "Printwachtrij tonen": "Show print queue",
    "&Weergave": "&View",
    "Thema": "Theme",
    "Taal / Language": "Language / Taal",
    "&Help": "&Help",
    "Log tonen": "Show log",
    "Logmap openen": "Open log folder",
    "Over {app}": "About {app}",
    "Wijzigingen in “{name}” opslaan?": "Save changes to “{name}”?",
    "Je wijzigingen gaan verloren als je ze niet opslaat.":
        "Your changes will be lost if you don't save them.",
    "Niet opslaan": "Don't save",
    "Annuleren": "Cancel",
    "Wijzigingen hersteld": "Changes reverted",
    "Ongedaan gemaakt": "Undone",
    "Opnieuw uitgevoerd": "Redone",
    "Label hernoemen": "Rename label",
    "Nieuwe naam:": "New name:",
    " en {n} andere": " and {n} more",
    "{n} label(s) verwijderen?": "Delete {n} label(s)?",
    "niet verbonden": "not connected",
    "Categorie afdrukken": "Print category",
    "Categorie:": "Category:",
    "Printer gewijzigd in {model}. Start {app} opnieuw om dit model te gebruiken.":
        "Printer changed to {model}. Restart {app} to use this model.",
    "De nieuwe taal wordt gebruikt zodra je {app} opnieuw start.":
        "The new language is used when you restart {app}.",
    "simulatie": "simulation",
    "{state} (simulatie)": "{state} (simulation)",
    " · batterij {pct}%": " · battery {pct}%",
    "Verbonden": "Connected",
    "Verbinden…": "Connecting…",
    "Printerfout": "Printer error",
    "Geen printer": "No printer",
    "Bibliotheek importeren": "Import library",
    "Importeren": "Import",
    "{n} labels gevonden. Samenvoegen met de huidige bibliotheek of de bibliotheek vervangen?":
        "{n} labels found. Merge them into the current library or replace the library?",
    "Samenvoegen": "Merge",
    "Vervangen": "Replace",
    "{added} toegevoegd, {updated} bijgewerkt": "{added} added, {updated} updated",
    "Bibliotheek vervangen ({n} labels)": "Library replaced ({n} labels)",
    "Bibliotheek exporteren": "Export library",
    "{n} labels geëxporteerd": "{n} labels exported",
    "CSV importeren": "Import CSV",
    "CSV-import": "CSV import",
    "{n} labels geïmporteerd.": "{n} labels imported.",
    "Problemen:": "Problems:",
    "CSV exporteren": "Export CSV",
    "CSV geëxporteerd": "CSV exported",
    "Map kiezen voor {n} PNG's": "Choose a folder for {n} PNGs",
    "PNG-export": "PNG export",
    "Welke weergave exporteren?": "Which view should be exported?",
    "Ontwerp ({w} × {h}, 4× vergroot)": "Design ({w} × {h}, enlarged 4×)",
    "Printerraster ({w} × {h}, 1:1)": "Printer raster ({w} × {h}, 1:1)",
    "{n} PNG's opgeslagen in {folder}": "{n} PNGs saved in {folder}",
    "PDF exporteren": "Export PDF",
    "PDF met {n} pagina's opgeslagen": "PDF with {n} pages saved",
    "SVG exporteren": "Export SVG",
    "Back-up maken": "Create backup",
    "Back-up gemaakt ({files})": "Backup created ({files})",
    "Back-up herstellen": "Restore backup",
    "De huidige bibliotheek en instellingen worden overschreven. Doorgaan?":
        "The current library and settings will be overwritten. Continue?",
    "Back-up hersteld": "Backup restored",
    "● Niet opgeslagen": "● Not saved",
    "Geen label geselecteerd": "No label selected",
    "Opgeslagen": "Saved",
    "Opgeslagen en verplaatst naar {where}": "Saved and moved to {where}",
    "Bibliotheek opslaan mislukt:\n{error}": "Saving the library failed:\n{error}",
    "Alle tekst valt binnen het printbare gebied": "All text fits inside the printable area",
    "Er is geen printer verbonden.": "No printer is connected.",
    "Verbind eerst de printer opnieuw.": "Reconnect the printer first.",
    "Wachtrij  {n}": "Queue  {n}",
    "Wachtrij": "Queue",
    "{n} opdracht(en) in de wachtrij": "{n} job(s) in the queue",
    "Er wordt nog geprint. Toch afsluiten?": "Printing is still in progress. Quit anyway?",
    "{error}\n\nDe vorige versie staat in library.json.bak in {folder}.":
        "{error}\n\nThe previous version is in library.json.bak in {folder}.",
    # -- library ---------------------------------------------------------------------
    "Bibliotheek": "Library",
    "Alle categorieën": "All categories",
    "Lade-ID": "Tray ID",
    "Naam": "Name",
    "Categorie": "Category",
    "Laatst gewijzigd": "Last modified",
    "Sorteren": "Sort",
    "Weergaveopties": "View options",
    "Aflopend sorteren": "Sort descending",
    "Groeperen per categorie": "Group by category",
    "Zoeken op naam, tekst, lade-ID…": "Search name, text, tray ID…",
    "{n} van {total}": "{n} of {total}",
    "{n} labels": "{n} labels",
    "Selectie afdrukken…": "Print selection…",
    "(zonder categorie)": "(no category)",
    # -- properties ------------------------------------------------------------------
    "Bovenregel": "Top line",
    "Hoofdregel": "Main line",
    "Onderregel": "Bottom line",
    "Lade": "Tray",
    "Links": "Left",
    "Midden": "Centre",
    "Rechts": "Right",
    "Boven": "Top",
    "Onder": "Bottom",
    "Tekst of {veld}…": "Text or {field}…",
    "Veld invoegen: toont de waarde van een specificatie, de naam, lade of categorie op het "
    "etiket": "Insert field: shows the value of a specification, the name, tray or category "
               "on the label",
    "Nog geen velden": "No fields yet",
    "Vet": "Bold",
    "Cursief": "Italic",
    "Tekst": "Text",
    "Lettertype": "Font",
    "Grootte": "Size",
    "Uitlijning": "Alignment",
    "Label": "Label",
    "Layout": "Layout",
    "Opmaak": "Style",
    "Tekst automatisch passend maken": "Shrink text to fit",
    "180° (ondersteboven)": "180° (upside down)",
    "Rand rond printbaar gebied": "Border around printable area",
    "Wit op zwart": "White on black",
    "Verticaal": "Vertical",
    "Regelafstand": "Line spacing",
    "Marge horizontaal": "Horizontal margin",
    "Marge verticaal": "Vertical margin",
    "Rotatie": "Rotation",
    "Specificaties en notities": "Specifications and notes",
    "Specificaties": "Specifications",
    "Notities": "Notes",
    "Automatisch verkleind tot {pt} pt": "Automatically reduced to {pt} pt",
    # -- printer panel ---------------------------------------------------------------
    "Niet verbonden": "Not connected",
    "Fout": "Error",
    "Bluetooth-printer": "Bluetooth printer",
    "Simulatieprinter gebruiken": "Use simulated printer",
    "Voor testen zonder printer (geen hardware). Er wordt niets echt afgedrukt.":
        "For testing without a printer (no hardware). Nothing is actually printed.",
    "Alleen labelprinters tonen": "Show label printers only",
    "Zoeken": "Search",
    "Status": "Status",
    "Verbinding": "Connection",
    "Batterij": "Battery",
    "Toestand": "Condition",
    "Afdrukinstellingen": "Print settings",
    "Testlabel afdrukken": "Print test label",
    "Kalibratietest afdrukken": "Print calibration test",
    "Printdichtheid": "Print density",
    "Exemplaren": "Copies",
    "onbekend": "unknown",
    # -- queue -----------------------------------------------------------------------
    "Wachtrij leeg": "Queue empty",
    "Stop": "Stop",
    "Printen stoppen na het huidige etiket": "Stop printing after the current label",
    "Hervat": "Resume",
    "Wachtrij hervatten": "Resume the queue",
    "Mislukte en geannuleerde opdrachten opnieuw proberen": "Retry failed and cancelled jobs",
    "Annuleer": "Cancel",
    "Wachtende opdrachten annuleren": "Cancel waiting jobs",
    "Wis klaar": "Clear done",
    "Afgeronde opdrachten uit de lijst halen": "Remove finished jobs from the list",
    "Dichtheid": "Density",
    "Melding": "Message",
    "<b style='color:{color}'>Gestopt</b> · {pending} wachtend · {failed} mislukt":
        "<b style='color:{color}'>Stopped</b> · {pending} waiting · {failed} failed",
    "Bezig met printen · {pending} wachtend": "Printing · {pending} waiting",
    "{done}/{total} etiketten klaar": "{done}/{total} labels done",
    " · {failed} mislukt": " · {failed} failed",
    "Wachtend": "Waiting",
    "Bezig": "Printing",
    "Klaar": "Done",
    "Mislukt": "Failed",
    "Geannuleerd": "Cancelled",
    # -- dialogs ---------------------------------------------------------------------
    "Afdrukvoorbeeld": "Print preview",
    "<b>{n} label(s)</b> — dit is de 1-bit printerraster zoals die naar de printer gaat. "
    "Printer: {printer}": "<b>{n} label(s)</b> — this is the 1-bit printer raster exactly as "
                          "it is sent to the printer. Printer: {printer}",
    "Voorbeeld": "Preview",
    "Let op": "Note",
    "Totaal": "Total",
    "Afdrukken": "Print",
    "{n} etiketten": "{n} labels",
    "{n} label(s) hebben tekst buiten het printbare gebied.":
        "{n} label(s) have text outside the printable area.",
    "Geen printer verbonden. Verbind eerst in het printerpaneel (of zet de simulatieprinter "
    "aan).": "No printer connected. Connect one in the printer panel first (or switch on the "
             "simulated printer).",
    "Kalibratie": "Calibration",
    "Zo kalibreer je": "How to calibrate",
    "Kies <i>Afdrukken → Kalibratietest</i>. Er komt een kader met middellijnen en een "
    "millimeterliniaal op het etiket.": "Choose <i>Print → Calibration test</i>. The label "
                                        "shows a frame with centre lines and a millimetre "
                                        "ruler.",
    "Kijk of er links en rechts evenveel wit naast het kader staat (ongeveer 2 mm), en boven "
    "en onder ook.": "Check that there is equal white space left and right of the frame (about "
                     "2 mm), and above and below too.",
    "Staat het scheef? Verschuif hieronder, druk opnieuw af en herhaal tot het klopt.":
        "Off-centre? Shift it below, print again and repeat until it is right.",
    "Bekende afwijkingen van je printer worden al automatisch gecorrigeerd. Meestal is alles "
    "hier 0 goed.": "Known deviations of your printer are already corrected automatically. "
                    "Usually 0 everywhere is right.",
    "Positie op het etiket": "Position on the label",
    "Links / rechts": "Left / right",
    "Omhoog / omlaag": "Up / down",
    "Afdrukkwaliteit": "Print quality",
    "Etiket ondersteboven afdrukken": "Print the label upside down",
    "Zwartdrempel": "Black threshold",
    "Bepaalt hoe dik letters worden. Hoger = dikker en zwarter, lager = dunner. Standaard 140; "
    "pas aan als kleine tekst dichtloopt of wegvalt.":
        "Controls how heavy letters are. Higher = bolder and blacker, lower = thinner. Default "
        "140; adjust if small text fills in or disappears.",
    "Gladde randen": "Smooth edges",
    "Hoe nauwkeurig letters naar printerdots worden omgezet. 4× is scherp en snel genoeg; "
    "hoger maakt weinig verschil.": "How precisely letters are converted to printer dots. 4× "
                                    "is sharp and fast enough; higher makes little difference.",
    "Alleen nodig als je labels op hun kop uit de printer komen.":
        "Only needed if your labels come out of the printer upside down.",
    "Standaardwaarden": "Defaults",
    "Geen verschuiving.": "No shift.",
    "Afdruk schuift {mm} mm {direction} ({dpm} dots = 1 mm).":
        "Print moves {mm} mm {direction} ({dpm} dots = 1 mm).",
    "naar rechts": "to the right",
    "naar links": "to the left",
    "naar onder": "down",
    "naar boven": "up",
    "Meer wit links dan rechts? Kies een negatief getal; meer wit rechts: positief.":
        "More white on the left than the right? Choose a negative number; more on the right: "
        "positive.",
    "Meer wit boven dan onder? Kies een negatief getal; meer wit onder: positief.":
        "More white at the top than the bottom? Choose a negative number; more at the bottom: "
        "positive.",
    "Versie {version}": "Version {version}",
    "Etiketten ontwerpen, beheren en afdrukken.\nOpen source, lokaal, zonder account.":
        "Design, manage and print labels.\nOpen source, local, no account.",
    "Model": "Model",
    "Printkop": "Printhead",
    "Etiket": "Label",
    "{w} × {h} mm, veilig gebied {sw} × {sh} mm": "{w} × {h} mm, safe area {sw} × {sh} mm",
    "Gegevens": "Data",
    "Logs": "Logs",
    "Broncode": "Source code",
    "Met dank aan": "Thanks to",
    "Interface": "Interface",
    "Bluetooth": "Bluetooth",
    "Beeldbewerking": "Imaging",
    "DejaVu Sans, vrije licentie": "DejaVu Sans, free licence",
    "© {app}-bijdragers · MIT-licentie": "© {app} contributors · MIT licence",
    "Systeeminfo kopiëren": "Copy system info",
    "Versies van Etiknivo, Python, Qt en het besturingssysteem, handig bij een foutmelding":
        "Versions of Etiknivo, Python, Qt and the operating system, useful for a bug report",
    "Sluiten": "Close",
    "Gekopieerd ✓": "Copied ✓",
    # -- log window ------------------------------------------------------------------
    "Alles": "Everything",
    "Waarschuwingen en fouten": "Warnings and errors",
    "Printopdrachten": "Print jobs",
    "Log": "Log",
    "Zoeken in log…": "Search log…",
    "Bewaard in app.log en print.log, ook na afsluiten of een crash.":
        "Kept in app.log and print.log, also after quitting or a crash.",
    "Kopiëren": "Copy",
    "Zichtbare regels naar het klembord, bv. voor een foutmelding":
        "Copy the visible lines to the clipboard, e.g. for a bug report",
    "Wissen": "Clear",
    "Leegt dit venster; de logbestanden blijven bewaard":
        "Empties this window; the log files are kept",
    "1 regel": "1 line",
    "{n} regels": "{n} lines",
    # -- theme -----------------------------------------------------------------------
    "Systeem": "System",
    "Licht": "Light",
    "Donker": "Dark",
    # -- printing --------------------------------------------------------------------
    "Printer niet gereed: {status}": "Printer not ready: {status}",
    "onbekend (geen antwoord)": "unknown (no answer)",
    "gereed": "ready",
    "deksel open": "cover open",
    "papier op / geen etiket gedetecteerd": "out of paper / no label detected",
    "printkop oververhit": "printhead overheated",
    "batterij bijna leeg": "battery low",
    "bezig met printen": "printing",
    "laadt op": "charging",
    "Raster moet 1-bit zijn (mode '1'), niet '{mode}'":
        "Raster must be 1-bit (mode '1'), not '{mode}'",
    "Rasterbreedte {width} ≠ printkopbreedte {head}": "Raster width {width} ≠ printhead width {head}",
    "Ongeldige rasterhoogte {height}": "Invalid raster height {height}",
    "Geen bekende printerdienst gevonden op dit Bluetooth-apparaat":
        "No known printer service found on this Bluetooth device",
    "Geen antwoord op {cmd} binnen {s} s": "No answer to {cmd} within {s} s",
    "Verbinden mislukt na {n} pogingen: {error}": "Connecting failed after {n} attempts: {error}",
    "Geen printer verbonden": "No printer connected",
    "Bluetooth-scan mislukt: {error}. Staat Bluetooth aan en heeft de app "
    "Bluetooth-toestemming?": "Bluetooth scan failed: {error}. Is Bluetooth on and does the "
                              "app have Bluetooth permission?",
    "Printer {address} niet gevonden. Staat hij aan en binnen bereik?":
        "Printer {address} not found. Is it switched on and in range?",
    "Geen ondersteunde labelprinter gevonden. Staat hij aan?":
        "No supported label printer found. Is it switched on?",
    "Printer antwoordt niet (time-out)": "Printer does not answer (timeout)",
    "Bluetooth-fout: {error}": "Bluetooth error: {error}",
    "Afdrukken gestopt": "Printing stopped",
    "Verbinding verbroken. Je kunt opnieuw verbinden.":
        "Connection lost. You can connect again.",
    "Backend: {name}": "Backend: {name}",
    "Zoeken naar Bluetooth-apparaten…": "Searching for Bluetooth devices…",
    "Verbroken": "Disconnected",
    "Status bijgewerkt": "Status updated",
    "Verbinden mislukt: {error}": "Connecting failed: {error}",
    "Status opvragen mislukt: {error}": "Reading the status failed: {error}",
    "Simulatie (geen echte printer)": "Simulation (no real printer)",
    "Gesimuleerde Bluetooth-fout": "Simulated Bluetooth error",
    "{name} (simulatie)": "{name} (simulation)",
    "Aantal exemplaren moet minimaal 1 zijn": "The number of copies must be at least 1",
    "Afgebroken": "Aborted",
    "Onverwachte fout: {error}": "Unexpected error: {error}",
    # -- rendering, storage ----------------------------------------------------------
    "Verwacht mode '1', kreeg '{mode}'": "Expected mode '1', got '{mode}'",
    "Tekst past niet, zelfs niet bij de minimale lettergrootte ({pt} pt). Kort de tekst in "
    "of verklein de marges.": "Text does not fit, not even at the minimum font size ({pt} "
                              "pt). Shorten the text or reduce the margins.",
    "Label bevat geen zichtbare tekst": "Label has no visible text",
    "Regel '{text}' valt buiten het printbare gebied": "Line '{text}' is outside the printable area",
    "Onbekend veld {{{name}}}: voeg '{name}' toe bij Specificaties":
        "Unknown field {{{name}}}: add '{name}' under Specifications",
    "Lettertype '{font}' mist teken(s) {chars}; '{fallback}' gebruikt voor deze regel":
        "Font '{font}' lacks character(s) {chars}; '{fallback}' used for this line",
    "Teken(s) {chars} kunnen niet worden weergegeven": "Character(s) {chars} cannot be shown",
    "Lettertype '{font}' niet gevonden; '{used}' gebruikt": "Font '{font}' not found; '{used}' used",
    "Geen labels om te exporteren": "No labels to export",
    "Kolom 'main' (of 'hoofdtekst') ontbreekt in de kopregel":
        "Column 'main' (or 'hoofdtekst') is missing in the header",
    "Regel {n}: hoofdtekst ontbreekt": "Line {n}: main text missing",
    "Regel {n}: onbekende layout '{layout}', standaard gebruikt":
        "Line {n}: unknown layout '{layout}', default used",
    "Geen geldig back-upbestand: {error}": "Not a valid backup file: {error}",
    "Back-up is beschadigd: {error}": "Backup is damaged: {error}",
    "Back-up bevat geen library.json": "Backup does not contain library.json",
    "Ongeldig bibliotheekbestand: lijst 'labels' ontbreekt":
        "Invalid library file: list 'labels' is missing",
    "Ongeldig label op positie {n}": "Invalid label at position {n}",
    "Ongeldig label op positie {n}: {error}": "Invalid label at position {n}: {error}",
    "Bibliotheek kon niet worden gelezen: {error}": "The library could not be read: {error}",
    # QR code and barcode
    "Geen": "None",
    "QR-code links": "QR code on the left",
    "QR-code rechts": "QR code on the right",
    "Barcode (Code 128) i.p.v. onderregel": "Barcode (Code 128) instead of bottom line",
    "QR-code of barcode": "QR code or barcode",
    "Tekst of {veld}, bv. {Lade} of een link": "Text or {field}, e.g. {Tray} or a link",
    "Soort": "Type",
    "Inhoud": "Content",
    "{slot} (vervangen door barcode)": "{slot} (replaced by barcode)",
    "Scan met je telefoon. Korte tekst geeft grotere blokjes die makkelijker scannen; een link "
    "past tot ongeveer 40 tekens goed.":
        "Scan it with your phone. Short text gives larger squares that scan more easily; a link "
        "of up to about 40 characters works well.",
    "Voor een handscanner. Komt op de plaats van de onderregel; die tekst blijft bewaard. Past "
    "tot ongeveer 15 tekens (cijfers het dubbele); korter geeft dikkere streepjes. Alleen "
    "letters, cijfers en leestekens zonder accenten.":
        "For a handheld scanner. Takes the place of the bottom line, whose text is kept. Fits "
        "about 15 characters (twice as many digits); shorter text gives thicker bars. Only "
        "letters, digits and punctuation without accents.",
    "De code is leeg: vul de tekst voor de code in": "The code is empty: fill in its content",
    "Tekst is te lang voor een barcode op dit etiket": "Text is too long for a barcode on this label",
    "QR-code wordt te klein om te scannen; kort de tekst in":
        "The QR code gets too small to scan; shorten the text",
    "Teken(s) {chars} kunnen niet in een barcode; gebruik letters, cijfers en leestekens zonder "
    "accenten":
        "Character(s) {chars} cannot go in a barcode; use letters, digits and punctuation without "
        "accents",
    "Tekst is te lang voor een QR-code (maximaal {n} tekens)":
        "Text is too long for a QR code (at most {n} characters)",
    "De barcode heeft erg dunne streepjes; kort de tekst in als hij slecht scant":
        "The barcode has very thin bars; shorten the text if it scans poorly",
    # label rolls
    "Andere etiketmaat": "Other label size",
    "Meet een etiket op de rol, zonder de tussenruimte. De lengte is de richting waarin het "
    "papier uit de printer komt; de hoogte gaat over de printkop (die drukt maximaal 12 mm).":
        "Measure one label on the roll, without the gap. The length is the direction in which "
        "the paper comes out of the printer; the height runs across the printhead (which prints "
        "at most 12 mm).",
    "Lengte": "Length",
    "Hoogte": "Height",
    "Etiketrol: {size}": "Label roll: {size}",
    "Welke etiketten er in de printer zitten. Alle labels worden voor deze maat ontworpen en "
    "afgedrukt.":
        "Which labels are in the printer. All labels are designed and printed for this size.",
    "Etiketrol": "Label roll",
    "Aangepast…": "Custom…",
    # pictograms
    "Symbool": "Symbol",
    "Eigen afbeelding": "Own image",
    "Pictogram": "Pictogram",
    "Afbeelding kiezen…": "Choose image…",
    "PNG, JPG of SVG, bv. een logo. Wordt zwart-wit afgedrukt en in het label bewaard.":
        "PNG, JPG or SVG, e.g. a logo. Printed in black and white and stored in the label.",
    "Plaats": "Position",
    "Afbeelding": "Image",
    "Afbeelding kiezen": "Choose image",
    "Andere afbeelding…": "Other image…",
    "Afbeeldingen": "Images",
    "'{name}' kon niet worden gelezen als afbeelding.": "'{name}' could not be read as an image.",
    "Geen ruimte voor het pictogram": "No room for the pictogram",
    "Onbekend symbool '{name}'": "Unknown symbol '{name}'",
    "Geen afbeelding gekozen": "No image chosen",
    "Weerstand": "Resistor",
    "Potmeter": "Potentiometer",
    "Condensator": "Capacitor",
    "Elco": "Electrolytic capacitor",
    "Diode": "Diode",
    "LED": "LED",
    "Transistor": "Transistor",
    "IC": "IC",
    "Zekering": "Fuse",
    "Schakelaar": "Switch",
    "Connector": "Connector",
    "Spoel": "Inductor",
    "Kristal": "Crystal",
    "Aarde": "Ground",
    "Schroef": "Screw",
    "Moer": "Nut",
    "Kabel": "Cable",
    # copy format
    "Opmaak overnemen": "Copy format",
    "De opmaak van <b>{name}</b> overnemen. De tekst, specificaties en notities van de andere "
    "labels blijven zoals ze zijn.":
        "Copy the format of <b>{name}</b>. The text, specifications and notes of the other "
        "labels stay as they are.",
    "Wat": "What",
    "Op welke labels": "To which labels",
    "Geselecteerde labels ({n})": "Selected labels ({n})",
    "Alle labels in categorie": "All labels in category",
    "Alle labels": "All labels",
    "Toepassen": "Apply",
    "Toepassen op {n} label(s)": "Apply to {n} label(s)",
    "Opmaak overnemen…": "Copy format…",
    "Opmaak overgenomen op {n} label(s)": "Format copied to {n} label(s)",
    "Layout en lettertypen": "Layout and fonts",
    "Opmaak (uitlijning, marges, rand, rotatie)": "Style (alignment, margins, border, rotation)",
    "90° (van onder naar boven lezen)": "90° (reads bottom to top)",
    "270° (van boven naar onder lezen)": "270° (reads top to bottom)",
    # print history
    "Afdrukgeschiedenis": "Print history",
    "Afdrukgeschiedenis…": "Print history…",
    "Zoeken op lade of naam…": "Search by drawer or name…",
    "Simulatie verbergen": "Hide simulation",
    "Opnieuw afdrukken gebruikt het label zoals het nu is.": "Printing again uses the label as it is now.",
    "Opnieuw afdrukken…": "Print again…",
    "Geschiedenis wissen…": "Clear history…",
    "Geschiedenis wissen": "Clear history",
    "{n} opdrachten, {m} etiketten": "{n} jobs, {m} labels",
    "Wanneer": "When",
    "De hele afdrukgeschiedenis wissen?": "Clear the entire print history?",
    "Simulatie": "Simulation",
    "(verwijderd)": "(deleted)",
    # print-time fields
    "Datum": "Date",
    "Nr": "No",
    "Aantal": "Count",
    "Lijn tussen tekstregels": "Line between text lines",
    # updates
    "Zoeken naar updates…": "Check for updates…",
    "Bij opstarten naar updates zoeken": "Check for updates at start-up",
    "Nieuwe versie": "New version",
    "{app} {new} is beschikbaar. Je gebruikt versie {current}.":
        "{app} {new} is available. You are using version {current}.",
    "Downloadpagina openen": "Open download page",
    "Zoeken naar updates": "Check for updates",
    "Kon niet zoeken naar updates: {error}": "Could not check for updates: {error}",
    "Er is nog geen versie gepubliceerd op GitHub.": "No version has been published on GitHub yet.",
    "Je gebruikt de nieuwste versie ({version}).": "You are using the latest version ({version}).",
    "Onbekend versienummer: {tag}": "Unknown version number: {tag}",
    "GitHub antwoordde met fout {code}": "GitHub answered with error {code}",
    "Geen verbinding met GitHub ({error})": "Cannot reach GitHub ({error})",
    "Onverwacht antwoord van GitHub": "Unexpected answer from GitHub",
    "Huidig label afdrukken": "Print current label",
    "Wijzigingen opslaan": "Save changes",
    # free layout
    "Elementen": "Elements",
    "Naar voren: boven de andere elementen tekenen": "Bring forward: draw above the other elements",
    "Naar achteren: onder de andere elementen tekenen": "Send backward: draw below the other elements",
    "Sleep een element in het ontwerp om het te verplaatsen; sleep het hoekje rechtsonder om het "
    "groter of kleiner te maken. Pijltjestoetsen schuiven 1 dot (met Shift 1 mm).":
        "Drag an element in the design to move it; drag its bottom-right corner to make it "
        "larger or smaller. Arrow keys move it 1 dot (with Shift 1 mm).",
    "Element": "Element",
    "Plaats (x, y)": "Position (x, y)",
    "Grootte (b, h)": "Size (w, h)",
    "Toevoegen": "Add",
    "QR-code": "QR code",
    "Barcode": "Barcode",
    "Lijn": "Line",
    "Kader": "Frame",
    "Label bevat geen elementen: voeg er een toe": "Label has no elements: add one",
    "{element} valt deels buiten het printbare gebied": "{element} is partly outside the printable area",
    "Tekst '{text}' past niet in zijn vak, zelfs niet bij de minimale lettergrootte":
        "Text '{text}' does not fit its box, even at the smallest font size",
    "Kies een symbool": "Choose a symbol",
    # -- files and devices ---------------------------------------------------------------
    "Het bestand kon niet worden gelezen of geschreven:\n{error}":
        "The file could not be read or written:\n{error}",
    "(naamloos)": "(unnamed)",
    "{found} apparaten gevonden, {n} ondersteunde printer(s)":
        "{found} devices found, {n} supported printer(s)",
    "CSV-bestand kon niet worden gedecodeerd": "CSV file could not be decoded",
    "JSON kon niet worden gelezen: {error}": "JSON could not be read: {error}",
    "CSV-bestand is leeg": "CSV file is empty",
    "CSV-bestand bevat geen kopregel": "CSV file has no header row",
    "{name} (kopie)": "{name} (copy)",
    # -- specifications table and narrow inspector -------------------------------------
    "Stijl": "Style",
    "Een specificatie heeft een naam en een waarde, bv. Spanning en 50 V. Zet {Spanning} in "
    "een tekstregel (of gebruik de knop { } achter de specificatie) om de waarde op het "
    "etiket te tonen. Pas je de waarde aan, dan verandert het etiket mee.":
        "A specification has a name and a value, e.g. Voltage and 50 V. Put {Voltage} in a "
        "text line (or use the { } button after the specification) to show the value on the "
        "label. Change the value and the label follows.",
    "Alleen voor jezelf, bv. waar besteld. Komt niet op het etiket.":
        "Just for you, e.g. where it was ordered. Not printed on the label.",
    "Notities komen niet op het etiket, dus een {veld} wordt hier niet ingevuld. Zet het in "
    "een tekstregel.":
        "Notes are not printed, so a {field} is not filled in here. Put it in a text line.",
    "het geselecteerde element": "the selected element",
    "+ Specificatie": "+ Specification",
    "Nieuwe specificatie, bv. Spanning met de waarde 50 V":
        "New specification, e.g. Voltage with the value 50 V",
    "Geselecteerde specificatie verwijderen": "Delete the selected specification",
    "Een {veld} in een waarde wordt niet ingevuld: typ de waarde zelf, bv. 50 V.":
        "A {field} in a value is not filled in: type the value itself, e.g. 50 V.",
    "Waarde": "Value",
    "In {place} zetten": "Put in {place}",
    "{field} op het etiket zetten": "Put {field} on the label",
    "Geef de specificatie eerst een naam": "Give the specification a name first",
    # -- label overview ----------------------------------------------------------------
    "Labeloverzicht…": "Label overview…",
    "Labeloverzicht": "Label overview",
    "Grootte van de etiketjes": "Size of the labels",
    "Klik op een label om het te openen.": "Click a label to open it.",
    "Opslaan als PDF…": "Save as PDF…",
    "A4-pagina's met de labels op ware grootte, om af te drukken en bij je ladekast te hangen":
        "A4 pages with the labels at real size, to print and hang next to your drawers",
    "Opslaan als PNG…": "Save as PNG…",
    "Eén afbeelding met alle labels": "One image with all labels",
    "Labeloverzicht opslaan": "Save label overview",
    "Geen labels gevonden": "No labels found",
    "{app} · pagina {n} van {total}": "{app} · page {n} of {total}",
    "{n} labels · {date}": "{n} labels · {date}",
    "(vervolg)": "(continued)",
    # -- symbols and their categories ------------------------------------------------
    "Luidspreker": "Speaker",
    "Antenne": "Antenna",
    "Batterijcel": "Battery cell",
    "Spanning": "Voltage",
    "Lamp": "Lamp",
    "Stopcontact": "Socket",
    "Stekker": "Plug",
    "USB": "USB",
    "Bout": "Bolt",
    "Ring": "Washer",
    "Spijker": "Nail",
    "Plug": "Wall plug",
    "Haak": "Hook",
    "Veer": "Spring",
    "Hamer": "Hammer",
    "Schroevendraaier": "Screwdriver",
    "Steeksleutel": "Wrench",
    "Zaag": "Saw",
    "Liniaal": "Ruler",
    "Boor": "Drill",
    "Huis": "House",
    "Pot": "Jar",
    "Fles": "Bottle",
    "Mok": "Mug",
    "Bestek": "Cutlery",
    "Vriezer": "Freezer",
    "Vlam": "Flame",
    "Water": "Water",
    "Plant": "Plant",
    "Doos": "Box",
    "Map": "Folder",
    "Document": "Document",
    "Envelop": "Envelope",
    "Potlood": "Pencil",
    "Schaar": "Scissors",
    "Boek": "Book",
    "Sleutel": "Key",
    "Verboden": "Prohibited",
    "Informatie": "Information",
    "Vinkje": "Check mark",
    "Kruis": "Cross",
    "Breekbaar": "Fragile",
    "Ster": "Star",
    "Hart": "Heart",
    "Elektronica": "Electronics",
    "Gereedschap": "Tools",
    "Bevestiging": "Fasteners",
    "Aanduidingen": "Signs",
    "Deze kant boven": "This way up",
    "Stroom en kabels": "Power and cables",
    "Huis en keuken": "Home and kitchen",
    "Kantoor en opslag": "Office and storage",
    "Regel '{text}' past niet en is ingekort": "Line '{text}' does not fit and was shortened",
    # -- layout switch ----------------------------------------------------------------
    "Tot drie tekstregels onder elkaar, met een QR-code of barcode en een pictogram ernaast":
        "Up to three lines of text, with a QR code or barcode and a pictogram beside them",
    "Losse elementen die je in het ontwerp versleept en schaalt":
        "Loose elements you drag and resize in the design",
    "Regels":
        "Lines",
    "Vrij":
        "Free",
    "Vrije layout":
        "Free layout",
    "De regels zijn veranderd sinds je de vrije layout maakte.":
        "The lines have changed since you made the free layout.",
    "Wil je de elementen opnieuw maken uit de regels, of je vorige vrije layout houden?":
        "Do you want to make the elements again from the lines, or keep your earlier free layout?",
    "Opnieuw maken":
        "Make again",
    "Vorige houden":
        "Keep earlier",
    "De lade-ID komt alleen op het etiket als een element {Lade} bevat. De elementen staan los van de"
    " regels: wat je hier verandert, komt daar niet terug.":
        "The tray ID is only printed if an element contains {Tray}. The elements are separate from "
        "the lines: what you change here does not carry over.",
    "De lade-ID komt alleen op het etiket als een regel {Lade} bevat. Met 1, 2 of 3 zet je regels aan"
    " of uit; hun tekst en opmaak blijven bewaard.":
        "The tray ID is only printed if a line contains {Tray}. 1, 2 or 3 turns lines on or off; "
        "their text and style are kept.",
    "Alleen de hoofdregel":
        "Only the main line",
    "Hoofdregel en onderregel":
        "Main line and bottom line",
    "Bovenregel, hoofdregel en onderregel":
        "Top line, main line and bottom line",
}
