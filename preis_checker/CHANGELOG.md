# Changelog

## 1.0.5
- Captcha-Seiten (z. B. Cloudflare Turnstile bei Mindfactory) werden als Sperre erkannt; Captchas werden nicht gelöst
- Gesperrte Shops pausieren 12 Stunden (`produkte.sperre_pause_stunden`), Shop-Status zeigt „pausiert bis …“

## 1.0.4
- Galaxus-Preisformat („449.–“) wird erkannt
- Bot-Schutz: zweiter Anlauf nach Neuladen, „Human Verification“ (Euronics) erkannt
- Diagnose: optionale Such-URL zum Ausprobieren, Seitentitel und erkannte Kacheln im Ergebnis

## 1.0.3
- Sets/Bundles („… + Era 100“, „Set“, „Bundle“) werden standardmäßig aussortiert (pro Artikel `bundles: true` erlaubt sie)
- Diagnose-Schnittstelle `/api/diagnose?shop=…&q=…`: zeigt jedes erkannte Angebot mit Grund fürs Aussortieren

## 1.0.2
- Volles Chromium im neuen Headless-Modus (Playwright 1.56), passender User-Agent ohne „HeadlessChrome“ → weniger Bot-Sperren
- Wartet auf Cloudflare-Zwischenseiten, gesperrte Shops heißen jetzt „Blockiert (Bot-Schutz)“

## 1.0.1
- Fix: parallele Shop-Abfragen liefen in Threads und haben sich gegenseitig umgeleitet – jetzt eigener Prozess je Browser

## 1.0.0
- Komplett neue Oberfläche: Produktkarten mit Mini-Verlauf, Detailseite mit interaktivem Preisdiagramm (Zeitraum, Shops ein-/ausblenden), Shop-Vergleich, Dunkelmodus
- Preisverlauf: jeder Shop-Preis wird bei jeder Prüfung gespeichert
- Statistik: Tiefst-/Höchstpreis, Ø 30 Tage, Schwankung, Trend, Kaufempfehlung
- 17 Shops: Geizhals, idealo, MediaMarkt, Saturn, Amazon, Otto, Cyberport, notebooksbilliger, Galaxus, expert, Euronics, Kaufland, Conrad, Alternate, Mindfactory, Caseking, Proshop
- Kategorie je Artikel (Elektronik, PC-Hardware, Allgemein, Alle)
- Parallele Abfrage mit Live-Fortschritt, Shop-Status-Übersicht
- Genauere Treffer: „Switch 2“ passt nicht mehr auf „Switch V2 2022“
- Fix: Check24-Verbrauchsfeld hinter Button, Geizhals-Zeitüberschreitung

## 0.3.0
- Benachrichtigung per Checkbox: jedes Handy aus HA einzeln anhaken (mehrere möglich)

## 0.2.0
- Schnellsuche: beliebiges Produkt sofort suchen, mit einem Klick beobachten
- Panel auch für Nicht-Admin-Benutzer sichtbar
- Fix: Anzeige des Update-Status

## 0.1.0
- Erste Version: Strom/Internet über Check24, Produkte über Geizhals/Alternate/Mindfactory
- Schnäppchen-Alarm, Einstellungsseite, automatische HA-Sensoren
