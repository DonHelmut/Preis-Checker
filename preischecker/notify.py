from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger(__name__)


def _post(url: str, data: bytes, headers: dict) -> None:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    urllib.request.urlopen(req, timeout=15).read()


def text_fuer(ergebnis: dict) -> str:
    best = ergebnis["angebote"][0]
    akt = ergebnis["aktuell"]
    zeilen = [
        f"{ergebnis['kategorie'].capitalize()}: {best['ersparnis_jahr']:.0f} €/Jahr sparen",
        f"Aktuell: {akt.get('anbieter')} – {akt['kosten_jahr']:.2f} €/Jahr",
        f"Besser: {best['anbieter']} {best.get('tarif') or ''} – {best['kosten_jahr']:.2f} €/Jahr",
    ]
    if akt.get("kuendigen_bis"):
        zeilen.append(f"Kündigen bis: {akt['kuendigen_bis']}")
    return "\n".join(zeilen)


def produkt_melden(cfg: dict, ergebnis: dict, vorher: dict | None) -> bool:
    """Melden, wenn Zielpreis erstmals erreicht oder neuer Tiefstpreis darunter."""
    if not ergebnis.get("ziel_erreicht"):
        return False
    alt = (vorher or {}).get("bester_preis")
    return not (vorher or {}).get("ziel_erreicht") or alt is None or ergebnis["bester_preis"] < alt


def senden_produkt(cfg: dict, ergebnis: dict, vorher: dict | None) -> None:
    if not produkt_melden(cfg, ergebnis, vorher):
        return
    best = ergebnis["angebote"][0]
    text = (f"Zielpreis erreicht: {ergebnis['suche']}\n"
            f"{best['preis']:.2f} € bei {best['shop']} (Ziel {ergebnis['zielpreis']:.2f} €)\n"
            f"{best['name']}\n{best['url']}")
    _verteilen(cfg, text, {"kategorie": "produkt", "suche": ergebnis["suche"], "preis": best["preis"],
                           "shop": best["shop"], "url": best["url"], "name": best["name"]})


def _verteilen(cfg: dict, text: str, payload: dict) -> None:
    n = cfg["benachrichtigung"]
    try:
        if n.get("telegram_bot_token") and n.get("telegram_chat_id"):
            _post(
                f"https://api.telegram.org/bot{n['telegram_bot_token']}/sendMessage",
                json.dumps({"chat_id": n["telegram_chat_id"], "text": text}).encode(),
                {"Content-Type": "application/json"},
            )
        if n.get("ntfy_topic"):
            _post(f"https://ntfy.sh/{n['ntfy_topic']}", text.encode("utf-8"), {"Title": "Preis-Checker"})
        if n.get("webhook_url"):
            _post(n["webhook_url"], json.dumps({"text": text, **payload}).encode(), {"Content-Type": "application/json"})
    except Exception as e:  # Benachrichtigung darf den Lauf nicht abbrechen
        log.error("Benachrichtigung fehlgeschlagen: %s", e)


def senden(cfg: dict, ergebnis: dict) -> None:
    schwelle = cfg["pruefung"].get("benachrichtigen_ab_euro_jahr", 50)
    ersparnis = ergebnis.get("beste_ersparnis_jahr")
    if ersparnis is None or ersparnis < schwelle:
        return
    text = text_fuer(ergebnis)
    _verteilen(cfg, text, {"kategorie": ergebnis["kategorie"], "ersparnis_jahr": ersparnis,
                           "bestes_angebot": {k: ergebnis["angebote"][0].get(k) for k in ("anbieter", "tarif", "kosten_jahr")}})
