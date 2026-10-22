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


def test_haendler_aus_preisvergleich(tmp_path, monkeypatch):
    """Suchseite im Geizhals-Stil → Produktseite mit Händlerliste → günstigster Händler wird übernommen."""
    from preischecker import worker
    produkt = tmp_path / "produkt.html"
    produkt.write_text("""<html><body><h1>Sonos Beam (Gen 2)</h1><div class="angebote">
      <div class="offer"><span>€ 469,00</span><img alt="MediaMarkt"><span>lagernd</span></div>
      <div class="offer"><span>€ 449,00</span><span>Versand ab € 4,99</span><a href="#">Alternate</a></div>
      <div class="offer"><span>€ 479,00</span><span>kaufen bei technik-shop24.de</span></div>
    </div></body></html>""")
    suche = tmp_path / "suche.html"
    suche.write_text(f"""<html><body><div class="liste">
      <a href="file://{produkt}"><div>Sonos Beam (Gen 2) schwarz</div><span>ab € 449,00</span></a>
      <a href="file://{produkt}"><div>Sonos Beam (Gen 2) Wandhalterung</div><span>ab € 39,00</span></a>
      <a href="file://{produkt}"><div>Sonos Arc Ultra</div><span>ab € 899,00</span></a>
    </div></body></html>""")
    cfg = {"browser": {"timeout_sekunden": 10}, "produkte": {}}
    artikel = {"suche": "Sonos Beam Gen 2", "min_preis": 250}
    try:
        _, _, gefunden, fehler, _ = worker.auftrag(cfg, "Sonos Beam Gen 2", "geizhals", f"file://{suche}?{{q}}",
                                                   artikel=artikel)
    finally:
        worker._schliessen()
    assert fehler is None
    beam = next(a for a in gefunden if a.name == "Sonos Beam (Gen 2) schwarz")
    assert beam.haendler == "Alternate" and beam.preis == 449.0
    assert all(a.haendler is None for a in gefunden if a is not beam)  # nur der günstigste passende Treffer


def test_spaetes_cookie_banner_blockiert_nicht(tmp_path):
    """Check24-Stil: Banner erscheint verzögert und legt eine Sperrschicht über die Seite."""
    from preischecker.sources import browser as b
    (tmp_path / "c24.html").write_text("""<html><body>
      <button onclick="document.title='abgeschickt'">Tarife vergleichen</button>
      <script>setTimeout(() => {
        const w = document.createElement('div'); w.className = 'c24-cookie-consent-wrapper';
        w.innerHTML = '<div class="c24-strict-blocking-layer" style="position:fixed;inset:0;background:rgba(0,0,0,.3)"></div>'
          + '<div style="position:fixed;bottom:0;left:0;right:0;background:#fff"><span>Wir nutzen Cookies</span>'
          + '<a class="c24-cookie-consent-button" onclick="this.closest(\\'.c24-cookie-consent-wrapper\\').remove()">'
          + '<span>geht klar</span></a></div>';
        document.body.appendChild(w);
      }, 600);</script></body></html>""")
    with b.browser_page({"browser": {"timeout_sekunden": 5}}) as page:
        page.goto(f"file://{tmp_path}/c24.html")
        assert b.accept_cookies(page) is True
        b.submit(page)
        page.wait_for_timeout(300)
        assert page.title() == "abgeschickt"


