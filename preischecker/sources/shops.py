"""Produktsuche in deutschen Shops und Preisvergleichen.

Jeder Shop wird wie von Hand im Browser durchsucht, die Ergebnis-Kacheln
werden per Text-Heuristik ausgelesen (keine shop-spezifischen CSS-Klassen).
Weitere Shops per Config: produkte.eigene_shops: {name: "https://shop.de/suche?q={q}"}
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, quote_plus

from ..models import ProduktAngebot
from . import browser as b

log = logging.getLogger(__name__)


class BlockiertError(RuntimeError):
    """Shop zeigt eine Bot-Schutz-Seite (Cloudflare, Captcha …)."""


@dataclass(frozen=True)
class Shop:
    key: str
    name: str
    url: str           # {q} = Suchbegriff (Query-kodiert), {p} = Pfad-kodiert
    gruppen: tuple[str, ...]


SHOP_LISTE = [
    Shop("geizhals", "Geizhals", "https://geizhals.de/?fs={q}&hloc=de", ("vergleich",)),
    Shop("idealo", "idealo", "https://www.idealo.de/preisvergleich/MainSearchProductCategory.html?q={q}", ("vergleich",)),
    Shop("mediamarkt", "MediaMarkt", "https://www.mediamarkt.de/de/search.html?query={q}", ("elektronik",)),
    Shop("saturn", "Saturn", "https://www.saturn.de/de/search.html?query={q}", ("elektronik",)),
    Shop("amazon", "Amazon", "https://www.amazon.de/s?k={q}", ("elektronik", "hardware", "allgemein")),
    Shop("otto", "Otto", "https://www.otto.de/suche/{p}/", ("elektronik", "allgemein")),
    Shop("cyberport", "Cyberport", "https://www.cyberport.de/tools/search-results.html?q={q}", ("elektronik", "hardware")),
    Shop("notebooksbilliger", "notebooksbilliger", "https://www.notebooksbilliger.de/produkte/{p}", ("elektronik", "hardware")),
    Shop("galaxus", "Galaxus", "https://www.galaxus.de/de/search?q={q}", ("elektronik", "hardware", "allgemein")),
    Shop("expert", "expert", "https://www.expert.de/suche?q={q}", ("elektronik",)),
    Shop("euronics", "Euronics", "https://www.euronics.de/search?sSearch={q}", ("elektronik",)),
    Shop("kaufland", "Kaufland", "https://www.kaufland.de/s/?search_value={q}", ("elektronik", "allgemein")),
    Shop("conrad", "Conrad", "https://www.conrad.de/de/search.html?search={q}", ("elektronik", "hardware")),
    Shop("alternate", "Alternate", "https://www.alternate.de/listing.xhtml?q={q}", ("hardware", "elektronik")),
    Shop("mindfactory", "Mindfactory", "https://www.mindfactory.de/search_result.php?search_query={q}", ("hardware",)),
    Shop("caseking", "Caseking", "https://www.caseking.de/search?search={q}", ("hardware",)),
    Shop("proshop", "Proshop", "https://www.proshop.de/?s={q}", ("hardware",)),
]
SHOPS = {s.key: s for s in SHOP_LISTE}

KATEGORIEN = {
    "alle": "Alle Shops",
    "elektronik": "Elektronik (MediaMarkt, Saturn, Amazon …)",
    "hardware": "PC-Hardware (Alternate, Mindfactory, Caseking …)",
    "allgemein": "Allgemein (Amazon, Otto, Kaufland …)",
}
GRUPPEN_NAMEN = {"vergleich": "Preisvergleiche", "elektronik": "Elektronikmärkte",
                 "hardware": "PC-Hardware", "allgemein": "Kaufhäuser"}
STANDARD_AUS = {"conrad", "proshop"}  # standardmäßig aus, per Einstellung zuschaltbar

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


def _token_passt(token: str, name_klein: str, name_norm: str) -> bool:
    t = norm(token)
    if not t:
        return True
    if t.isdigit():  # Zahlen wortgenau: "2" passt nicht auf "V2" oder "2022"
        return re.search(rf"(?<![0-9a-zäöüß]){t}(?![0-9])", name_klein) is not None
    return t in name_norm


def enthaelt_suche(name_: str, woerter: list[str]) -> bool:
    name_klein = name_.lower()
    name_norm = norm(name_)
    phrase = norm("".join(woerter))
    if phrase and phrase in name_norm and not phrase.isdigit():
        # "RX 9070 XT" passt auf "RX9070XT"; Zahl am Ende darf nicht weiterlaufen ("Switch 2" ≠ "Switch 2022")
        idx = name_norm.index(phrase) + len(phrase)
        if not (phrase[-1].isdigit() and idx < len(name_norm) and name_norm[idx].isdigit()):
            return True
    return all(_token_passt(w, name_klein, name_norm) for w in woerter)


def passt(angebot: ProduktAngebot, artikel: dict) -> bool:
    """Relevanzfilter gegen Zubehör & Fehltreffer."""
    woerter = artikel.get("muss_enthalten") or artikel["suche"].split()
    if not enthaelt_suche(angebot.name, woerter):
        return False
    n = norm(angebot.name)
    if any(norm(w) and norm(w) in n for w in artikel.get("darf_nicht_enthalten", [])):
        return False
    if artikel.get("min_preis") and angebot.preis < artikel["min_preis"]:
        return False
    if artikel.get("max_preis") and angebot.preis > artikel["max_preis"]:
        return False
    return True


def suchen(page, shop: str, url_vorlage: str, suche: str, cfg: dict, debug: bool = False) -> list[ProduktAngebot]:
    url = url_vorlage.replace("{p}", quote(suche)).replace("{q}", quote_plus(suche))
    page.goto(url, wait_until="domcontentloaded")
    if not b.schutzseite_abwarten(page):
        b.dump_debug(page, f"{shop}-{norm(suche)[:30]}-schutz", [])
        raise BlockiertError(f"Bot-Schutz: {page.title()[:60]}")
    b.accept_cookies(page)
    cards = b.wait_for_cards(page, r"€|,[-–]", timeout_s=min(cfg["browser"].get("timeout_sekunden", 60), 30),
                             min_len=25, min_cards=2)
    angebote = [a for a in (parse_produkt(c, shop) for c in cards) if a]
    if debug or not angebote:
        pfad = b.dump_debug(page, f"{shop}-{norm(suche)[:30]}", cards)
        log.warning("%s '%s': %d Kacheln, %d Preise erkannt. Debug: %s", shop, suche, len(cards), len(angebote), pfad)
    return angebote


def aktive_shops(cfg: dict) -> dict[str, str]:
    """Alle eingeschalteten Shops: key -> URL-Vorlage."""
    p = cfg["produkte"]
    gewaehlt = p.get("quellen") or [k for k in SHOPS if k not in STANDARD_AUS]
    shops = {k: SHOPS[k].url for k in gewaehlt if k in SHOPS}
    shops.update(p.get("eigene_shops") or {})
    return shops


def shops_fuer(cfg: dict, artikel: dict) -> dict[str, str]:
    """Shops für einen Artikel je nach Kategorie (Preisvergleiche + eigene Shops immer)."""
    kat = artikel.get("kategorie") or "alle"
    out = {}
    for k, url in aktive_shops(cfg).items():
        shop = SHOPS.get(k)
        if kat == "alle" or shop is None or "vergleich" in shop.gruppen or kat in shop.gruppen:
            out[k] = url
    return out


def shop_name(key: str) -> str:
    return SHOPS[key].name if key in SHOPS else key


def alle_shops(cfg: dict) -> dict[str, str]:  # Kompatibilität
    return aktive_shops(cfg)
