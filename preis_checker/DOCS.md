# Preis-Checker

## Einrichten
1. Add-on starten, links in der Seitenleiste **Preis-Checker** öffnen.
2. Oben **Einstellungen**: Adresse, Strom-/Internetvertrag, Produkte eintragen → Speichern.
3. **Übersicht → Jetzt prüfen**. Danach automatisch alle 6 Stunden (einstellbar).

## Preisverlauf & Statistik
Jeder Shop-Preis wird bei jeder Prüfung gespeichert. Auf der Detailseite eines Artikels: Diagramm (7/30/90 Tage/alles, Shops ein-/ausblendbar), Tiefstpreis, Ø 30 Tage, Schwankung, Trend und eine Einschätzung („Tiefstpreis“, „Guter Preis“, „Eher teuer“, „Abwarten“).

## Shops
Preisvergleiche (Geizhals, idealo) werden immer abgefragt. Je nach Kategorie des Artikels zusätzlich Elektronikmärkte (MediaMarkt, Saturn, Amazon, Otto, Cyberport, notebooksbilliger, Galaxus, expert, Euronics, Kaufland, Conrad) oder PC-Hardware (Alternate, Mindfactory, Caseking, Proshop …). Ein-/ausschalten unter Einstellungen → Shops. Der Status jedes Shops steht unten auf der Übersicht.

## Schnellsuche
Übersicht → Suchbegriff eingeben → nach ca. 30–60 s Preise aller Shops. „Beobachten + Preisalarm“ übernimmt den Artikel in die Liste.

## Andere Personen
Jede Person mit eigenem HA-Konto (auch ohne Admin-Rechte) sieht „Preis-Checker“ in der Seitenleiste – im Browser und in der HA-App.

## Sensoren
Werden automatisch angelegt, keine YAML nötig:
- `sensor.preischecker_<suche>` – bester Preis, Attribute: `anzeige` („429,00 € bei geizhals“), `shop`, `url`, `aktion`, `schnaeppchen`, `gruende`, `zielpreis`, `top` …
- `sensor.preischecker_strom_ersparnis`, `sensor.preischecker_internet_ersparnis`

## Benachrichtigung
Einstellungen → **Benachrichtigen an**: eigenes Handy anhaken (jeder für sich, mehrere möglich) → „Speichern + Testnachricht“.

## Ruhezeit
Standard 22:00–07:00: in dieser Zeit gehen keine Meldungen raus (weder Handy noch HA-Glocke). Was nachts anfällt, kommt zum Ende der Ruhezeit gesammelt. Einstellungen → Benachrichtigung.

## Probleme
Keine Treffer? Im Add-on-Log nach „Debug:“ suchen. Screenshots/HTML liegen unter `/data/debug/` im Add-on.
