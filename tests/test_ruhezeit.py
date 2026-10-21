from datetime import datetime

from preischecker import db, notify


def _n(**k):
    return {"ruhezeit": True, "ruhe_von": "22:00", "ruhe_bis": "07:00", "ruhe_nachholen": True} | k


def test_ruhezeit_ueber_mitternacht():
    n = _n()
    assert notify.in_ruhezeit(n, datetime(2026, 10, 21, 23, 30))
    assert notify.in_ruhezeit(n, datetime(2026, 10, 22, 6, 59))
    assert not notify.in_ruhezeit(n, datetime(2026, 10, 22, 7, 0))
    assert not notify.in_ruhezeit(n, datetime(2026, 10, 21, 21, 59))
    tag = _n(ruhe_von="12:00", ruhe_bis="14:00")
    assert notify.in_ruhezeit(tag, datetime(2026, 10, 21, 13, 0)) and not notify.in_ruhezeit(tag, datetime(2026, 10, 21, 15, 0))
    assert not notify.in_ruhezeit(_n(ruhezeit=False), datetime(2026, 10, 21, 23, 30))
    assert not notify.in_ruhezeit(_n(ruhe_von="kaputt"), datetime(2026, 10, 21, 23, 30))


def test_nachts_nichts_morgens_gesammelt(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    gesendet = []
    monkeypatch.setattr(notify, "_laut_senden", lambda cfg, text, payload: gesendet.append(text))
    cfg = {"benachrichtigung": _n()}
    monkeypatch.setattr(notify, "in_ruhezeit", lambda n, jetzt=None: True)
    notify._verteilen(cfg, "Zielpreis erreicht: Switch 2", {})
    notify._verteilen(cfg, "Schnäppchen: Sonos Beam", {})
    assert gesendet == [] and notify.nachholen(cfg) == 0  # nachts: gar nichts, auch nicht die Glocke
    monkeypatch.setattr(notify, "in_ruhezeit", lambda n, jetzt=None: False)
    assert notify.nachholen(cfg) == 2
    assert len(gesendet) == 1 and "2 Meldungen" in gesendet[0] and "Switch 2" in gesendet[0] and "Sonos" in gesendet[0]
    assert notify.nachholen(cfg) == 0  # nur einmal


def test_ohne_nachholen_wird_verworfen(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notify, "in_ruhezeit", lambda n, jetzt=None: True)
    notify._verteilen({"benachrichtigung": _n(ruhe_nachholen=False)}, "x", {})
    assert db.nachrichten_abholen() == []


def test_testnachricht_ignoriert_ruhezeit(monkeypatch):
    gesendet = []
    monkeypatch.setattr(notify, "_laut_senden", lambda cfg, text, payload: gesendet.append(text))
    monkeypatch.setattr(notify, "in_ruhezeit", lambda n, jetzt=None: True)
    notify.test({"benachrichtigung": _n()})
    assert gesendet and "Testnachricht" in gesendet[0]


def test_einstellungen_ruhezeit(tmp_path, monkeypatch):
    import yaml
    from preischecker import web
    from preischecker.config import load_config, load_raw
    monkeypatch.setattr(web, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({}))
    assert load_config(path)["benachrichtigung"]["ruhe_von"] == "22:00"  # Standard an
    app = web.create_app(path).test_client()
    assert 'type="time" name="benachrichtigung.ruhe_von" value="22:00"' in app.get("/einstellungen").get_data(as_text=True)
    app.post("/einstellungen", data={"benachrichtigung.ruhezeit": "on", "benachrichtigung.ruhe_von": "23:15",
                                     "benachrichtigung.ruhe_bis": "06:30"})
    n = load_raw(path)["benachrichtigung"]
    assert (n["ruhezeit"], n["ruhe_von"], n["ruhe_bis"], n["ruhe_nachholen"]) == (True, "23:15", "06:30", False)
    r = app.post("/einstellungen", data={"benachrichtigung.ruhe_von": "25:99"})
    assert r.status_code == 400
