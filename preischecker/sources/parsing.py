"""Text-Heuristiken: aus dem sichtbaren Text einer Ergebnis-Kachel Preise ziehen.

Bewusst tolerant gegenüber Layout-Änderungen: es wird nur Text ausgewertet,
keine CSS-Klassen.
"""
from __future__ import annotations

import re

from ..models import InternetAngebot, StromAngebot

ZAHL = r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"

_SKIP_LINE = re.compile(
    r"(€|ct|kwh|mbit|monat|jahr|bonus|tarif ?tipp|empfehlung|top|testsieger|bewertung|"
    r"weiter|details|vergleich|preisgarantie|laufzeit|ökostrom|^[\d\s.,%+-]+$)",
    re.I,
)


def zahl(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def _find(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, re.I | re.S)
    return zahl(m.group(1)) if m else None


def _monate(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text, re.I | re.S)
    if not m:
        return None
    wert = int(m.group(1))
    if m.lastindex and m.lastindex >= 2 and m.group(2) and m.group(2).lower().startswith("jahr"):
        wert *= 12
    return wert


def anbieter_und_tarif(text: str) -> tuple[str, str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    namen = [l for l in lines if 2 <= len(l) <= 60 and not _SKIP_LINE.search(l)]
    anbieter = namen[0] if namen else (lines[0][:60] if lines else "?")
    tarif = namen[1] if len(namen) > 1 else ""
    return anbieter, tarif


# Check24 (2026): Tarifname, darunter die Note („7,9“), Kosten als „37,56 Ct./kWh · 18,17 €/Monat“
_NOTE = re.compile(r"^\d{1,2},\d$")
_FLEX = re.compile(r"flextarif|variabler preis|dynamisch", re.I)


def _name_vor_note(text: str) -> str | None:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for name, folgt in zip(lines, lines[1:]):
        if _NOTE.match(folgt) and len(name) <= 60:
            return name
    return None


def parse_strom(text: str, quelle: str = "") -> StromAngebot | None:
    if _FLEX.search(text):  # Preis nur für den ersten Monat bekannt → nicht vergleichbar
        return None
    ap = _find(rf"Arbeitspreis\D{{0,40}}?{ZAHL}\s*ct", text) or _find(rf"{ZAHL}\s*ct\.?\s*/\s*kWh", text)
    gp = (_find(rf"Grundpreis\D{{0,40}}?{ZAHL}\s*€\s*(?:/|pro|im)?\s*Monat", text)
          or _find(rf"ct\.?\s*/\s*kWh\W{{0,6}}{ZAHL}\s*€\s*/\s*Monat", text))
    gp_jahr = None
    if gp is None:
        gp_jahr = _find(rf"Grundpreis\D{{0,40}}?{ZAHL}\s*€\s*(?:/|pro|im)?\s*Jahr", text)
        if gp_jahr is not None:
            gp = round(gp_jahr / 12, 2)
    jahr = _find(rf"{ZAHL}\s*€\s*(?:/|pro|im)\s*(?:1\.\s*)?Jahr", text)
    if jahr is not None and gp_jahr is not None and abs(jahr - gp_jahr) < 0.01:
        jahr = None
    bonus = _find(rf"(?:Neukunden|Sofort|Treue)?bonus\D{{0,40}}?{ZAHL}\s*€", text) or 0.0
    if ap is None and jahr is None:
        return None
    name = _name_vor_note(text)
    anbieter, tarif = (name, "") if name else anbieter_und_tarif(text)
    return StromAngebot(
        anbieter=anbieter,
        tarif=tarif,
        arbeitspreis_ct=ap,
        grundpreis_monat=gp,
        jahrespreis_angezeigt=jahr,
        bonus=bonus,
        laufzeit_monate=_monate(r"(?:Vertrags)?laufzeit\D{0,20}?(\d+)\s*(Monat|Jahr)", text),
        preisgarantie_monate=_monate(r"Preisgarantie\D{0,30}?(\d+)\s*(Monat|Jahr)", text),
        oekostrom=bool(re.search(r"öko|grün|erneuerbar", text, re.I)),
        quelle=quelle,
        rohtext=text[:2000],
    )


def parse_internet(text: str, quelle: str = "") -> InternetAngebot | None:
    mbits = [int(m) for m in re.findall(r"(\d{2,5})\s*M[Bb]it", text)]
    if not mbits:
        return None
    name = _name_vor_note(text)
    anbieter, tarif = (name, "") if name else anbieter_und_tarif(text)
    angebot = InternetAngebot(
        anbieter=anbieter,
        tarif=tarif,
        download_mbit=max(mbits),
        quelle=quelle,
        rohtext=text[:2000],
    )
    angebot.durchschnitt_monat_angezeigt = _find(
        rf"(?:Durchschnitt|effektiv|Ø)\D{{0,40}}?{ZAHL}\s*€", text
    )
    # "1.-6. Monat 19,99 €" / "ab 7. Monat 39,99 €"
    m = re.search(rf"(?:1\.?\s*[-–]\s*|bis\s*(?:zum\s*)?)(\d{{1,2}})\.\s*Monat\D{{0,20}}?{ZAHL}\s*€", text, re.I)
    if m:
        angebot.aktion_monate = int(m.group(1))
        angebot.preis_monat_start = zahl(m.group(2))
    m = re.search(rf"ab\s*(?:dem\s*)?(\d{{1,2}})\.\s*Monat\D{{0,20}}?{ZAHL}\s*€", text, re.I)
    if m:
        angebot.preis_monat_regulaer = zahl(m.group(2))
        if not angebot.aktion_monate:
            angebot.aktion_monate = int(m.group(1)) - 1
    if angebot.preis_monat_regulaer is None and angebot.preis_monat_start is None:
        einzel = _find(rf"{ZAHL}\s*€\s*(?:/|pro|im)\s*Monat", text)
        if einzel is not None and angebot.durchschnitt_monat_angezeigt is None:
            angebot.preis_monat_regulaer = einzel
    angebot.anschlussgebuehr = (
        _find(rf"(?:Anschluss|Bereitstellung|Einrichtung)\w*\D{{0,30}}?{ZAHL}\s*€", text) or 0.0
    )
    angebot.bonus = _find(rf"(?:Bonus|Startguthaben|Gutschrift|Cashback)\D{{0,30}}?{ZAHL}\s*€", text) or 0.0
    lz = _monate(r"(?:Mindest|Vertrags)?laufzeit\D{0,20}?(\d+)\s*(Monat|Jahr)", text)
    if lz:
        angebot.laufzeit_monate = lz
    if angebot.durchschnitt_monat() is None:
        return None
    return angebot
