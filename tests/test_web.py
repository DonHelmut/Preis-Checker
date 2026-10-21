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
