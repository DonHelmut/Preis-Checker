"""Daten für die Weboberfläche aufbereiten (Templates bleiben logikarm)."""
from __future__ import annotations

from datetime import datetime, timedelta

from . import analytics, db
from .ha import slug
from .sources.shops import GRUPPEN_NAMEN, KATEGORIEN, SHOP_LISTE, SHOPS, aktive_shops, shop_name, shops_fuer

MAX_SHOP_LINIEN = 7  # + Bestpreis = 8 Farben, mehr werden nicht gezeichnet


def _seit(tage: int | None) -> str | None:
    return (datetime.now() - timedelta(days=tage)).isoformat(timespec="seconds") if tage else None


def artikel_nach_slug(cfg: dict, s: str) -> dict | None:
    return next((a for a in cfg["produkte"].get("liste") or [] if slug(a["suche"]) == s), None)


def produkt_karte(cfg: dict, artikel: dict) -> dict:
    suche = artikel["suche"]
    letzte = db.letzte(f"produkt:{suche}") or {}
    rows = db.preisverlauf(suche, _seit(365))
    k = analytics.kennzahlen(rows, artikel.get("zielpreis"))
    reihe = analytics.bestpreis_reihe([r for r in rows if r["zeit"] >= (_seit(30) or "")])
    best = (letzte.get("angebote") or [None])[0]
    return {
        "artikel": artikel,
        "slug": slug(suche),
        "kategorie": KATEGORIEN.get(artikel.get("kategorie") or "alle", "Alle Shops").split(" (")[0],
        "letzte": letzte,
        "best": best,
        "k": k,
        "spark": [round(p["preis"], 2) for p in reihe],
        "shops_mit_preis": len({a["shop"] for a in letzte.get("angebote") or []}),
        "shops_gesamt": len(shops_fuer(cfg, artikel)),
    }


def produkt_detail(cfg: dict, artikel: dict) -> dict:
    karte = produkt_karte(cfg, artikel)
    rows = db.preisverlauf(artikel["suche"])
    reihe = analytics.bestpreis_reihe(rows)
    vergleich = analytics.shop_vergleich(rows)
    for v in vergleich:
        v["shop_name"] = shop_name(v["shop"])

    # Linien: Bestpreis + bis zu 7 aktuell günstigste Shops, Farbe folgt der festen Shop-Reihenfolge
    reihen = analytics.shop_reihen(rows)
    gezeigt = [v["shop"] for v in vergleich if v["aktuell"]][:MAX_SHOP_LINIEN]
    ordnung = {s.key: i for i, s in enumerate(SHOP_LISTE)}
    gezeigt.sort(key=lambda s: ordnung.get(s, 999))
    serien = [{"key": "best", "name": "Bestpreis", "farbe": "best",
               "punkte": [[p["zeit"], p["preis"], shop_name(p["shop"])] for p in reihe]}]
    for i, shop in enumerate(gezeigt):
        serien.append({"key": shop, "name": shop_name(shop), "farbe": f"s{i + 1}",
                       "punkte": [[p["zeit"], p["preis"]] for p in reihen.get(shop, [])]})
    chart = {"serien": serien, "ziel": artikel.get("zielpreis")}
    return {**karte, "rows": rows, "reihe": reihe, "vergleich": vergleich, "chart": chart,
            "k": analytics.kennzahlen(rows, artikel.get("zielpreis"))}


def shop_uebersicht(cfg: dict) -> list[dict]:
    status = db.shop_status_alle()
    aktiv = aktive_shops(cfg)
    out = []
    for s in SHOP_LISTE:
        st = status.get(s.key)
        if not st:
            zustand, text = "unbekannt", "Noch nicht abgefragt"
        elif not st["ok"]:
            from .runner import fehler_kurz
            zustand, text = "fehler", fehler_kurz(st["fehler"] or "Fehler").capitalize()
        elif st["treffer"] == 0:
            zustand, text = "warnung", "Keine Preise erkannt"
        else:
            zustand, text = "ok", f"{st['treffer']} Preise"
        out.append({"key": s.key, "name": s.name, "aktiv": s.key in aktiv, "zustand": zustand, "text": text,
                    "gruppen": [GRUPPEN_NAMEN[g] for g in s.gruppen], "status": st})
    for key in aktiv:
        if key not in SHOPS:
            st = status.get(key)
            out.append({"key": key, "name": key, "aktiv": True, "gruppen": ["Eigener Shop"], "status": st,
                        "zustand": "unbekannt" if not st else ("ok" if st["ok"] and st["treffer"] else "warnung"),
                        "text": "Eigener Shop" if not st else f"{st['treffer']} Preise"})
    return out


def vertrag_karte(cfg: dict, kat: str) -> dict | None:
    if not cfg[kat].get("aktiv"):
        return None
    return {"kat": kat, "name": "Strom" if kat == "strom" else "Internet",
            "letzte": db.letzte(kat), "verlauf": db.verlauf(kat, 60)}
