import yaml
from werkzeug.datastructures import MultiDict

from preischecker import settings, web
from preischecker.config import load_raw


def _app(tmp_path, monkeypatch, cfg):
    monkeypatch.setattr(web, "DATA_DIR", tmp_path)
    from preischecker import db
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True))
    return path, web.create_app(path).test_client()


def test_seite_zeigt_werte(tmp_path, monkeypatch):
    _, app = _app(tmp_path, monkeypatch, {"strom": {"anbieter": "Stadtwerke X", "arbeitspreis_ct": 32.5},
                                          "produkte": {"liste": [{"suche": "RX 9070 XT", "zielpreis": 600.0}]}})
    html = app.get("/einstellungen").get_data(as_text=True)
    assert 'value="Stadtwerke X"' in html and 'value="32.5"' in html
    assert 'value="RX 9070 XT"' in html and 'value="600"' in html
    assert 'href="/einstellungen"' in html and 'class="aktiv"' in html


def test_speichern(tmp_path, monkeypatch):
    path, app = _app(tmp_path, monkeypatch, {
        "benachrichtigung": {"telegram_bot_token": "geheim"},
        "browser": {"headless": True},
        "produkte": {"liste": [{"suche": "Switch 2", "muss_enthalten": ["switch", "2"]}]},
    })
    form = MultiDict([
        ("standort.plz", "12345"), ("strom.aktiv", "on"), ("strom.verbrauch_kwh", "2.500"),
        ("strom.arbeitspreis_ct", "29,9"), ("strom.vertragsende", "2027-03-31"),
        ("benachrichtigung.telegram_bot_token", ""), ("quellen_feld", "1"), ("quelle_geizhals", "on"),
        ("p_suche", "Switch 2"), ("p_zielpreis", "429,99"), ("p_min_preis", ""), ("p_max_preis", ""),
        ("p_darf_nicht_enthalten", "hülle, tasche"),
        ("p_suche", "RX 9070 XT"), ("p_zielpreis", ""), ("p_min_preis", "450"), ("p_max_preis", ""),
        ("p_darf_nicht_enthalten", ""),
        ("p_suche", ""), ("p_zielpreis", ""), ("p_min_preis", ""), ("p_max_preis", ""), ("p_darf_nicht_enthalten", ""),
    ])
    r = app.post("/einstellungen", data=form)
    assert r.status_code == 302
    cfg = load_raw(path)
    assert cfg["standort"]["plz"] == "12345"
    assert cfg["strom"]["aktiv"] is True and cfg["strom"]["arbeitspreis_ct"] == 29.9
    assert cfg["strom"]["vertragsende"] == "2027-03-31"
    assert cfg["internet"]["aktiv"] is False
    assert cfg["benachrichtigung"]["telegram_bot_token"] == "geheim"   # leeres Passwortfeld behält Wert
    assert cfg["browser"] == {"headless": True}                        # unbekannte Teile bleiben
    assert cfg["produkte"]["quellen"] == ["geizhals"]
    assert cfg["produkte"]["liste"] == [
        {"suche": "Switch 2", "zielpreis": 429.99, "darf_nicht_enthalten": ["hülle", "tasche"],
         "muss_enthalten": ["switch", "2"]},
        {"suche": "RX 9070 XT", "min_preis": 450.0},
    ]


def test_ungueltig(tmp_path, monkeypatch):
    path, app = _app(tmp_path, monkeypatch, {"strom": {"verbrauch_kwh": 2500}})
    r = app.post("/einstellungen", data={"strom.verbrauch_kwh": "viel"})
    assert r.status_code == 400 and "ungültiger Wert" in r.get_data(as_text=True)
    assert load_raw(path)["strom"]["verbrauch_kwh"] == 2500


def test_erster_start_legt_config_an(tmp_path, monkeypatch):
    path = tmp_path / "sub" / "config.yaml"
    cfg = load_raw(path)
    assert path.exists() and "strom" in cfg


def test_ingress_prefix(tmp_path, monkeypatch):
    _, app = _app(tmp_path, monkeypatch, {})
    r = app.post("/einstellungen", data={}, headers={"X-Ingress-Path": "/api/hassio_ingress/abc"})
    assert r.headers["Location"].startswith("/api/hassio_ingress/abc/einstellungen")


def test_api_einstellungen(tmp_path, monkeypatch):
    path, app = _app(tmp_path, monkeypatch, {"strom": {"aktiv": True, "verbrauch_kwh": 2500},
                                             "benachrichtigung": {"telegram_bot_token": "geheim"}})
    r = app.post("/api/einstellungen", json={"strom": {"verbrauch_kwh": 3000}, "produkte": {"liste": [{"suche": "X"}]},
                                             "benachrichtigung": {"ha_dienst": "notify.handy"}})
    assert r.status_code == 200
    cfg = load_raw(path)
    assert cfg["strom"] == {"aktiv": True, "verbrauch_kwh": 3000}
    assert cfg["produkte"]["liste"] == [{"suche": "X"}]
    assert cfg["benachrichtigung"] == {"telegram_bot_token": "geheim", "ha_dienst": "notify.handy"}
    assert app.get("/api/einstellungen").get_json()["benachrichtigung"]["telegram_bot_token"] == "***"
    assert app.post("/api/einstellungen", data="kaputt").status_code == 400


def test_schnellsuche_und_beobachten(tmp_path, monkeypatch):
    from preischecker import runner
    from preischecker.models import ProduktAngebot
    from preischecker import compare

    def fake(cfg, artikel, fortschritt=None):
        return compare.produkt(cfg, artikel, [ProduktAngebot("Dyson V15 Detect", 499.0, "geizhals", "https://g/1"),
                                              ProduktAngebot("Dyson V15 Akku", 89.0, "alternate")]) | {"fehler": None}
    monkeypatch.setattr(runner, "schnellsuche", fake)
    path, app = _app(tmp_path, monkeypatch, {"produkte": {"aktiv": False}})
    r = app.post("/suche", data={"q": "Dyson V15", "min_preis": "200"})
    assert r.status_code == 302 and "/suche/" in r.headers["Location"]
    import time
    for _ in range(50):
        html = app.get(r.headers["Location"]).get_data(as_text=True)
        if "läuft" not in html:
            break
        time.sleep(0.05)
    assert "499,00 €" in html and "https://g/1" in html and "Akku" not in html   # min_preis filtert Zubehör
    app.post("/beobachten", data={"q": "Dyson V15", "min_preis": "200", "zielpreis": "450"})
    cfg = load_raw(path)
    assert cfg["produkte"]["aktiv"] is True
    assert cfg["produkte"]["liste"] == [{"suche": "Dyson V15", "zielpreis": 450.0, "min_preis": 200.0}]


def test_links_mit_ingress(tmp_path, monkeypatch):
    _, app = _app(tmp_path, monkeypatch, {})
    html = app.get("/", headers={"X-Ingress-Path": "/api/hassio_ingress/abc"}).get_data(as_text=True)
    assert 'action="/api/hassio_ingress/abc/suche"' in html
    assert 'href="/api/hassio_ingress/abc/einstellungen"' in html
