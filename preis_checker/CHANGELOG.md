# Changelog


## 1.1.9
- Check24 Internet: Hausnummer aus der Vorschlagsliste wählen
- Diagnose: Netzwerk-Anfragen (netz.txt) und JSON-Antworten abrufbar

## 1.1.8
- Check24 Strom: neues Kachel-Format („37,56 Ct./kWh · 18,17 €/Monat“) wird erkannt; Flextarife ignoriert
- Check24: nach dem Absenden bis zu 12 s auf Seitenwechsel/neuen Tab warten, sonst Klick wiederholen

## 1.1.7
- Check24: „Vergleichen“-Button hat Vorrang (vorher wurde z. B. „ohne Router · mit Young Tarifen“ geklickt)
- Ergebnisse in neuem Tab werden ebenfalls ausgelesen

## 1.1.6
- Check24 Strom: Verbrauch mit „Übernehmen“ bestätigen, sonst startete der Vergleich nicht
- Check24 Internet: neues Formular (Adresse im Dialog hinter „Adresse“-Button)
- Nettopreis („723,67 € exkl. MwSt.“) wird gezielt hochgerechnet, nicht der kleinste Betrag der Kachel

## 1.1.5
- Fix Check24 Strom/Internet: offene Ortsauswahl („71404 Korb“) verdeckte den nächsten Button → Timeout
- Klicks bei Formularen mit kürzerem Timeout und zweitem Versuch

## 1.1.4
- Preisverlauf: Uhrzeiten auf der Zeitachse bei kurzen Zeiträumen
- Hinweis, wenn erst seit kurzem gemessen wird (7 T/30 T sehen dann gleich aus)
## 1.1.3
- Fix Check24 Internet: verzögert eingeblendetes Cookie-Banner („geht klar“) blockierte den Vergleichen-Button
- Cookie-Banner allgemein robuster erkannt (wartet kurz, sucht auch Links/Buttons in Consent-Bereichen)

## 1.1.2
- Ruhezeit (Standard 22:00–07:00, in den Einstellungen änderbar): keine Meldungen, weder Handy noch HA-Glocke
- Meldungen aus der Ruhezeit werden zum Ende gesammelt verschickt (abschaltbar, dann verworfen)
- Testnachricht geht immer sofort raus

## 1.1.1
- Fix: Nettopreise für Geschäftskunden („zzgl. MwSt.“, z. B. Conrad) werden mit 19 % MwSt. auf den Endpreis gerechnet; stehen Netto und Brutto da, zählt Brutto
- Neu: `/api/daten/shop-entfernen` löscht falsch gelesene Preise eines Shops und bewertet gespeicherte Ergebnisse neu

## 1.1.0
- Geizhals/idealo: beim günstigsten passenden Treffer wird die Produktseite geöffnet und der tatsächliche Händler ausgelesen – Anzeige z. B. „Alternate (über Geizhals)“
- Händler erscheint in Übersicht, Detailseite, Schnellsuche, HA-Sensor (`haendler`, `anzeige`) und Benachrichtigung
- Datenbank speichert den Händler mit (bestehende Daten werden automatisch übernommen)

## 1.0.6
- Diagnose läuft im Hintergrund (`/api/diagnose` → id, Ergebnis unter `/api/diagnose/<id>`)

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
