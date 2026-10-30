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

_BETRAG = r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2})|[,.][-–])"  # 449,90 · 449,– · 449.– (Galaxus)
_PREIS = re.compile(rf"€\s*{_BETRAG}|{_BETRAG}\s*€?")
_KEIN_PREIS_DAVOR = re.compile(r"(versand\w*|uvp|statt|spar|ersparnis|rabatt|cashback|gutschein|pfand|zzgl)"
                               r"(\W+(ab|von|nur|für|fuer))?\W*$", re.I)  # auch „Versand ab € 4,99“
_KEIN_PREIS_DANACH = re.compile(r"^[ \t€*]*(%|prozent|mtl\b|monat|/\s*m|x\s*\d)", re.I)  # nur dieselbe Zeile
# Finanzierung: Zinssatz, Raten, Mindestrate, Gesamtbetrag sind keine Kaufpreise (MediaMarkt/Saturn)
# Marktplatz-/Gebrauchthinweise („Zusätzlich neue und refurbished Angebote ab 407,99 €“) sind nicht der Shoppreis
_NEBENANGEBOT = re.compile(r"(refurbished|gebraucht|generalüberholt|b-ware|weitere angebote|marktplatz|"
                           r"angebote ab|anderen? (händler|anbieter))[^\n€]{0,30}$", re.I)
_FINANZIERUNG = re.compile(r"(zins\w*|\brate[n]?|mindestrate|finanzierung\w*|gesamtbetrag|"
                           r"p\.\s?a\.|mind\.)[^\n€]{0,25}$", re.I)
_ALTPREIS_DAVOR = re.compile(r"(uvp|statt|vorher|bisher|ursprünglich)\W*$", re.I)
_AKTION = re.compile(r"\bangebot\b|\bdeal\b|\bsale\b|reduziert|aktion|black ?friday|cyber|tagesangebot|-\s?\d{1,2}\s?%", re.I)
_LIEFERBAR = re.compile(r"lagernd|auf lager|sofort (lieferbar|verfügbar)|versandfertig|lieferbar in", re.I)
_NICHT_LIEFERBAR = re.compile(r"nicht (lieferbar|verfügbar)|ausverkauft|vergriffen|derzeit nicht|kein liefertermin", re.I)


def norm(s: str) -> str:
    return re.sub(r"[^0-9a-zäöüß]", "", s.lower())


_NETTO = re.compile(r"(zzgl|exkl|excl|ohne)\.?\s*(gesetzl\.?\s*)?(mwst|ust|vat|mehrwertsteuer)|\bnetto\b", re.I)
_BRUTTO = re.compile(r"(inkl|incl)\.?\s*(gesetzl\.?\s*)?(mwst|ust|vat|mehrwertsteuer)|\bbrutto\b", re.I)
MWST = 1.19


def _betraege(text: str):
    for m in _PREIS.finditer(text):
        g = m.groups()
        euro, cent = (g[0], g[1]) if g[0] else (g[2], g[3])
        wert = int(euro.replace(".", "")) + int(cent or 0) / 100
        if wert >= 1:
            yield wert, text[max(0, m.start() - 30):m.start()], text[m.end():m.end() + 12], text[m.end():m.end() + 60]


def preis(text: str) -> float | None:
    """Endpreis für Privatkunden. Nettopreise (Geschäftskunden, „zzgl. MwSt.“) werden mit 19 % hochgerechnet."""
    kandidaten = [(w, umfeld) for w, davor, danach, umfeld in _betraege(text)
                  if not _KEIN_PREIS_DAVOR.search(davor) and not _KEIN_PREIS_DANACH.search(danach)
                  and not _FINANZIERUNG.search(davor) and not _NEBENANGEBOT.search(davor)]
    if not kandidaten:
        return None
    if not _NETTO.search(text):
        return min(w for w, _ in kandidaten)
    if _BRUTTO.search(text):  # Netto und Brutto angegeben → Bruttopreis nehmen
        brutto = [w for w, umfeld in kandidaten if _BRUTTO.search(umfeld) and not _NETTO.search(umfeld[:25])]
        if brutto:
            return min(brutto)
        netto = [w for w, umfeld in kandidaten if _NETTO.search(umfeld)]
        rest = [w for w, _ in kandidaten if w not in netto]
        if rest:
            return min(rest)
    # „723,67 € exkl. MwSt.“: genau dieser Nettopreis zählt, nicht ein kleinerer Betrag daneben (Zubehör im Bundle o. Ä.)
    direkt = [w for w, umfeld in kandidaten if _NETTO.search(umfeld[:25])]
    return round(min(direkt or [w for w, _ in kandidaten]) * MWST, 2)


