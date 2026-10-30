import yaml

from preischecker import compare, db, ha
from preischecker.config import load_config
from preischecker.models import ProduktAngebot


def test_sensoren(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    path = tmp_path / "config.yaml"
    artikel = {"suche": "Nintendo Switch 2", "zielpreis": 430}
    path.write_text(yaml.safe_dump({"produkte": {"aktiv": True, "liste": [artikel, {"suche": "RX 9070 XT"}]},
                                    "strom": {"aktiv": False}}))
    cfg = load_config(path)
    db.speichern(compare.produkt(cfg, artikel, [ProduktAngebot("Nintendo Switch 2", 419.0, "geizhals", "https://g")]))
    s = {e: (st, a) for e, st, a in ha.sensoren(cfg)}
    st, a = s["sensor.preischecker_nintendo_switch_2"]
    assert st == 419.0 and a["shop"] == "geizhals" and a["ziel_erreicht"] and a["unit_of_measurement"] == "€"
    assert s["sensor.preischecker_rx_9070_xt"][0] == "unknown"
    assert "sensor.preischecker_strom_ersparnis" not in s


def test_slug():
    assert ha.slug("Grafikkarte Größe 9070 XT") == "grafikkarte_groesse_9070_xt"


def test_benachrichtigen_ruft_dienst(monkeypatch):
    aufrufe = []
    monkeypatch.setenv("SUPERVISOR_TOKEN", "x")
    monkeypatch.setattr(ha, "_post", lambda pfad, daten: aufrufe.append((pfad, daten)))
    from preischecker import notify
    notify.test({"benachrichtigung": {"ha_dienst": "notify.mobile_app_handy"}})
    assert aufrufe[0][0] == "/services/notify/mobile_app_handy" and "Testnachricht" in aufrufe[0][1]["message"]


def test_checkboxen_handys(tmp_path, monkeypatch):
    from preischecker import web
    monkeypatch.setenv("SUPERVISOR_TOKEN", "x")
    monkeypatch.setattr(ha, "_get", lambda pfad: [
        {"domain": "light", "services": {"turn_on": {}}},
        {"domain": "notify", "services": {"mobile_app_kalle_handy": {}, "mobile_app_franzi_handy": {},
                                          "notify": {}, "send_message": {}}}])
    monkeypatch.setattr(web, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"benachrichtigung": {"ha_dienst": "notify.mobile_app_kalle_handy"}}))
    app = web.create_app(path).test_client()
    html = app.get("/einstellungen").get_data(as_text=True)
    assert "Franzi Handy" in html and "Kalle Handy" in html and "HA-Glocke" in html and "send_message" not in html
    assert 'value="notify.mobile_app_kalle_handy" checked' in html
    assert 'value="notify.mobile_app_franzi_handy" checked' not in html

    app.post("/einstellungen", data={"ha_dienste_feld": "1",
                                     "ha_dienste": ["notify.mobile_app_kalle_handy", "notify.mobile_app_franzi_handy"]})
    from preischecker.config import load_raw
    n = load_raw(path)["benachrichtigung"]
    assert n["ha_dienste"] == ["notify.mobile_app_kalle_handy", "notify.mobile_app_franzi_handy"]
    assert "ha_dienst" not in n

    aufrufe = []
    monkeypatch.setattr(ha, "_post", lambda pfad, daten: aufrufe.append(pfad))
    from preischecker import notify
    notify.test({"benachrichtigung": n})
    assert aufrufe == ["/services/notify/mobile_app_kalle_handy", "/services/notify/mobile_app_franzi_handy"]


def test_ohne_addon_keine_checkboxen_und_nichts_geloescht(tmp_path, monkeypatch):
    from preischecker import web
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setattr(web, "DATA_DIR", tmp_path)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"benachrichtigung": {"ha_dienste": ["notify.x"]}}))
    app = web.create_app(path).test_client()
    assert "Benachrichtigen an" not in app.get("/einstellungen").get_data(as_text=True)
    app.post("/einstellungen", data={})
    from preischecker.config import load_raw
    assert load_raw(path)["benachrichtigung"]["ha_dienste"] == ["notify.x"]


def test_push_oeffnet_angebot(monkeypatch):
    aufrufe = []
    monkeypatch.setenv("SUPERVISOR_TOKEN", "x")
    monkeypatch.setattr(ha, "_post", lambda pfad, daten: aufrufe.append((pfad, daten)))
    from preischecker import notify
    cfg = {"benachrichtigung": {"ha_dienste": ["notify.mobile_app_kalle", "persistent_notification.create"]}}
    notify._laut_senden(cfg, "Preisfehler", {"url": "https://www.alternate.de/x"})
    handy, glocke = aufrufe
    assert handy[1]["data"] == {"clickAction": "https://www.alternate.de/x", "url": "https://www.alternate.de/x"}
    assert "data" not in glocke[1]  # HA-Glocke kennt keine Links


def test_nachgeholt_behaelt_link(tmp_path, monkeypatch):
    from preischecker import db, notify
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notify, "in_ruhezeit", lambda n, jetzt=None: False)
    gesendet = []
    monkeypatch.setattr(notify, "_laut_senden", lambda cfg, text, payload: gesendet.append(payload))
    db.nachricht_merken("Möglicher Preisfehler", {"url": "https://shop/x"})
    assert notify.nachholen({"benachrichtigung": {}}) == 1 and gesendet[0]["url"] == "https://shop/x"
