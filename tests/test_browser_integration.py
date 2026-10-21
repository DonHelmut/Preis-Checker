"""Echter Browser, mehrere Arbeitsprozesse parallel. Läuft nur mit PREISCHECKER_CHROMIUM (Pfad zu Chromium)."""
import os

import pytest
import yaml

from preischecker import db, runner
from preischecker.config import load_config

pytestmark = pytest.mark.skipif(not (os.environ.get("PREISCHECKER_CHROMIUM") or os.environ.get("PREISCHECKER_BROWSERTEST")),
                                reason="Browsertest nur mit PREISCHECKER_BROWSERTEST=1 oder PREISCHECKER_CHROMIUM")

SEITE = """<html><body><div class="liste">{karten}</div></body></html>"""
KARTE = '<a href="/p/{i}"><div>{name}</div><span>{preis} €</span><span>Auf Lager</span></a>'


def test_schutzseite_wird_erkannt(tmp_path):
    from preischecker.sources import browser, shops
    (tmp_path / "cf.html").write_text("<html><head><title>Nur einen Moment…</title></head><body>…</body></html>")
    cfg = {"browser": {"timeout_sekunden": 5}, "produkte": {}}
    with browser.browser_page(cfg) as page:
        import preischecker.sources.browser as b
        orig = b.schutzseite_abwarten
        b.schutzseite_abwarten = lambda page, sekunden=20: orig(page, 2)
        try:
            with pytest.raises(shops.BlockiertError):
                shops.suchen(page, "x", f"file://{tmp_path}/cf.html?{{q}}", "test", cfg)
        finally:
            b.schutzseite_abwarten = orig


def test_parallele_prozesse_ohne_vermischung(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    shops = {}
    for n, basis in (("shop_a", 400), ("shop_b", 500), ("shop_c", 600)):
        for suche in ("Alpha Eins", "Beta Zwei"):
            karten = "".join(KARTE.format(i=i, name=f"{suche} Modell {n} {i}", preis=f"{basis + i},00")
                             for i in range(3))
            (tmp_path / f"{n}-{suche.replace(' ', '+')}.html").write_text(SEITE.format(karten=karten))
        shops[n] = f"file://{tmp_path}/{n}-{{q}}.html"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"produkte": {"aktiv": True, "parallel": 3, "quellen": ["x"],
                                                 "eigene_shops": shops,
                                                 "liste": [{"suche": "Alpha Eins"}, {"suche": "Beta Zwei"}]},
                                    "browser": {"timeout_sekunden": 10}}))
    cfg = load_config(path)
    auftraege = [(a["suche"], s, u) for a in cfg["produkte"]["liste"] for s, u in shops.items()]
    f = runner.Fortschritt()
    f.beginnen(len(auftraege), "Test")
    angebote, fehler = runner.sammeln(cfg, auftraege, f, status_speichern=False)
    assert not fehler
    for suche in ("Alpha Eins", "Beta Zwei"):
        je_shop = {}
        for a in angebote[suche]:
            assert a.name.startswith(suche) and a.shop in a.name  # keine Vermischung zwischen Prozessen
            je_shop.setdefault(a.shop, []).append(a.preis)
        assert {k: min(v) for k, v in je_shop.items()} == {"shop_a": 400, "shop_b": 500, "shop_c": 600}
    assert f.fertig == 6


def test_turnstile_captcha_gilt_als_sperre(tmp_path):
    from preischecker.sources import browser as b
    (tmp_path / "cap.html").write_text('<html><body><form id="captcha_form"><div class="cf-turnstile"></div>'
                                      '<button>I am human</button></form></body></html>')
    with b.browser_page({"browser": {"timeout_sekunden": 5}}) as page:
        page.goto(f"file://{tmp_path}/cap.html")
        assert b.schutzseite_abwarten(page, 2) is False
        page.set_content("<html><head><title>Suche</title></head><body>ok</body></html>")
        assert b.schutzseite_abwarten(page, 2) is True