def alter_preis(text: str) -> float | None:
    """Streichpreis / UVP, falls angezeigt."""
    werte = [w for w, davor, *_ in _betraege(text) if _ALTPREIS_DAVOR.search(davor)]
    return max(werte) if werte else None


def name(text: str, suche: str | None = None) -> str:
    """Produktname aus dem Kacheltext.

    Bevorzugt die Zeile mit den Suchwörtern – sonst gewinnt bei Preisvergleichen die lange Technik-Zeile
    („Soundbar ohne Subwoofer, 3.0, WLAN …“) gegen den eigentlichen Titel („Sonos Beam (Gen.2)“).
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    kandidaten = [l for l in lines if "€" not in l and re.search(r"[A-Za-z]{2}", l) and len(l) <= 200]
    if suche:
        # Zeile, die nur den Suchbegriff wiederholt (Brotkrumen/„Ergebnisse für …“), ist kein Produktname
        mit_suche = [l for l in kandidaten if enthaelt_suche(l, suche.split()) and l.lower() != suche.strip().lower()]
        if mit_suche:
            return max(mit_suche, key=len)
    return max(kandidaten, key=len) if kandidaten else (lines[0] if lines else "?")


def parse_produkt(card: dict, shop: str, suche: str | None = None) -> ProduktAngebot | None:
    text = card["text"]
    p = preis(text)
    if p is None:
        return None
    lieferbar = False if _NICHT_LIEFERBAR.search(text) else (True if _LIEFERBAR.search(text) else None)
    alt = alter_preis(text)
    if alt is not None and alt <= p:
        alt = None
    return ProduktAngebot(name=name(text, suche), preis=p, shop=shop, url=card.get("href", ""),
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


def ablehnungsgrund(angebot: ProduktAngebot, artikel: dict) -> str | None:
    """None = Treffer, sonst warum aussortiert (für Filter und Diagnose)."""
    woerter = artikel.get("muss_enthalten") or artikel["suche"].split()
    if not enthaelt_suche(angebot.name, woerter):
        return "Suchwörter fehlen"
    n = norm(angebot.name)
    for w in artikel.get("darf_nicht_enthalten", []):
        if norm(w) and norm(w) in n:
            return f"enthält „{w}“"
    if not artikel.get("bundles") and "+" not in artikel["suche"] and re.search(r"\s\+\s|\bset\b|\bbundle\b", angebot.name, re.I):
        return "Set/Bundle"
    if artikel.get("min_preis") and angebot.preis < artikel["min_preis"]:
        return "unter Mindestpreis"
    if artikel.get("max_preis") and angebot.preis > artikel["max_preis"]:
        return "über Höchstpreis"
    return None


def passt(angebot: ProduktAngebot, artikel: dict) -> bool:
    """Relevanzfilter gegen Zubehör & Fehltreffer."""
    return ablehnungsgrund(angebot, artikel) is None


def suchen(page, shop: str, url_vorlage: str, suche: str, cfg: dict, debug: bool = False) -> list[ProduktAngebot]:
    url = url_vorlage.replace("{p}", quote(suche)).replace("{q}", quote_plus(suche))
    page.goto(url, wait_until="domcontentloaded")
    if not b.schutzseite_abwarten(page):
        page.reload(wait_until="domcontentloaded")  # Cloudflare lässt beim 2. Anlauf oft durch
    if not b.schutzseite_abwarten(page):
        b.dump_debug(page, f"{shop}-{norm(suche)[:30]}-schutz", [])
        raise BlockiertError(f"Bot-Schutz: {page.title()[:60]}")
    b.accept_cookies(page)
    # Kacheln müssen ein Suchwort enthalten – sonst gewinnen z. B. Finanzierungs-Fußnoten mit „€“ (MediaMarkt)
    woerter = [re.escape(w) for w in suche.split() if len(w) > 2] or [r"€|,[-–]"]
    cards = b.wait_for_cards(page, "|".join(woerter), timeout_s=min(cfg["browser"].get("timeout_sekunden", 60), 30),
                             min_len=25, min_cards=2)
    if len(cards) < 2:
        cards = page.evaluate(b.FIND_CARDS_JS, {"keyword": r"€|,[-–]", "minLen": 25})
    angebote = [a for a in (parse_produkt(c, shop, suche) for c in cards) if a]
    if debug or not angebote:
        pfad = b.dump_debug(page, f"{shop}-{norm(suche)[:30]}", cards)
        log.warning("%s '%s': %d Kacheln, %d Preise erkannt. Debug: %s", shop, suche, len(cards), len(angebote), pfad)
    return angebote


VERGLEICHSPORTALE = {"geizhals", "idealo"}

# Händler, die auf Preisvergleichs-Produktseiten auftauchen: Erkennungsmuster -> Anzeigename
HAENDLER = [
    (r"amazon", "Amazon"), (r"media\s?markt", "MediaMarkt"), (r"saturn", "Saturn"), (r"\botto\b", "Otto"),
    (r"alternate", "Alternate"), (r"mindfactory", "Mindfactory"), (r"caseking", "Caseking"),
    (r"cyberport", "Cyberport"), (r"notebooksbilliger|\bnbb\b", "notebooksbilliger"), (r"galaxus", "Galaxus"),
    (r"proshop", "Proshop"), (r"computer\s?universe", "computeruniverse"), (r"jacob", "Jacob"),
    (r"\barlt\b", "ARLT"), (r"kaufland", "Kaufland"), (r"\bexpert\b", "expert"), (r"euronics", "Euronics"),
    (r"conrad", "Conrad"), (r"\bebay\b", "eBay"), (r"\blidl\b", "Lidl"), (r"coolblue", "Coolblue"),
    (r"\bbaur\b", "BAUR"), (r"\bquelle\b", "Quelle"), (r"\btink\b", "tink"), (r"hardwarecamp", "Hardwarecamp24"),
    (r"\bbora\b", "Bora Computer"), (r"\bcsv\b|csv-direct", "CSV-Direct"), (r"\bluxnote\b", "Luxnote"),
    (r"\bdeltatecc\b", "Deltatecc"), (r"\bkmcomputer|km-computer", "KM Computer"), (r"\bhifi\.de|hifi-regler", "HiFi"),
    (r"\bteufel\b", "Teufel"), (r"\bsonos\.com|\bsonos store", "Sonos"), (r"\bapple\.com|apple store", "Apple"),
    (r"\bgamestop\b", "GameStop"), (r"\bmüller\b|mueller\.de", "Müller"), (r"\bnintendo store|my nintendo", "Nintendo"),
]
_HAENDLER_RX = [(re.compile(m, re.I), n) for m, n in HAENDLER]
_DOMAIN = re.compile(r"\b([a-z0-9][a-z0-9-]{1,40})\.(de|com|at|eu|net|shop)\b", re.I)


def haendler_aus_karte(card: dict) -> str | None:
    """Händlername aus einer Angebotszeile eines Preisvergleichs (Text oder Logo-Alt-Text)."""
    teile = [*(card.get("bilder") or []), card.get("text") or ""]
    for teil in teile:
        treffer = [(m.start(), n) for rx, n in _HAENDLER_RX for m in [rx.search(teil)] if m]
        if treffer:
            return min(treffer)[1]
    for teil in teile:  # unbekannter Händler: Domain wie "foo-shop.de"
        m = _DOMAIN.search(teil)
        if m and m.group(1).lower() not in VERGLEICHSPORTALE:
            return m.group(0)
    return None


def haendler_ermitteln(page, angebot: ProduktAngebot, cfg: dict) -> tuple[str, float, str] | None:
    """Produktseite eines Preisvergleichs öffnen: günstigster Händler, sein Preis und Link zum Angebot."""
    page.goto(angebot.url, wait_until="domcontentloaded")
    if not b.schutzseite_abwarten(page, 10):
        return None
    b.accept_cookies(page)
    cards = b.wait_for_cards(page, r"€|,[-–]", timeout_s=min(cfg["browser"].get("timeout_sekunden", 60), 20),
                             min_len=15, min_cards=2)
    zeilen = []
    for c in cards:
        p, h = preis(c["text"]), haendler_aus_karte(c)
        if p is not None and h:
            zeilen.append((p, h, c.get("href") or ""))
    if not zeilen:
        b.dump_debug(page, f"{angebot.shop}-haendler-{norm(angebot.name)[:24]}", cards)
        return None
    p, h, link = min(zeilen, key=lambda z: z[0])
    return h, p, link


# Wörter, die auf Zubehör statt auf das Produkt selbst hindeuten
_ZUBEHOER = re.compile(
    r"\b(für|fuer|for|kompatibel|passend|geeignet)\b|hülle|huelle|\bcase\b|cover|tasche|folie|glas|schutz|skin|"
    r"adapter|ladestation|ladegerät|netzteil|halter|ständer|staender|grip|\bspiele?\b|videospiel|"
    r"gutschein|guthaben|\bcode\b|abo\b|mitgliedschaft|ersatz|reparatur|kühler|kuehler|lüfter|luefter|"
    r"backplate|wasserkühl|riser|fernbedienung|\bleer|attrappe|dummy|aufkleber|poster|figur|tasse", re.I)


def sieht_nach_hauptprodukt_aus(name: str) -> bool:
    return len(name) <= 160 and not _ZUBEHOER.search(name)


def preisfehler_kandidat(angebot: ProduktAngebot, artikel: dict) -> bool:
    """Unter dem Mindestpreis, sonst aber passend und kein Zubehör."""
    return ablehnungsgrund(angebot, artikel) == "unter Mindestpreis" and sieht_nach_hauptprodukt_aus(angebot.name)


def haendler_ergaenzen(page, angebote: list[ProduktAngebot], artikel: dict, cfg: dict, anzahl: int = 1) -> None:
    """Bei Preisvergleichs-Treffern den tatsächlichen Händler samt Link nachtragen.

    Geprüft werden der günstigste passende Treffer und bis zu zwei mögliche Preisfehler. Ein Preisfehler gilt nur,
    wenn der Preis auf der Produktseite wirklich bei einem Händler steht (sonst oft Gebraucht-/Fremdangebot).
    """
    nutzbar = [a for a in angebote if a.url and not a.url.startswith(("javascript:", "#"))]
    kandidaten = sorted((a for a in nutzbar if passt(a, artikel)), key=lambda a: a.preis)[:anzahl]
    kandidaten += sorted((a for a in nutzbar if preisfehler_kandidat(a, artikel)), key=lambda a: a.preis)[:2]
    for a in kandidaten:
        try:
            ergebnis = haendler_ermitteln(page, a, cfg)
        except Exception as e:
            log.info("Händler für %s nicht ermittelbar: %s", a.name[:40], e)
            a.bestaetigt = False
            continue
        if not ergebnis:
            a.bestaetigt = False
            continue
        h, p, link = ergebnis
        a.bestaetigt = abs(p - a.preis) <= max(2.0, a.preis * 0.05)
        if a.bestaetigt:  # gleiche Größenordnung → Händler, Preis und Direktlink übernehmen
            a.haendler, a.preis = h, p
            if link.startswith("http"):
                a.vergleich_url, a.url = a.url, link
        elif passt(a, artikel):
            a.haendler = h  # Händler trotzdem nennen; Preis/Link bleiben vom Portal


def anbieter(a) -> str:
    """Anzeigename: Shop, bei Preisvergleichen mit tatsächlichem Händler."""
    shop = a["shop"] if isinstance(a, dict) else a.shop
    h = a.get("haendler") if isinstance(a, dict) else getattr(a, "haendler", None)
    return f"{h} (über {shop_name(shop)})" if h else shop_name(shop)


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
