"""Kennzahlen aus dem gespeicherten Preisverlauf: Tiefst/Höchst, Schwankung, Trend, Empfehlung."""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean, median, pstdev


def _zeit(z: str) -> datetime:
    return datetime.fromisoformat(z)


def bestpreis_reihe(rows: list[dict]) -> list[dict]:
    """Günstigster Preis je Prüflauf (rows nach Zeit sortiert)."""
    laeufe: dict[str, dict] = {}
    for r in rows:
        b = laeufe.get(r["zeit"])
        if b is None or r["preis"] < b["preis"]:
            laeufe[r["zeit"]] = r
    return [{"zeit": z, "preis": r["preis"], "shop": r["shop"]} for z, r in sorted(laeufe.items())]


def shop_reihen(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["shop"], []).append({"zeit": r["zeit"], "preis": r["preis"]})
    return out


def _fenster(reihe: list[dict], tage: int, jetzt: datetime) -> list[float]:
    grenze = jetzt - timedelta(days=tage)
    return [p["preis"] for p in reihe if _zeit(p["zeit"]) >= grenze]


def kennzahlen(rows: list[dict], zielpreis: float | None = None, jetzt: datetime | None = None) -> dict:
    reihe = bestpreis_reihe(rows)
    if not reihe:
        leer = dict.fromkeys(("seit", "aktuell", "aktuell_shop", "aenderung", "aenderung_prozent", "tiefst",
                              "tiefst_zeit", "tiefst_shop", "hoechst", "hoechst_zeit", "schnitt30", "median90",
                              "gegen_schnitt_prozent", "schwankung_prozent", "spanne_prozent", "schwankung_stufe",
                              "trend_prozent", "perzentil", "bis_ziel"))
        return leer | {"messungen": 0, "zielpreis": zielpreis,
                       "empfehlung": {"stufe": "neutral", "text": "Noch keine Daten", "detail": ""}}
    jetzt = jetzt or _zeit(reihe[-1]["zeit"])
    aktuell = reihe[-1]["preis"]
    alle = [p["preis"] for p in reihe]
    tief = min(reihe, key=lambda p: (p["preis"], p["zeit"]))
    hoch = max(reihe, key=lambda p: (p["preis"], p["zeit"]))
    w30 = _fenster(reihe, 30, jetzt) or alle
    w90 = _fenster(reihe, 90, jetzt) or alle
    w7 = _fenster(reihe, 7, jetzt)
    davor = [p["preis"] for p in reihe if jetzt - timedelta(days=30) <= _zeit(p["zeit"]) < jetzt - timedelta(days=7)]

    schnitt30 = mean(w30)
    schwankung = (pstdev(w30) / schnitt30 * 100) if len(w30) > 1 and schnitt30 else 0.0
    spanne = (max(w30) - min(w30)) / schnitt30 * 100 if schnitt30 else 0.0
    trend = ((mean(w7) - mean(davor)) / mean(davor) * 100) if w7 and davor else None
    vorher = reihe[-2]["preis"] if len(reihe) > 1 else None
    perzentil = round(sum(1 for p in w90 if p < aktuell) / len(w90) * 100) if len(w90) > 1 else None

    k = {
        "messungen": len(reihe),
        "seit": reihe[0]["zeit"],
        "aktuell": aktuell,
        "aktuell_shop": reihe[-1]["shop"],
        "aenderung": round(aktuell - vorher, 2) if vorher is not None else None,
        "aenderung_prozent": round((aktuell - vorher) / vorher * 100, 1) if vorher else None,
        "tiefst": tief["preis"], "tiefst_zeit": tief["zeit"], "tiefst_shop": tief["shop"],
        "hoechst": hoch["preis"], "hoechst_zeit": hoch["zeit"],
        "schnitt30": round(schnitt30, 2),
        "median90": round(median(w90), 2),
        "gegen_schnitt_prozent": round((aktuell - schnitt30) / schnitt30 * 100, 1) if schnitt30 else None,
        "schwankung_prozent": round(schwankung, 1),
        "spanne_prozent": round(spanne, 1),
        "schwankung_stufe": "niedrig" if schwankung < 3 else ("mittel" if schwankung < 8 else "hoch"),
        "trend_prozent": round(trend, 1) if trend is not None else None,
        "perzentil": perzentil,
        "zielpreis": zielpreis,
        "bis_ziel": round(aktuell - zielpreis, 2) if zielpreis else None,
    }
    k["empfehlung"] = empfehlung(k)
    return k


def empfehlung(k: dict) -> dict:
    if k["messungen"] < 4:
        return {"stufe": "neutral", "text": "Sammelt noch Daten",
                "detail": f"{k['messungen']} von mind. 4 Messungen für eine Einschätzung"}
    if k.get("zielpreis") and k["aktuell"] <= k["zielpreis"]:
        return {"stufe": "gut", "text": "Zielpreis erreicht", "detail": f"{-k['bis_ziel']:.2f} € unter deinem Ziel"}
    if k["aktuell"] <= k["tiefst"] * 1.005:
        return {"stufe": "gut", "text": "Tiefstpreis", "detail": "Günstigster Preis seit Beobachtungsbeginn"}
    p = k["perzentil"]
    if p is not None and p <= 20:
        return {"stufe": "gut", "text": "Guter Preis", "detail": f"Günstiger als {100 - p} % der letzten 90 Tage"}
    if p is not None and p >= 70:
        if k["trend_prozent"] is not None and k["trend_prozent"] < -1:
            return {"stufe": "warnung", "text": "Abwarten", "detail": "Eher teuer, Preis fällt gerade"}
        return {"stufe": "teuer", "text": "Eher teuer", "detail": f"Teurer als {p} % der letzten 90 Tage"}
    return {"stufe": "neutral", "text": "Normaler Preis", "detail": "Im üblichen Bereich der letzten 90 Tage"}


def shop_vergleich(rows: list[dict]) -> list[dict]:
    """Aktueller Preis je Shop (letzte Messung des Shops) mit Änderung und Shop-Tiefstpreis."""
    je: dict[str, list[dict]] = {}
    for r in rows:
        je.setdefault(r["shop"], []).append(r)
    letzte_zeit = max((r["zeit"] for r in rows), default=None)
    out = []
    for shop, liste in je.items():
        akt = liste[-1]
        vor = liste[-2]["preis"] if len(liste) > 1 else None
        out.append({
            "shop": shop, "preis": akt["preis"], "name": akt.get("name"), "url": akt.get("url"),
            "aktion": bool(akt.get("aktion")), "zeit": akt["zeit"], "aktuell": akt["zeit"] == letzte_zeit,
            "aenderung": round(akt["preis"] - vor, 2) if vor is not None else None,
            "tiefst": min(r["preis"] for r in liste), "messungen": len(liste),
        })
    out.sort(key=lambda r: (not r["aktuell"], r["preis"]))
    return out
