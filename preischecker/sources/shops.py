"""Produktsuche in deutschen Shops / Preisvergleichen.

Geizhals listet fast alle deutschen Händler, Alternate und Mindfactory
werden zusätzlich direkt durchsucht. Weitere Shops per Config:
produkte.eigene_shops: {name: "https://shop.de/suche?q={q}"}
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from ..models import ProduktAngebot
from . import browser as b

log = logging.getLogger(__name__)

SHOPS = {
    "geizhals": "https://geizhals.de/?fs={q}&hloc=de",
    "alternate": "https://www.alternate.de/listing.xhtml?q={q}",
    "mindfactory": "https://www.mindfactory.de/search_result.php?search_query={q}",
}

_BETRAG = r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2})|,[-–])"
_PREIS = re.compile(rf"€\s*{_BETRAG}|{_BETRAG}\s*€?")
_KEIN_PREIS_DAVOR = re.compile(r"(versand|uvp|statt|spar|ersparnis|rabatt|cashback|gutschein|pfand|zzgl)\W*$", re.I)
_KEIN_PREIS_DANACH = re.compile(r"^\W*(mtl|monat|/\s*m|rate|finanz)", re.I)
_ALTPREIS_DAVOR = re.compile(r"(uvp|statt|vorher|bisher|ursprünglich)\W*$", re.I)
_AKTION = re.compile(r"\bangebot\b|\bdeal\b|\bsale\b|reduziert|aktion|black ?friday|cyber|tagesangebot|-\s?\d{1,2}\s?%", re.I)
_LIEFERBAR = re.compile(r"lagernd|auf lager|sofort (lieferbar|verfügbar)|versandfertig|lieferbar in", re.I)
_NICHT_LIEFERBAR = re.compile(r"nicht (lieferbar|verfügbar)|ausverkauft|vergriffen|derzeit nicht|kein liefertermin", re.I)


def norm(s: str) -> str:
    return re.sub(r"[^0-9a-zäöüß]", "", s.lower())


def _betraege(text: str):
    for m in _PREIS.finditer(text):
        g = m.groups()
        euro, cent = (g[0], g[1]) if g[0] else (g[2], g[3])
        wert = int(euro.replace(".", "")) + int(cent or 0) / 100
        if wert >= 1:
            yield wert, text[max(0, m.start() - 30):m.start()], text[m.end():m.end() + 12]


def preis(text: str) -> float | None:
    werte = [w for w, davor, danach in _betraege(text)
             if not _KEIN_PREIS_DAVOR.search(davor) and not _KEIN_PREIS_DANACH.search(danach)]
    return min(werte) if werte else None


def alter_preis(text: str) -> float | None:
    """Streichpreis / UVP, falls angezeigt."""
    werte = [w for w, davor, _ in _betraege(text) if _ALTPREIS_DAVOR.search(davor)]
    return max(werte) if werte else None


def name(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    kandidaten = [l for l in lines if "€" not in l and re.search(r"[A-Za-z]{2}", l) and len(l) <= 200]
    return max(kandidaten, key=len) if kandidaten else (lines[0] if lines else "?")


def parse_produkt(card: dict, shop: str) -> ProduktAngebot | None:
    text = card["text"]
    p = preis(text)
    if p is None:
        return None
    lieferbar = False if _NICHT_LIEFERBAR.search(text) else (True if _LIEFERBAR.search(text) else None)
    alt = alter_preis(text)
    if alt is not None and alt <= p:
        alt = None
    return ProduktAngebot(name=name(text), preis=p, shop=shop, url=card.get("href", ""),
                          lieferbar=lieferbar, alter_preis=alt,
                          aktion=bool(alt or _AKTION.search(text)), rohtext=text[:1500])


def passt(angebot: ProduktAngebot, artikel: dict) -> bool:
    """Relevanzfilter gegen Zubehör & Fehltreffer."""
    n = norm(angebot.name)
    woerter = artikel.get("muss_enthalten") or artikel["suche"].split()
    if not all(norm(w) in n for w in woerter):
        return False
    if any(norm(w) in n for w in artikel.get("darf_nicht_enthalten", [])):
        return False
    if artikel.get("min_preis") and angebot.preis < artikel["min_preis"]:
        return False
    if artikel.get("max_preis") and angebot.preis > artikel["max_preis"]:
        return False
    return True


def suchen(page, shop: str, url_vorlage: str, suche: str, cfg: dict, debug: bool = False) -> list[ProduktAngebot]:
    page.goto(url_vorlage.format(q=quote_plus(suche)))
    b.accept_cookies(page)
    cards = b.wait_for_cards(page, r"€|,[-–]", timeout_s=min(cfg["browser"].get("timeout_sekunden", 60), 30),
                             min_len=25, min_cards=2)
    angebote = [a for a in (parse_produkt(c, shop) for c in cards) if a]
    if debug or not angebote:
        pfad = b.dump_debug(page, f"{shop}-{norm(suche)[:30]}", cards)
        log.warning("%s '%s': %d Kacheln, %d Preise erkannt. Debug: %s", shop, suche, len(cards), len(angebote), pfad)
    return angebote


def alle_shops(cfg: dict) -> dict[str, str]:
    p = cfg["produkte"]
    shops = {k: v for k, v in SHOPS.items() if k in p.get("quellen", list(SHOPS))}
    shops.update(p.get("eigene_shops") or {})
    return shops
