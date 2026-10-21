from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from . import compare, db, ha, notify
from .models import ProduktAngebot
from .sources import browser, check24, shops

log = logging.getLogger(__name__)
_lock = threading.Lock()

QUELLEN = {
    "strom": (check24.strom, compare.strom),
    "internet": (check24.internet, compare.internet),
}


@dataclass
class Fortschritt:
    """Live-Stand eines Laufs für die Oberfläche."""
    gesamt: int = 0
    fertig: int = 0
    aktiv: bool = False
    phase: str = ""
    laufend: list[str] = field(default_factory=list)
    start: float | None = None
    ende: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def beginnen(self, gesamt: int, phase: str) -> None:
        with self._lock:
            self.gesamt, self.fertig, self.phase = gesamt, 0, phase
            self.aktiv, self.start, self.ende, self.laufend = True, time.time(), None, []

    def schritt_start(self, text: str) -> None:
        with self._lock:
            self.laufend.append(text)

    def schritt_fertig(self, text: str) -> None:
        with self._lock:
            self.fertig += 1
            if text in self.laufend:
                self.laufend.remove(text)

    def beenden(self) -> None:
        with self._lock:
            self.aktiv, self.ende, self.laufend = False, time.time(), []

    def als_dict(self) -> dict:
        with self._lock:
            return {"aktiv": self.aktiv, "gesamt": self.gesamt, "fertig": self.fertig, "phase": self.phase,
                    "laufend": list(self.laufend), "start": self.start, "ende": self.ende,
                    "prozent": round(self.fertig / self.gesamt * 100) if self.gesamt else 0}


FORTSCHRITT = Fortschritt()
NAECHSTE_PRUEFUNG: dict = {"zeit": None}


def sammeln(cfg: dict, auftraege: list[tuple[str, str, str]], fortschritt: Fortschritt,
            debug: bool = False, status_speichern: bool = True) -> tuple[dict, dict]:
    """Shops parallel durchsuchen. auftraege = [(suche, shop, url_vorlage)].

    Liefert ({suche: [ProduktAngebot]}, {suche: [fehlertext]}).
    """
    q: queue.Queue = queue.Queue()
    for a in auftraege:
        q.put(a)
    angebote: dict[str, list[ProduktAngebot]] = {}
    fehler: dict[str, list[str]] = {}
    lock = threading.Lock()
    parallel = max(1, min(int(cfg["produkte"].get("parallel", 3)), len(auftraege) or 1))

    def ein_auftrag(page, suche, shop, url):
        label = f"{shops.shop_name(shop)}: {suche}"
        fortschritt.schritt_start(label)
        t0 = time.time()
        try:
            gefunden = shops.suchen(page, shop, url, suche, cfg, debug)
            ok, fehlertext = True, None
        except Exception as e:
            gefunden, ok, fehlertext = [], False, f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"
            log.warning("%s fehlgeschlagen: %s", label, fehlertext)
        with lock:
            angebote.setdefault(suche, []).extend(gefunden)
            if not ok:
                fehler.setdefault(suche, []).append(f"{shops.shop_name(shop)}: {fehlertext.split(':')[0]}")
        if status_speichern:
            db.shop_status_setzen(shop, ok, len(gefunden), time.time() - t0, fehlertext)
        fortschritt.schritt_fertig(label)

    def arbeiter():
        neustarts = 0
        while not q.empty() and neustarts <= 2:
            try:
                with browser.browser_page(cfg) as page:
                    while True:
                        try:
                            suche, shop, url = q.get_nowait()
                        except queue.Empty:
                            return
                        ein_auftrag(page, suche, shop, url)
                        if page.is_closed():
                            raise RuntimeError("Browser-Tab geschlossen")
            except Exception:
                neustarts += 1
                log.exception("Browser neu gestartet (%d)", neustarts)
        # Rest nach zu vielen Abstürzen als Fehler verbuchen
        while True:
            try:
                suche, shop, _ = q.get_nowait()
            except queue.Empty:
                return
            with lock:
                fehler.setdefault(suche, []).append(f"{shops.shop_name(shop)}: Browser-Absturz")
            fortschritt.schritt_fertig("")

    threads = [threading.Thread(target=arbeiter, daemon=True) for _ in range(parallel)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return angebote, fehler


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
            FORTSCHRITT.beginnen(1, f"{kat.capitalize()}-Tarife bei Check24")
            holen, vergleichen = QUELLEN[kat]
            try:
                ergebnis = vergleichen(cfg, holen(cfg, debug=debug))
                fehler = None if ergebnis["angebote"] else "Keine Angebote erkannt (siehe Diagnose)"
            except Exception as e:
                log.exception("%s fehlgeschlagen", kat)
                ergebnis = vergleichen(cfg, [])
                fehler = f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
            db.speichern(ergebnis, fehler)
            if not fehler:
                notify.senden(cfg, ergebnis)
            ergebnisse.append({**ergebnis, "fehler": fehler})
        ha.sync(cfg)
        return ergebnisse
    finally:
        FORTSCHRITT.beenden()
        _lock.release()


def produkte_pruefen(cfg: dict, debug: bool = False) -> list[dict]:
    liste = cfg["produkte"].get("liste") or []
    auftraege = [(a["suche"], shop, url) for a in liste for shop, url in shops.shops_fuer(cfg, a).items()]
    FORTSCHRITT.beginnen(len(auftraege), "Produktpreise")
    angebote, fehler = sammeln(cfg, auftraege, FORTSCHRITT, debug)
    zeit = datetime.now().isoformat(timespec="seconds")
    ergebnisse = []
    for artikel in liste:
        suche = artikel["suche"]
        kat = f"produkt:{suche}"
        verlauf = [v["bestes_jahr"] for v in db.verlauf(kat, 120) if v["bestes_jahr"] is not None]
        ergebnis = compare.produkt(cfg, artikel, angebote.get(suche, []), verlauf)
        f = list(fehler.get(suche, []))
        if not ergebnis["angebote"]:
            f.append("Keine passenden Angebote")
        vorher = db.letzte(kat)
        db.speichern(ergebnis, "; ".join(f) or None)
        db.preise_speichern(suche, zeit, ergebnis["angebote"])
        notify.senden_produkt(cfg, ergebnis, vorher)
        ergebnisse.append({**ergebnis, "fehler": "; ".join(f) or None})
    return ergebnisse


def schnellsuche(cfg: dict, artikel: dict, fortschritt: Fortschritt | None = None) -> dict:
    """Einmalige Suche ohne Speichern/Benachrichtigen."""
    fortschritt = fortschritt or Fortschritt()
    auftraege = [(artikel["suche"], shop, url) for shop, url in shops.shops_fuer(cfg, artikel).items()]
    fortschritt.beginnen(len(auftraege), "Schnellsuche")
    angebote, fehler = sammeln(cfg, auftraege, fortschritt, status_speichern=False)
    fortschritt.beenden()
    ergebnis = compare.produkt(cfg, artikel, angebote.get(artikel["suche"], []))
    return {**ergebnis, "fehler": "; ".join(fehler.get(artikel["suche"], [])) or None}


def laeuft() -> bool:
    return _lock.locked()
