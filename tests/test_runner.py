import yaml

from preischecker import db, runner
from preischecker.config import load_config
from preischecker.models import ProduktAngebot
from preischecker.sources import shops


def test_parallel_sammeln_und_verlauf(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"produkte": {"aktiv": True, "parallel": 1, "quellen": ["geizhals", "mediamarkt", "saturn"],
                                                 "liste": [{"suche": "Switch 2", "darf_nicht_enthalten": ["hülle"]}, {"suche": "RX 9070 XT", "min_preis": 100}]},
                                    "strom": {"aktiv": False}, "internet": {"aktiv": False}}))
    cfg = load_config(path)

    class FakeBrowser:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def is_closed(self): return False

    preise = {"geizhals": 449.0, "mediamarkt": 469.0, "saturn": 459.0}

    def fake_suchen(page, shop, url, suche, cfg, debug=False):
        if shop == "saturn" and suche == "RX 9070 XT":
            raise TimeoutError("zu langsam")
        name = "Nintendo Switch 2 grau" if suche == "Switch 2" else "Sapphire RX 9070 XT"
        return [ProduktAngebot(name, preise[shop], shop, f"https://{shop}/x"),
                ProduktAngebot("Hülle für " + name, 19.0, shop)]

    monkeypatch.setattr(runner.worker.browser, "browser_page", lambda cfg: FakeBrowser())
    monkeypatch.setattr(shops, "suchen", fake_suchen)
    monkeypatch.setattr(runner.ha, "sync", lambda cfg: None)
    ergebnisse = runner.pruefen(cfg, ["produkte"])
    e = {x["suche"]: x for x in ergebnisse}
    assert e["Switch 2"]["bester_preis"] == 449.0 and e["RX 9070 XT"]["bester_preis"] == 449.0
    assert "Saturn: Zeitüberschreitung" in e["RX 9070 XT"]["fehler"]
    verlauf = db.preisverlauf("RX 9070 XT")
    assert {r["shop"] for r in verlauf} == {"geizhals", "mediamarkt"}
    status = db.shop_status_alle()
    assert status["geizhals"]["ok"] == 1 and status["geizhals"]["ok_gesamt"] == 2
    assert status["saturn"]["fehler_gesamt"] == 1
    assert not runner.FORTSCHRITT.aktiv and runner.FORTSCHRITT.fertig == 6


def test_gesperrte_shops_pausieren(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    db.shop_status_setzen("mindfactory", False, 0, 3.0, "BlockiertError: Bot-Schutz: SECURITY CHECK")
    db.shop_status_setzen("otto", False, 0, 3.0, "TimeoutError: zu langsam")
    db.shop_status_setzen("geizhals", True, 12, 3.0, None)
    assert set(db.gesperrte_shops(12)) == {"mindfactory"}
    cfg = {"produkte": {"sperre_pause_stunden": 12}}
    a = [("x", "mindfactory", "u"), ("x", "otto", "u"), ("x", "geizhals", "u")]
    assert [s for _, s, _ in runner._ohne_gesperrte(cfg, a)] == ["otto", "geizhals"]
    assert runner._ohne_gesperrte({"produkte": {"sperre_pause_stunden": 0}}, a) == a


def test_haendler_wird_gespeichert_und_alte_db_migriert(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    # Datenbank im Stand vor 1.1 (ohne Spalte haendler)
    con = sqlite3.connect(tmp_path / "preischecker.db")
    con.execute("CREATE TABLE preise (id INTEGER PRIMARY KEY AUTOINCREMENT, zeit TEXT NOT NULL, suche TEXT NOT NULL,"
                " shop TEXT NOT NULL, name TEXT, preis REAL NOT NULL, url TEXT, lieferbar INTEGER, aktion INTEGER,"
                " alter_preis REAL)")
    con.execute("INSERT INTO preise (zeit, suche, shop, name, preis) VALUES ('2026-10-20T10:00:00', 'X', 'amazon', 'X', 500)")
    con.commit()
    con.close()
    db.preise_speichern("X", "2026-10-21T10:00:00", [{"shop": "geizhals", "haendler": "Alternate", "name": "X", "preis": 449.0}])
    rows = db.preisverlauf("X")
    assert [(r["shop"], r["haendler"]) for r in rows] == [("amazon", None), ("geizhals", "Alternate")]
    from preischecker import analytics
    assert analytics.bestpreis_reihe(rows)[-1]["haendler"] == "Alternate"
    assert analytics.kennzahlen(rows)["tiefst_haendler"] == "Alternate"
