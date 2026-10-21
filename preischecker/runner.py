from __future__ import annotations

import logging
import threading

from . import compare, db, ha, notify
from .sources import browser, check24, shops

log = logging.getLogger(__name__)
_lock = threading.Lock()

QUELLEN = {
    "strom": (check24.strom, compare.strom),
    "internet": (check24.internet, compare.internet),
}


def pruefen(cfg: dict, kategorien: list[str] | None = None, debug: bool = False) -> list[dict]:
    if not _lock.acquire(blocking=False):
        log.info("Prüfung läuft bereits")
        return []
    try:
        ergebnisse = []
        kategorien = kategorien or [*QUELLEN, "produkte"]
        if "produkte" in kategorien and cfg["produkte"].get("aktiv"):
            try:
                ergebnisse += produkte_pruefen(cfg, debug)
            except Exception:
                log.exception("Produktprüfung fehlgeschlagen")
        for kat in kategorien:
            if kat == "produkte" or not cfg[kat].get("aktiv"):
                continue
            holen, vergleichen = QUELLEN[kat]
            try:
                ergebnis = vergleichen(cfg, holen(cfg, debug=debug))
                fehler = None if ergebnis["angebote"] else "Keine Angebote erkannt (siehe data/debug/)"
            except Exception as e:
                log.exception("%s fehlgeschlagen", kat)
                ergebnis = vergleichen(cfg, [])
                fehler = f"{type(e).__name__}: {e}"
            db.speichern(ergebnis, fehler)
            if not fehler:
                notify.senden(cfg, ergebnis)
            ergebnisse.append({**ergebnis, "fehler": fehler})
        ha.sync(cfg)
        return ergebnisse
    finally:
        _lock.release()


def produkte_pruefen(cfg: dict, debug: bool = False) -> list[dict]:
    ergebnisse = []
    quellen = shops.alle_shops(cfg)
    with browser.browser_page(cfg) as page:
        for artikel in cfg["produkte"].get("liste") or []:
            angebote, fehler = [], []
            for shop, url in quellen.items():
                try:
                    angebote += shops.suchen(page, shop, url, artikel["suche"], cfg, debug)
                except Exception as e:
                    log.warning("%s / %s fehlgeschlagen: %s", shop, artikel["suche"], e)
                    fehler.append(f"{shop}: {type(e).__name__}")
            kat = f"produkt:{artikel['suche']}"
            verlauf = [v["bestes_jahr"] for v in db.verlauf(kat, 120) if v["bestes_jahr"] is not None]
            ergebnis = compare.produkt(cfg, artikel, angebote, verlauf)
            if not ergebnis["angebote"]:
                fehler.append("Keine passenden Angebote")
            vorher = db.letzte(ergebnis["kategorie"])
            db.speichern(ergebnis, "; ".join(fehler) or None)
            notify.senden_produkt(cfg, ergebnis, vorher)
            ergebnisse.append({**ergebnis, "fehler": "; ".join(fehler) or None})
    return ergebnisse


def schnellsuche(cfg: dict, artikel: dict) -> dict:
    """Einmalige Suche ohne Speichern/Benachrichtigen."""
    angebote, fehler = [], []
    with browser.browser_page(cfg) as page:
        for shop, url in shops.alle_shops(cfg).items():
            try:
                angebote += shops.suchen(page, shop, url, artikel["suche"], cfg)
            except Exception as e:
                log.warning("Schnellsuche %s / %s: %s", shop, artikel["suche"], e)
                fehler.append(f"{shop}: {type(e).__name__}")
    ergebnis = compare.produkt(cfg, artikel, angebote)
    return {**ergebnis, "fehler": "; ".join(fehler) or None}


def laeuft() -> bool:
    return _lock.locked()
