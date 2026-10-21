from datetime import datetime, timedelta

from preischecker import analytics


def _rows(preise, start=datetime(2026, 9, 1), schritt=timedelta(hours=6), shop="a"):
    return [{"zeit": (start + i * schritt).isoformat(timespec="seconds"), "shop": shop, "preis": p}
            for i, p in enumerate(preise)]


def test_bestpreis_je_lauf():
    rows = _rows([500, 490]) + _rows([480, 495], shop="b")
    rows.sort(key=lambda r: r["zeit"])
    r = analytics.bestpreis_reihe(rows)
    assert [(p["preis"], p["shop"]) for p in r] == [(480, "b"), (490, "a")]


def test_kennzahlen_tiefstpreis_und_trend():
    preise = [600] * 40 + [580] * 20 + [540]
    k = analytics.kennzahlen(_rows(preise, schritt=timedelta(hours=12)))
    assert k["messungen"] == 61 and k["tiefst"] == 540 and k["hoechst"] == 600
    assert k["aenderung"] == -40 and k["aenderung_prozent"] == -6.9
    assert k["trend_prozent"] < 0
    assert k["empfehlung"]["text"] == "Tiefstpreis"
    assert k["perzentil"] == 0


def test_eher_teuer_und_abwarten():
    k = analytics.kennzahlen(_rows([500] * 30 + [560] * 3, schritt=timedelta(days=1)))
    assert k["empfehlung"]["stufe"] == "teuer"
    k = analytics.kennzahlen(_rows([500] * 20 + [600] * 8 + [580] * 2, schritt=timedelta(days=1)))
    assert k["trend_prozent"] > 0  # letzte 7 Tage teurer als davor
    k = analytics.kennzahlen(_rows([500] * 63 + [800] * 20 + [700] * 7, schritt=timedelta(days=1)))
    assert k["trend_prozent"] < -1 and k["empfehlung"]["text"] == "Abwarten"


def test_zielpreis_und_wenig_daten():
    assert analytics.kennzahlen(_rows([500, 490]))["empfehlung"]["text"] == "Sammelt noch Daten"
    k = analytics.kennzahlen(_rows([520, 510, 505, 499]), zielpreis=500)
    assert k["empfehlung"]["text"] == "Zielpreis erreicht" and k["bis_ziel"] == -1
    assert analytics.kennzahlen([])["messungen"] == 0


def test_schwankung():
    ruhig = analytics.kennzahlen(_rows([500, 501, 499, 500, 500]))
    wild = analytics.kennzahlen(_rows([500, 400, 600, 450, 550]))
    assert ruhig["schwankung_stufe"] == "niedrig" and wild["schwankung_stufe"] == "hoch"


def test_shop_vergleich():
    rows = sorted(_rows([500, 480]) + _rows([510], shop="b"), key=lambda r: r["zeit"])
    v = analytics.shop_vergleich(rows)
    assert v[0]["shop"] == "a" and v[0]["aenderung"] == -20 and v[0]["aktuell"]
    assert v[1]["shop"] == "b" and not v[1]["aktuell"]
