"""Browser-Arbeitsprozess für parallele Shop-Abfragen.

Die Sync-API von Playwright ist nicht thread-fähig (parallele Tabs in Threads
haben sich gegenseitig umgeleitet). Deshalb läuft jeder parallele Browser in
einem eigenen Prozess, der seinen Browser über mehrere Aufträge offen hält.
"""
from __future__ import annotations

import atexit
import logging
import time

from .models import ProduktAngebot
from .sources import browser, shops

log = logging.getLogger(__name__)
_STAND: dict = {"cm": None, "page": None}


def _schliessen() -> None:
    cm, _STAND["cm"], _STAND["page"] = _STAND["cm"], None, None
    if cm is not None:
        try:
            cm.__exit__(None, None, None)
        except Exception:
            pass


atexit.register(_schliessen)


def _seite(cfg: dict):
    page = _STAND["page"]
    if page is None or page.is_closed():
        _schliessen()
        cm = browser.browser_page(cfg)
        _STAND["page"], _STAND["cm"] = cm.__enter__(), cm
    return _STAND["page"]


def auftrag(cfg: dict, suche: str, shop: str, url: str, debug: bool = False, artikel: dict | None = None
            ) -> tuple[str, str, list[ProduktAngebot], str | None, float]:
    """Einen Shop durchsuchen. Liefert (suche, shop, angebote, fehlertext, dauer).

    Bei Preisvergleichen wird für den günstigsten passenden Treffer der echte Händler nachgeschlagen.
    """
    t0 = time.time()
    try:
        page = _seite(cfg)
        gefunden = shops.suchen(page, shop, url, suche, cfg, debug)
        if shop in shops.VERGLEICHSPORTALE and gefunden:
            shops.haendler_ergaenzen(page, gefunden, artikel or {"suche": suche}, cfg)
        return suche, shop, gefunden, None, time.time() - t0
    except Exception as e:
        _schliessen()  # Browser im Zweifel frisch starten
        text = f"{type(e).__name__}: {str(e).splitlines()[0][:160] if str(e) else ''}"
        log.warning("%s / %s fehlgeschlagen: %s", shop, suche, text)
        return suche, shop, [], text, time.time() - t0
