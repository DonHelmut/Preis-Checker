from __future__ import annotations

from datetime import date, timedelta

from .models import InternetAngebot, ProduktAngebot, StromAngebot


def kuendigen_bis(vertrag: dict) -> str | None:
    ende = vertrag.get("vertragsende")
    if not ende:
        return None
    ende = ende if isinstance(ende, date) else date.fromisoformat(str(ende))
    return (ende - timedelta(weeks=vertrag.get("kuendigungsfrist_wochen", 4))).isoformat()


def strom(cfg: dict, angebote: list[StromAngebot]) -> dict:
    v = cfg["strom"]
    f = v["filter"]
    kwh = v["verbrauch_kwh"]
    aktuell = round(kwh * v["arbeitspreis_ct"] / 100 + 12 * v["grundpreis_monat"], 2)
    rows = []
    for a in angebote:
        if f.get("max_laufzeit_monate") and a.laufzeit_monate and a.laufzeit_monate > f["max_laufzeit_monate"]:
            continue
        if f.get("nur_oekostrom") and not a.oekostrom:
            continue
        kosten = a.jahreskosten(kwh, f.get("bonus_einrechnen", False))
        if kosten is None:
            continue
        rows.append({**a.to_dict(), "kosten_jahr": kosten, "ersparnis_jahr": round(aktuell - kosten, 2)})
    rows.sort(key=lambda r: r["kosten_jahr"])
    return {
        "kategorie": "strom",
        "aktuell": {**{k: v.get(k) for k in ("anbieter", "tarif", "arbeitspreis_ct", "grundpreis_monat", "verbrauch_kwh")},
                    "kosten_jahr": aktuell, "kuendigen_bis": kuendigen_bis(v)},
        "angebote": rows,
        "beste_ersparnis_jahr": rows[0]["ersparnis_jahr"] if rows else None,
    }


def internet(cfg: dict, angebote: list[InternetAngebot]) -> dict:
    v = cfg["internet"]
    f = v["filter"]
    aktuell = round(v["preis_monat"] * 12, 2)
    rows = []
    for a in angebote:
        if f.get("min_download_mbit") and (a.download_mbit or 0) < f["min_download_mbit"]:
            continue
        if f.get("max_laufzeit_monate") and a.laufzeit_monate > f["max_laufzeit_monate"]:
            continue
        monat = a.durchschnitt_monat(f.get("bonus_einrechnen", True))
        if monat is None:
            continue
        kosten = round(monat * 12, 2)
        rows.append({**a.to_dict(), "monat_effektiv": monat, "kosten_jahr": kosten,
                     "ersparnis_jahr": round(aktuell - kosten, 2)})
    rows.sort(key=lambda r: r["kosten_jahr"])
    return {
        "kategorie": "internet",
        "aktuell": {**{k: v.get(k) for k in ("anbieter", "tarif", "preis_monat", "download_mbit")},
                    "kosten_jahr": aktuell, "kuendigen_bis": kuendigen_bis(v)},
        "angebote": rows,
        "beste_ersparnis_jahr": rows[0]["ersparnis_jahr"] if rows else None,
    }


def produkt(cfg: dict, artikel: dict, angebote: list[ProduktAngebot]) -> dict:
    from .sources.shops import passt
    nur_lieferbar = cfg["produkte"].get("nur_lieferbar", True)
    beste: dict[tuple, dict] = {}
    for a in angebote:
        if not passt(a, artikel) or (nur_lieferbar and a.lieferbar is False):
            continue
        key = (a.shop, a.name.lower())
        if key not in beste or a.preis < beste[key]["preis"]:
            row = a.to_dict()
            row.pop("rohtext")
            beste[key] = row
    rows = sorted(beste.values(), key=lambda r: r["preis"])
    ziel = artikel.get("zielpreis")
    return {
        "kategorie": f"produkt:{artikel['suche']}",
        "suche": artikel["suche"],
        "zielpreis": ziel,
        "aktuell": {"kosten_jahr": None},
        "angebote": rows,
        "bester_preis": rows[0]["preis"] if rows else None,
        "ziel_erreicht": bool(rows and ziel and rows[0]["preis"] <= ziel),
    }
