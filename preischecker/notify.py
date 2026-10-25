from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime
from datetime import time as dtime

from . import db, ha
from .sources.shops import anbieter

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
    """Melden bei Zielpreis/Schnäppchen – erneut nur, wenn der Preis weiter fällt."""
    if not (ergebnis.get("ziel_erreicht") or ergebnis.get("schnaeppchen")):
        return False
    vorher = vorher or {}
    schon_gemeldet = vorher.get("ziel_erreicht") or vorher.get("schnaeppchen")
    alt = vorher.get("bester_preis")
    return not schon_gemeldet or alt is None or ergebnis["bester_preis"] < alt


def produkt_text(ergebnis: dict) -> str:
    best = ergebnis["angebote"][0]
    kopf = "Schnäppchen" if ergebnis.get("schnaeppchen") else "Zielpreis erreicht"
    zeilen = [f"{kopf}: {ergebnis['suche']}", f"{best['preis']:.2f} € bei {anbieter(best)}"]
    if ergebnis.get("zielpreis"):
        zeilen[-1] += f" (Ziel {ergebnis['zielpreis']:.2f} €)"
    zeilen += ergebnis.get("gruende") or []
    zeilen += [best["name"], best["url"]]
    return "\n".join(z for z in zeilen if z)


def senden_produkt(cfg: dict, ergebnis: dict, vorher: dict | None) -> None:
    if not produkt_melden(cfg, ergebnis, vorher):
        return
    best = ergebnis["angebote"][0]
    _verteilen(cfg, produkt_text(ergebnis), {
        "kategorie": "produkt", "suche": ergebnis["suche"], "preis": best["preis"], "shop": best["shop"],
        "haendler": best.get("haendler"), "anbieter": anbieter(best),
        "url": best["url"], "name": best["name"], "schnaeppchen": ergebnis.get("schnaeppchen", False),
        "ziel_erreicht": ergebnis.get("ziel_erreicht", False), "gruende": ergebnis.get("gruende") or []})


def verdacht_neu(ergebnis: dict, vorher: dict | None) -> list[dict]:
    """Verdächtig billige Angebote, die beim letzten Lauf noch nicht (so billig) da waren."""
    alt = {(v["shop"], v["name"]): v["preis"] for v in (vorher or {}).get("verdacht") or []}
    return [v for v in ergebnis.get("verdacht") or []
            if (v["shop"], v["name"]) not in alt or v["preis"] < alt[(v["shop"], v["name"])]]


def senden_verdacht(cfg: dict, ergebnis: dict, vorher: dict | None) -> None:
    neu = verdacht_neu(ergebnis, vorher)
    if not neu:
        return
    v = neu[0]
    normal = f" (sonst ab {ergebnis['bester_preis']:.2f} €)" if ergebnis.get("bester_preis") else ""
    text = "\n".join([f"Möglicher Preisfehler: {ergebnis['suche']}",
                      f"{v['preis']:.2f} € bei {anbieter(v)}{normal}",
                      "Bitte prüfen – kann auch ein Fake-Händler oder falsches Produkt sein.",
                      v["name"], v.get("url") or ""])
    _verteilen(cfg, text.strip(), {"kategorie": "preisfehler", "suche": ergebnis["suche"], "preis": v["preis"],
                                   "shop": v["shop"], "anbieter": anbieter(v), "url": v.get("url"), "name": v["name"]})


def ha_dienste(n: dict) -> list[str]:
    dienste = list(n.get("ha_dienste") or [])
    if n.get("ha_dienst") and n["ha_dienst"] not in dienste:  # alte Einzel-Einstellung
        dienste.append(n["ha_dienst"])
    return dienste


def in_ruhezeit(n: dict, jetzt: datetime | None = None) -> bool:
    """Ruhezeit (z. B. 22:00–07:00, auch über Mitternacht) aus den Einstellungen."""
    if not n.get("ruhezeit") or not n.get("ruhe_von") or not n.get("ruhe_bis"):
        return False
    try:
        von, bis = dtime.fromisoformat(str(n["ruhe_von"])), dtime.fromisoformat(str(n["ruhe_bis"]))
    except ValueError:
        return False
    t = (jetzt or datetime.now()).time()
    return von <= t < bis if von < bis else (t >= von or t < bis)


def _verteilen(cfg: dict, text: str, payload: dict) -> None:
    """In der Ruhezeit geht nichts raus (auch nicht die HA-Glocke); Meldungen werden gemerkt und danach nachgeholt."""
    n = cfg["benachrichtigung"]
    if not in_ruhezeit(n):
        _laut_senden(cfg, text, payload)
    elif n.get("ruhe_nachholen", True):
        db.nachricht_merken(text, payload)


def nachholen(cfg: dict) -> int:
    """Nach der Ruhezeit gemerkte Meldungen gesammelt an alle Kanäle schicken."""
    n = cfg["benachrichtigung"]
    if in_ruhezeit(n):
        return 0
    gemerkt = db.nachrichten_abholen()
    if not gemerkt:
        return 0
    if len(gemerkt) == 1:
        text = gemerkt[0]["text"]
    else:
        text = f"Preis-Checker – {len(gemerkt)} Meldungen aus der Ruhezeit:\n\n" + "\n\n".join(m["text"] for m in gemerkt)
    _laut_senden(cfg, text, {"kategorie": "nachgeholt", "anzahl": len(gemerkt)})
    return len(gemerkt)


def _laut_senden(cfg: dict, text: str, payload: dict) -> None:
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
        if ha.aktiv():
            for dienst in ha_dienste(n):
                try:
                    ha.benachrichtigen(dienst, text)
                except Exception as e:
                    log.error("HA-Dienst %s fehlgeschlagen: %s", dienst, e)
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


def test(cfg: dict) -> None:
    """Testnachricht geht immer sofort raus, auch in der Ruhezeit."""
    _laut_senden(cfg, "Preis-Checker: Testnachricht – Benachrichtigung funktioniert.", {"kategorie": "test"})
