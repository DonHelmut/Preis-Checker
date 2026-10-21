from __future__ import annotations

import logging
import threading

from . import compare, db, notify
from .sources import check24

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
        for kat in kategorien or list(QUELLEN):
            if not cfg[kat].get("aktiv"):
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
        return ergebnisse
    finally:
        _lock.release()


def laeuft() -> bool:
    return _lock.locked()
