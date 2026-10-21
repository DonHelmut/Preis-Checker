import yaml

from preischecker import compare, db
from preischecker.models import StromAngebot


def test_dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    cfg_path = tmp_path / "config.yaml"
    cfg = {"strom": {"aktiv": True, "anbieter": "Alt", "verbrauch_kwh": 2500, "arbeitspreis_ct": 32,
                     "grundpreis_monat": 12, "filter": {}}, "internet": {"aktiv": False}}
    cfg_path.write_text(yaml.safe_dump(cfg))
    from preischecker.config import load_config
    db.speichern(compare.strom(load_config(cfg_path), [StromAngebot("Neu", "T", 25, 10)]))
    from preischecker.web import create_app
    html = create_app(cfg_path).test_client().get("/").get_data(as_text=True)
    assert "Neu" in html and "944.00" in html


def test_dashboard_produkte(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    cfg_path = tmp_path / "config.yaml"
    artikel = {"suche": "RX 9070 XT", "zielpreis": 640}
    cfg_path.write_text(yaml.safe_dump({"produkte": {"aktiv": True, "liste": [artikel]}}))
    from preischecker.config import load_config
    from preischecker.models import ProduktAngebot
    cfg = load_config(cfg_path)
    for p in (659, 629):
        db.speichern(compare.produkt(cfg, artikel, [ProduktAngebot("Pulse RX 9070 XT", p, "alternate", "https://x/1")]))
    from preischecker.web import create_app
    html = create_app(cfg_path).test_client().get("/").get_data(as_text=True)
    assert "629.00 €" in html and "https://x/1" in html and "alternate" in html


def test_api_status_produkte(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    cfg_path = tmp_path / "config.yaml"
    artikel = {"suche": "RX 9070 XT", "zielpreis": 640}
    cfg_path.write_text(yaml.safe_dump({"produkte": {"aktiv": True, "liste": [artikel, {"suche": "Switch 2"}]}}))
    from preischecker.config import load_config
    from preischecker.models import ProduktAngebot
    db.speichern(compare.produkt(load_config(cfg_path), artikel,
                                 [ProduktAngebot("Pulse RX 9070 XT", 629, "alternate", "https://x/1")]))
    from preischecker.web import create_app
    p = create_app(cfg_path).test_client().get("/api/status").get_json()["produkte"]
    assert p["RX 9070 XT"]["bester_preis"] == 629 and p["RX 9070 XT"]["ziel_erreicht"]
    assert p["RX 9070 XT"]["url"] == "https://x/1"
    assert p["Switch 2"]["bester_preis"] is None


def test_api_anzeige(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    cfg_path = tmp_path / "config.yaml"
    artikel = {"suche": "Switch 2"}
    cfg_path.write_text(yaml.safe_dump({"produkte": {"aktiv": True, "liste": [artikel]}}))
    from preischecker.config import load_config
    from preischecker.models import ProduktAngebot
    db.speichern(compare.produkt(load_config(cfg_path), artikel,
                                 [ProduktAngebot("Nintendo Switch 2", 449.9, "geizhals", aktion=True)]))
    from preischecker.web import create_app
    app = create_app(cfg_path).test_client()
    p = app.get("/api/status").get_json()["produkte"]["Switch 2"]
    assert p["anzeige"] == "449,90 € bei geizhals" and p["aktion"] is True
    assert "Aktion" in app.get("/").get_data(as_text=True)


def test_update_anfordern(tmp_path, monkeypatch):
    from preischecker import web
    monkeypatch.setattr(web, "DATA_DIR", tmp_path)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("{}")
    (tmp_path / "update.status").write_text("ok abc -> def")
    (tmp_path / "version.txt").write_text("def 21.10.2026 Test")
    app = web.create_app(cfg_path).test_client()
    assert app.get("/api/version").get_json() == {"version": "def 21.10.2026 Test", "update": "ok abc -> def"}
    assert app.post("/api/update", json={}).get_json() == {"update": "angefordert"}
    assert (tmp_path / "update.request").exists()
    assert app.get("/api/update/status").get_data(as_text=True) == "angefordert"


def test_footer_update_status(tmp_path, monkeypatch):
    from preischecker import web
    monkeypatch.setattr(web, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    (tmp_path / "config.yaml").write_text("{}")
    (tmp_path / "update.status").write_text("ok a -> b")
    html = web.create_app(tmp_path / "config.yaml").test_client().get("/").get_data(as_text=True)
    assert "Update: ok a -&gt; b" in html and "built-in" not in html
