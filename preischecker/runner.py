from __future__ import annotations

import logging
import multiprocessing
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime

from . import compare, db, ha, notify, worker
from .models import ProduktAngebot
from .sources import check24, shops

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


FEHLER_NAMEN = {"BlockiertError": "blockiert (Bot-Schutz)", "TimeoutError": "Zeitüberschreitung"}


def fehler_kurz(fehlertext: str) -> str:
    art = fehlertext.split(":")[0]
    return FEHLER_NAMEN.get(art, "nicht erreichbar" if "net::" in fehlertext else art)


def sammeln(cfg: dict, auftraege: list[tuple[str, str, str]], fortschritt: Fortschritt,
            debug: bool = False, status_speichern: bool = True,
            artikel: dict[str, dict] | None = None) -> tuple[dict, dict]:
    """Shops parallel durchsuchen (je paralleler Browser ein Prozess). auftraege = [(suche, shop, url_vorlage)].

    artikel: {suche: artikel} für den Relevanzfilter bei der Händler-Ermittlung in Preisvergleichen.
    Liefert ({suche: [ProduktAngebot]}, {suche: [fehlertext]}).
    """
    artikel = artikel or {}
    angebote: dict[str, list[ProduktAngebot]] = {}
    fehler: dict[str, list[str]] = {}
    parallel = max(1, min(int(cfg["produkte"].get("parallel", 3)), len(auftraege) or 1))
    label = lambda a: f"{shops.shop_name(a[1])}: {a[0]}"  # noqa: E731

    def verbuchen(suche, shop, gefunden, fehlertext, dauer):
        angebote.setdefault(suche, []).extend(gefunden)
        if fehlertext:
            fehler.setdefault(suche, []).append(f"{shops.shop_name(shop)}: {fehler_kurz(fehlertext)}")
        if status_speichern:
            db.shop_status_setzen(shop, fehlertext is None, len(gefunden), dauer, fehlertext)
        fortschritt.schritt_fertig(f"{shops.shop_name(shop)}: {suche}")

    if parallel == 1:
        for a in auftraege:
            fortschritt.schritt_start(label(a))
            verbuchen(*worker.auftrag(cfg, *a, debug, artikel.get(a[0])))
        worker._schliessen()
        return angebote, fehler

    offen = list(auftraege)
    with ProcessPoolExecutor(max_workers=parallel, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = {pool.submit(worker.auftrag, cfg, *a, debug, artikel.get(a[0])): a for a in auftraege}
        for a in offen[:parallel]:
            fortschritt.schritt_start(label(a))
        for fut in as_completed(futures):
            a = futures[fut]
            try:
                verbuchen(*fut.result())
            except Exception as e:  # z. B. abgestürzter Arbeitsprozess
                log.warning("%s: Arbeitsprozess fehlgeschlagen: %s", label(a), e)
                verbuchen(a[0], a[1], [], f"{type(e).__name__}: Arbeitsprozess", 0.0)
            offen.remove(a)
            naechste = offen[parallel - 1] if len(offen) >= parallel else None
            if naechste:
                fortschritt.schritt_start(label(naechste))
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


def _ohne_gesperrte(cfg: dict, auftraege: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Gesperrte Shops eine Weile auslassen, statt sie immer wieder anzufragen.

    Wer in den letzten Tagen gesperrt hat, wird danach nur noch selten abgefragt (Standard: 1× täglich).
    """
    p = cfg["produkte"]
    pause = float(p.get("sperre_pause_stunden", 24))
    gesperrt = db.gesperrte_shops(pause)
    selten = db.schonend_zurueckhalten(float(p.get("empfindlich_abstand_stunden", 20)) if pause > 0 else 0)
    if gesperrt or selten:
        log.info("Pausiert wegen Bot-Sperre: %s", ", ".join(sorted(set(gesperrt) | set(selten))))
    return [a for a in auftraege if a[1] not in gesperrt and a[1] not in selten]


def produkte_pruefen(cfg: dict, debug: bool = False) -> list[dict]:
    liste = cfg["produkte"].get("liste") or []
    auftraege = _ohne_gesperrte(cfg, [(a["suche"], shop, url) for a in liste for shop, url in shops.shops_fuer(cfg, a).items()])
    FORTSCHRITT.beginnen(len(auftraege), "Produktpreise")
    angebote, fehler = sammeln(cfg, auftraege, FORTSCHRITT, debug, artikel={a["suche"]: a for a in liste})
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
        notify.senden_verdacht(cfg, ergebnis, vorher)
        ergebnisse.append({**ergebnis, "fehler": "; ".join(f) or None})
    return ergebnisse


def schnellsuche(cfg: dict, artikel: dict, fortschritt: Fortschritt | None = None) -> dict:
    """Einmalige Suche ohne Speichern/Benachrichtigen."""
    fortschritt = fortschritt or Fortschritt()
    auftraege = _ohne_gesperrte(cfg, [(artikel["suche"], shop, url) for shop, url in shops.shops_fuer(cfg, artikel).items()])
    fortschritt.beginnen(len(auftraege), "Schnellsuche")
    angebote, fehler = sammeln(cfg, auftraege, fortschritt, status_speichern=False,
                               artikel={artikel["suche"]: artikel})
    fortschritt.beenden()
    ergebnis = compare.produkt(cfg, artikel, angebote.get(artikel["suche"], []))
    return {**ergebnis, "fehler": "; ".join(fehler.get(artikel["suche"], [])) or None}


def laeuft() -> bool:
    return _lock.locked()
