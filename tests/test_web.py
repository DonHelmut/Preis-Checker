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