def test_offene_ortsauswahl_blockiert_nicht(tmp_path):
    """Check24-Stil: Nach der PLZ bleibt eine Ortsliste offen und verdeckt den Verbrauch-Button."""
    from preischecker.sources import browser as b
    (tmp_path / "strom.html").write_text("""<html><body>
      <input id="address" aria-label="Postleitzahl &amp; Ort" type="tel"
             oninput="document.getElementById('orte').style.display = this.value.length == 5 ? 'block' : 'none'">
      <button aria-label="Verbrauch " style="margin-top:20px"
              onclick="document.getElementById('kwhbox').style.display='block'">2.500 kWh</button>
      <div id="kwhbox" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:#eee">
        <input id="kwh" aria-label="Jahresverbrauch in kWh">
        <button onclick="document.getElementById('wert').value = document.getElementById('kwh').value;
                         this.parentNode.style.display='none'">Übernehmen</button></div>
      <input id="wert" type="hidden">
      <button title="Vergleichen" onclick="document.title = 'abgeschickt ' + document.getElementById('wert').value
                                            + ' ' + document.getElementById('address').value">Vergleichen</button>
      <div id="orte" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:#fff">
        <ul role="list"><li><button type="button"
          onclick="document.getElementById('address').value += ' Korb'; this.closest('#orte').style.display='none'">
          <span>71404</span><span>Korb</span></button></li></ul></div>
    </body></html>""")
    with b.browser_page({"browser": {"timeout_sekunden": 5}}) as page:
        page.goto(f"file://{tmp_path}/strom.html")
        assert b.fill_first(page, ["postleitzahl", "plz"], "71404")
        b.pick_autocomplete(page, "71404")
        assert b.fill_first(page, ["verbrauch", "kwh"], "2700")
        assert b.bestaetigen(page)
        b.submit(page)
        page.wait_for_timeout(300)
        assert page.title() == "abgeschickt 2700 71404 Korb"


def test_check24_dsl_adressdialog(tmp_path, monkeypatch):
    """Check24 DSL: Adresse steckt in einem Dialog hinter dem Button „Adresse“, Straße erst nach Ortswahl aktiv."""
    from preischecker.sources import browser as b, check24
    (tmp_path / "dsl.html").write_text("""<html><body>
      <button type="button" onclick="document.getElementById('dlg').show()"><p>Adresse</p><p> </p></button>
      <dialog id="dlg"><form method="dialog">
        <label for="r0">PLZ oder Ort</label><input id="r0" type="text"
          oninput="document.getElementById('l0').style.display = this.value.length == 5 ? 'block' : 'none'">
        <ul id="l0" style="display:none"><li onclick="document.getElementById('r0').value='71404 Korb';
            this.parentNode.style.display='none'; document.getElementById('r1').disabled=false">71404 Korb</li></ul>
        <label for="r1">Straße</label><input id="r1" type="text" disabled
          oninput="document.getElementById('l1').style.display='block'">
        <ul id="l1" style="display:none"><li onclick="document.getElementById('r1').value='Pestalozzistr.';
            this.parentNode.style.display='none'; document.getElementById('r2').disabled=false">Pestalozzistr.</li></ul>
        <label for="r2">Nr.</label><input id="r2" type="text" disabled
          oninput="document.getElementById('l2').style.display='block'">
        <ul id="l2" style="display:none"><li onclick="r2.value='19!'">19</li>
          <li onclick="r2.value='9!'; this.parentNode.style.display='none'">9</li></ul>
        <button type="submit">fertig</button></form></dialog>
      <button type="button" onclick="document.title = 'falscher Button'"><p>ohne Router · mit Young Tarifen</p></button>
      <fieldset><label><input type="radio" name="art" value="new" id="wechsel"> neuer Vertrag</label>
        <label><input type="radio" name="art" value="change"> Vertrag wechseln</label></fieldset>
      <button type="button" onclick="if (wechsel.checked) document.title = [r0.value, r1.value, r2.value].join('|')">vergleichen</button>
    </body></html>""")
    monkeypatch.setattr(check24, "DSL_START", f"file://{tmp_path}/dsl.html")
    monkeypatch.setattr(b, "wait_for_cards", lambda page, *a, **k: [{"text": page.title()}])
    cfg = {"browser": {"timeout_sekunden": 5},
           "standort": {"plz": "71404", "strasse": "Pestalozzistraße", "hausnummer": "9"}}
    with b.browser_page(cfg) as page:
        assert check24._dsl_cards(page, cfg)[1] == [{"text": "71404 Korb|Pestalozzistr.|9!"}]


def test_ergebnis_im_neuen_tab(tmp_path):
    from preischecker.sources import browser as b
    (tmp_path / "erg.html").write_text("<html><head><title>Ergebnis</title></head><body>ok</body></html>")
    (tmp_path / "start.html").write_text(f"""<html><body>
      <button onclick="window.open('file://{tmp_path}/erg.html')">Vergleichen</button></body></html>""")
    with b.browser_page({"browser": {"timeout_sekunden": 5}}) as page:
        page.goto(f"file://{tmp_path}/start.html")
        assert b.submit(page).title() == "Ergebnis"
