from __future__ import annotations

from . import db
from .sources.shops import shop_name


def produkt_status(artikel: dict) -> dict:
    e = db.letzte(f"produkt:{artikel['suche']}") or {}
    best = (e.get("angebote") or [{}])[0]
    return {
        "bester_preis": e.get("bester_preis"), "shop": best.get("shop"), "name": best.get("name"),
        "url": best.get("url"),
        "anzeige": f"{best['preis']:.2f}".replace(".", ",") + f" € bei {shop_name(best['shop'])}" if best else None,
        "shop_name": shop_name(best["shop"]) if best else None,
        "aktion": best.get("aktion", False), "alter_preis": best.get("alter_preis"),
        "rabatt_prozent": best.get("rabatt_prozent"),
        "zielpreis": artikel.get("zielpreis"), "ziel_erreicht": e.get("ziel_erreicht", False),
        "schnaeppchen": e.get("schnaeppchen", False), "gruende": e.get("gruende") or [],
        "durchschnitt": e.get("durchschnitt"), "zeit": e.get("zeit"), "fehler": e.get("fehler"),
        "top": [{k: a.get(k) for k in ("preis", "shop", "name", "url", "aktion")}
                for a in (e.get("angebote") or [])[:5]],
    }


def status_daten(cfg: dict) -> dict:
    produkte = {a["suche"]: produkt_status(a) for a in cfg["produkte"].get("liste") or []}
    return {kat: db.letzte(kat) for kat in ("strom", "internet")} | {"produkte": produkte}
