# Preis-Checker

Vergleicht die eigenen Strom- und Internetverträge regelmäßig mit aktuellen Check24-Angeboten.
Zeigt, was günstiger ist, und meldet sich (Telegram / ntfy / Home-Assistant-Webhook), wenn sich ein Wechsel lohnt.

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
| `pruefen [strom] [internet]` | Einmal prüfen, Ergebnis ausgeben + speichern |
| `debug [strom] [internet]` | Wie `pruefen`, speichert zusätzlich Screenshot, HTML, erkannte Kacheln unter `data/debug/` |
| `serve` | Weboberfläche (Port 8080) + Scheduler |
| `test-benachrichtigung` | Testnachricht an alle Kanäle |

In Docker: `docker compose exec preischecker python -m preischecker debug strom`

## Wie gerechnet wird

- **Strom**: Verbrauch × Arbeitspreis + 12 × Grundpreis. Bonus nur bei `bonus_einrechnen: true` (gilt nur im 1. Jahr).
- **Internet**: Ø-Monatspreis über die Mindestlaufzeit (Aktionsmonate + reguläre Monate + Anschlussgebühr − Bonus) × 12, verglichen mit dem aktuellen Monatspreis × 12.
- „Kündigen bis“ = Vertragsende − Kündigungsfrist.

## Wenn keine Angebote erkannt werden

Check24 ändert das Layout gelegentlich oder zeigt ein Captcha.
`python -m preischecker debug strom` ausführen und `data/debug/<neuester Ordner>/seite.png` + `kacheln.txt` ansehen.
Parser-Anpassungen in `preischecker/sources/parsing.py`, Formular/Navigation in `preischecker/sources/check24.py`.

## Home Assistant

`webhook_url: http://<ha>:8123/api/webhook/preischecker` setzen. Payload:
`{"text", "kategorie", "ersparnis_jahr", "bestes_angebot": {"anbieter", "tarif", "kosten_jahr"}}`.
Alternativ `GET /api/status` per REST-Sensor abfragen.

## Tests

```bash
pip install pytest && python -m pytest
```
