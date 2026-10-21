# Preis-Checker

## Einrichten
1. Add-on starten, links in der Seitenleiste **Preis-Checker** öffnen.
2. Oben **Einstellungen**: Adresse, Strom-/Internetvertrag, Produkte eintragen → Speichern.
3. **Übersicht → Jetzt prüfen**. Danach automatisch alle 6 Stunden (einstellbar).

## Schnellsuche
Übersicht → Suchbegriff eingeben → nach ca. 30–60 s Preise aller Shops. „Beobachten + Preisalarm“ übernimmt den Artikel in die Liste.

## Andere Personen
Jede Person mit eigenem HA-Konto (auch ohne Admin-Rechte) sieht „Preis-Checker“ in der Seitenleiste – im Browser und in der HA-App.

## Sensoren
Werden automatisch angelegt, keine YAML nötig:
- `sensor.preischecker_<suche>` – bester Preis, Attribute: `anzeige` („429,00 € bei geizhals“), `shop`, `url`, `aktion`, `schnaeppchen`, `gruende`, `zielpreis`, `top` …
- `sensor.preischecker_strom_ersparnis`, `sensor.preischecker_internet_ersparnis`

## Benachrichtigung
Einstellungen → **HA-Benachrichtigungsdienst**, z. B. `notify.mobile_app_<handy>` → „Speichern + Testnachricht“.

## Probleme
Keine Treffer? Im Add-on-Log nach „Debug:“ suchen. Screenshots/HTML liegen unter `/data/debug/` im Add-on.
