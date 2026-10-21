"""Check24 Strom- und DSL-Vergleich per Headless-Browser.

Check24 hat keine öffentliche API. Es wird die normale Webseite geöffnet,
das Formular wie von Hand ausgefüllt und die Ergebnis-Kacheln ausgelesen.
Ändert Check24 das Layout: `python -m preischecker debug strom|internet`
ausführen und den Ordner unter data/debug/ prüfen.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from ..models import InternetAngebot, StromAngebot
from . import browser as b
from .parsing import parse_internet, parse_strom

log = logging.getLogger(__name__)

STROM_START = "https://www.check24.de/strom/"
STROM_ERGEBNIS = "https://www.check24.de/strom/vergleich/check24/"
DSL_START = "https://www.check24.de/dsl/"


def _strom_cards(page, cfg: dict):
    ort = cfg["standort"]
    kwh = str(cfg["strom"]["verbrauch_kwh"])
    timeout = cfg["browser"].get("timeout_sekunden", 60)

    # 1. Versuch: Ergebnisseite direkt per URL-Parametern
    page.goto(f"{STROM_ERGEBNIS}?{urlencode({'zipcode': ort['plz'], 'totalconsumption': kwh})}", wait_until="domcontentloaded")
    b.accept_cookies(page)
    cards = b.wait_for_cards(page, r"kWh|Arbeitspreis", timeout_s=min(timeout, 25))
    if len(cards) >= 3:
        return page, cards

    # 2. Versuch: Formular ausfüllen
    page.goto(STROM_START, wait_until="domcontentloaded")
    b.accept_cookies(page)
    if b.fill_first(page, ["postleitzahl", "plz", "zipcode"], str(ort["plz"])):
        b.pick_autocomplete(page, str(ort["plz"]))
    if b.fill_first(page, ["verbrauch", "kwh", "consumption"], kwh):
        b.bestaetigen(page)
    page = b.submit(page)
    return page, b.wait_for_cards(page, r"kWh|Arbeitspreis", timeout_s=timeout)


def _dsl_cards(page, cfg: dict):
    ort = cfg["standort"]
    timeout = cfg["browser"].get("timeout_sekunden", 60)
    page.goto(DSL_START, wait_until="domcontentloaded")
    b.accept_cookies(page)
    b.oeffnen(page, r"^\W*adresse")  # Adressfelder liegen in einem Dialog
    if b.fill_first(page, ["postleitzahl", "plz", "zipcode"], str(ort["plz"])):
        b.pick_autocomplete(page, str(ort["plz"]))
    if ort.get("strasse") and b.fill_first(page, ["straße", "strasse", "street"], ort["strasse"]):
        b.pick_autocomplete(page, ort["strasse"][:8])  # Liste kürzt evtl. „…str.“
    if ort.get("hausnummer"):
        b.fill_first(page, ["hausnummer", "hausnr", "nr", "streetnumber", "housenumber"], str(ort["hausnummer"]))
    b.bestaetigen(page)
    page = b.submit(page)
    return page, b.wait_for_cards(page, r"Mbit", timeout_s=timeout)


def _run(cfg: dict, kind: str, debug: bool):
    collect = _strom_cards if kind == "strom" else _dsl_cards
    parse = parse_strom if kind == "strom" else parse_internet
    with b.browser_page(cfg) as page:
        try:
            page, cards = collect(page, cfg)
        except Exception:
            b.dump_debug(page.context.pages[-1], f"check24-{kind}-fehler", [])
            raise
        offers = [o for o in (parse(c["text"], quelle="check24") for c in cards) if o]
        if debug or not offers:
            path = b.dump_debug(page, f"check24-{kind}", cards)
            log.warning("Check24 %s: %d Kacheln, %d Angebote erkannt. Debug: %s", kind, len(cards), len(offers), path)
        return offers


def strom(cfg: dict, debug: bool = False) -> list[StromAngebot]:
    return _run(cfg, "strom", debug)


def internet(cfg: dict, debug: bool = False) -> list[InternetAngebot]:
    return _run(cfg, "internet", debug)
