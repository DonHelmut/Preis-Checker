# Preis-Checker

- **Verträge**: eigene Strom- und Internetverträge regelmäßig mit aktuellen Check24-Angeboten vergleichen.
- **Produkte**: Suchbegriffe (z. B. „Nintendo Switch 2“, „RX 9070 XT“) bei Geizhals, Alternate, Mindfactory (+ eigene Shops) beobachten, günstigsten Preis finden, Preisalarm bei Zielpreis.

Meldet sich per Telegram / ntfy / Home-Assistant-Webhook, wenn sich ein Wechsel lohnt oder der Zielpreis erreicht ist.

- Check24 hat keine öffentliche API → das Tool öffnet die Webseite per Headless-Chromium (Playwright), füllt das Formular aus und liest die Ergebnis-Kacheln.
- Läuft am besten auf einer privaten VM/LXC (private IP, Datacenter-IPs werden oft geblockt).
- Nur für private Nutzung, wenige Abrufe (Standard: 1× täglich). Automatisierte Abfragen sind laut Check24-AGB nicht vorgesehen.

## Installation (Proxmox-VM mit Docker)

```bash
git clone https://github.com/DonHelmut/Preis-Checker.git
cd Preis-Checker
cp config.example.yaml config.yaml
nano config.yaml          # eigene Vertragsdaten + Adresse eintragen
docker compose up -d --build
```

Weboberfläche: `http://<vm-ip>:8080` → „Jetzt prüfen“.

## Ohne Docker

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
cp config.example.yaml config.yaml && nano config.yaml
python -m preischecker pruefen          # einmal prüfen, Ergebnis im Terminal
python -m preischecker serve            # Weboberfläche + Prüfung alle intervall_stunden
```

## Befehle

| Befehl | Zweck |
|---|---|
| `pruefen [strom] [internet] [produkte]` | Einmal prüfen, Ergebnis ausgeben + speichern |
| `debug [strom] [internet] [produkte]` | Wie `pruefen`, speichert zusätzlich Screenshot, HTML, erkannte Kacheln unter `data/debug/` |
| `serve` | Weboberfläche (Port 8080) + Scheduler |
| `test-benachrichtigung` | Testnachricht an alle Kanäle |

In Docker: `docker compose exec preischecker python -m preischecker debug strom`

## Wie gerechnet wird

- **Strom**: Verbrauch × Arbeitspreis + 12 × Grundpreis. Bonus nur bei `bonus_einrechnen: true` (gilt nur im 1. Jahr).
- **Internet**: Ø-Monatspreis über die Mindestlaufzeit (Aktionsmonate + reguläre Monate + Anschlussgebühr − Bonus) × 12, verglichen mit dem aktuellen Monatspreis × 12.
- „Kündigen bis“ = Vertragsende − Kündigungsfrist.
- **Produkte**: günstigster Treffer über alle Quellen (Preis ohne Versand). Treffer zählt nur, wenn alle Wörter aus `suche` (oder `muss_enthalten`) im Namen stehen, kein Wort aus `darf_nicht_enthalten`, Preis zwischen `min_preis`/`max_preis`. Nicht lieferbare werden bei `nur_lieferbar: true` ausgeblendet.
- **Schnäppchen** (auch ohne Zielpreis), wenn eins zutrifft:
  - bester Preis ≥ `schnaeppchen_prozent` (15 %) unter dem Median der bisherigen Bestpreise (ab 4 Messungen)
  - ein Shop ≥ `markt_prozent` (25 %) unter dem Median der anderen Shops (Preisfehler)
  - Shop-Rabatt (Streichpreis/UVP) ≥ `schnaeppchen_prozent`
- Shop-Aktionen („Deal“, „Angebot“, „statt“, „-20 %“) werden als `aktion` markiert.
- Produkt-Meldung: bei Zielpreis oder Schnäppchen, erneut nur wenn der Preis weiter fällt.

## Weitere Shops

```yaml
produkte:
  eigene_shops:
    caseking: "https://www.caseking.de/search?search={q}"
    cyberport: "https://www.cyberport.de/tools/search-results.html?q={q}"
```
`{q}` = Suchbegriff. URL = Suchergebnisseite des Shops (im Browser einmal suchen, URL kopieren, Suchwort durch `{q}` ersetzen).

## Wenn keine Angebote erkannt werden

Check24 ändert das Layout gelegentlich oder zeigt ein Captcha.
`python -m preischecker debug strom` ausführen und `data/debug/<neuester Ordner>/seite.png` + `kacheln.txt` ansehen.
Parser-Anpassungen in `preischecker/sources/parsing.py`, Formular/Navigation in `preischecker/sources/check24.py`.

## Home Assistant

**Push** (`webhook_url: http://<ha>:8123/api/webhook/preischecker`), Payload enthält `text` + Details. Automation:
```yaml
triggers:
  - trigger: webhook
    webhook_id: preischecker
    allowed_methods: [POST]
    local_only: true
actions:
  - action: notify.notify
    data: {title: Preis-Checker, message: "{{ trigger.json.text }}"}
```

**Sensoren** über `GET /api/status` (`configuration.yaml`):
```yaml
rest:
  - resource: http://<vm-ip>:8080/api/status
    scan_interval: 1800
    sensor:
      - name: RX 9070 XT bester Preis
        unique_id: preischecker_rx9070xt
        value_template: "{{ value_json.produkte['RX 9070 XT'].bester_preis }}"
        unit_of_measurement: "€"
        json_attributes_path: "$.produkte['RX 9070 XT']"
        json_attributes: [anzeige, shop, name, url, aktion, rabatt_prozent, schnaeppchen, gruende,
                          zielpreis, ziel_erreicht, durchschnitt, zeit, top]
      - name: Strom Ersparnis
        value_template: "{{ value_json.strom.beste_ersparnis_jahr | default(0) }}"
        unit_of_measurement: "€"
```
Pro Suche einen Sensor; Schlüssel = `suche` aus der Config.

## Tests

```bash
pip install pytest && python -m pytest
```
