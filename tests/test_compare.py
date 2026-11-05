from preischecker import compare
from preischecker.models import InternetAngebot, StromAngebot

CFG = {
    "strom": {"verbrauch_kwh": 2500, "arbeitspreis_ct": 32.0, "grundpreis_monat": 12.0, "anbieter": "Alt",
              "vertragsende": "2027-03-31", "kuendigungsfrist_wochen": 4,
              "filter": {"max_laufzeit_monate": 12, "nur_oekostrom": False}},
    "internet": {"preis_monat": 45.0, "anbieter": "Alt", "filter": {"min_download_mbit": 100}},
}


def test_strom_sortiert_und_filtert():
    angebote = [
        StromAngebot("Teuer", arbeitspreis_ct=35, grundpreis_monat=10),
        StromAngebot("Billig", arbeitspreis_ct=25, grundpreis_monat=10),
        StromAngebot("Lang", arbeitspreis_ct=20, grundpreis_monat=10, laufzeit_monate=24),
    ]
    e = compare.strom(CFG, angebote)
    assert e["aktuell"]["kosten_jahr"] == 944.0
    assert [a["anbieter"] for a in e["angebote"]] == ["Billig", "Teuer"]
    assert e["beste_ersparnis_jahr"] == 944.0 - 745.0
    assert e["aktuell"]["kuendigen_bis"] == "2027-03-03"


def test_internet_min_download():
    angebote = [InternetAngebot("Lahm", download_mbit=50, preis_monat_regulaer=20),
                InternetAngebot("Schnell", download_mbit=250, preis_monat_regulaer=40)]
    e = compare.internet(CFG, angebote)
    assert [a["anbieter"] for a in e["angebote"]] == ["Schnell"]
    assert e["beste_ersparnis_jahr"] == 60.0


def test_strom_bonus_zaehlt_nicht_dauerhaft():
    # Wie E.ON real: Bonustarif ist ohne Bonus teurer → keine Ersparnis, nur Hinweis fürs 1. Jahr
    cfg = {"strom": {"verbrauch_kwh": 2700, "arbeitspreis_ct": 33.52, "grundpreis_monat": 18.34, "anbieter": "E.ON",
                     "filter": {}}}
    bonus = StromAngebot("E.ON ÖkoStrom Extra 12", arbeitspreis_ct=37.56, grundpreis_monat=18.17, bonus=309)
    e = compare.strom(cfg, [bonus])
    assert e["aktuell"]["kosten_jahr"] == 1125.12
    assert e["angebote"][0]["kosten_jahr"] == 1232.16 and e["beste_ersparnis_jahr"] == -107.04
    assert e["angebote"][0]["ersparnis_1_jahr"] == 201.96
    assert e["bonus_tipp"]["ersparnis_1_jahr"] == 201.96


def test_internet_ohne_mobilfunk_young_und_nicht_abschliessbar():
    cfg = {"internet": {"preis_monat": 42.99, "filter": {"min_download_mbit": 250}}}
    def a(name, roh, preis):
        return InternetAngebot(name, download_mbit=250, preis_monat_regulaer=preis, rohtext=roh, laufzeit_monate=24)
    e = compare.internet(cfg, [
        a("MagentaMobil Speedbox S Young (100GB)", "über Mobilfunk\nunter 28 Jahren", 29.95),
        a("GigaCube Zuhause 100GB", "über Mobilfunk", 34.99),
        a("Zuhause 250 Flex", "Bei CHECK24 nicht abschließbar", 30.0),
        a("Magenta Zuhause XL Young", "unter 28 Jahren", 31.0),
        a("Komplett easy speed 250", "250 MBit/s\nmtl. kündbar", 39.95),
    ])
    assert [r["anbieter"] for r in e["angebote"]] == ["Komplett easy speed 250"]
    cfg["internet"]["filter"].update(mobilfunk=True, young=True)
    assert len(compare.internet(cfg, [a("GigaCube Zuhause 100GB Young", "über Mobilfunk\nunter 28 Jahren", 34.99)])["angebote"]) == 1


def test_preisfehler_verdacht_unter_mindestpreis(monkeypatch):
    from preischecker.models import ProduktAngebot
    from preischecker import notify
    cfg = {"produkte": {"preisfehler_melden": True}}
    artikel = {"suche": "Nintendo Switch 2", "min_preis": 300, "darf_nicht_enthalten": ["schutzfolie"]}
    a = [ProduktAngebot("Nintendo Switch 2 Spielkonsole inkl. Dock und Joy-Con Controller", 49.0, "amazon", "https://a"),
         ProduktAngebot("Hülle für Nintendo Switch 2", 19.99, "amazon"),
         ProduktAngebot("Nintendo Switch 2 Schutzfolie", 9.99, "otto"),
         ProduktAngebot("Mario Kart World Spiel Nintendo Switch 2", 69.0, "mediamarkt"),
         ProduktAngebot("Nintendo Switch 2", 449.0, "saturn"),
         ProduktAngebot("Nintendo Switch 2", 459.0, "expert")]
    e = compare.produkt(cfg, artikel, a)
    assert e["bester_preis"] == 449.0  # Verdacht verfälscht den Bestpreis nicht
    assert [v["preis"] for v in e["verdacht"]] == [49.0]
    assert notify.verdacht_neu(e, None) and not notify.verdacht_neu(e, e)  # nur einmal melden
    gesendet = []
    monkeypatch.setattr(notify, "_verteilen", lambda cfg, text, daten: gesendet.append(text))
    notify.senden_verdacht(cfg, e, None)
    assert "Möglicher Preisfehler" in gesendet[0] and "49.00 €" in gesendet[0] and "449.00" in gesendet[0]


def test_refurbished_nur_anzeigen():
    from preischecker.models import ProduktAngebot
    artikel = {"suche": "Sonos Beam Gen 2", "min_preis": 350, "zielpreis": 420}
    a = [ProduktAngebot("SONOS Beam Gen.2 (neu oder refurbished)", 407.99, "mediamarkt", "https://mm/beam",
                        zustand="refurbished"),
         ProduktAngebot("Sonos Beam Gen 2 Amazon Renewed", 329.0, "amazon", "https://a/r"),
         ProduktAngebot("SONOS Beam Gen.2, Soundbar, Schwarz", 459.99, "mediamarkt", "https://mm/beam"),
         ProduktAngebot("Sonos Beam (Gen 2)", 449.0, "amazon")]
    e = compare.produkt({"produkte": {}}, artikel, a)
    assert e["bester_preis"] == 449.0 and not e["ziel_erreicht"] and not e["verdacht"]
    assert [r["preis"] for r in e["refurbished"]] == [329.0, 407.99]
    assert all(r["preis"] >= 449 for r in e["angebote"])


def test_refurbished_ohne_spiele():
    from preischecker.models import ProduktAngebot
    artikel = {"suche": "Nintendo Switch 2", "min_preis": 300}
    a = [ProduktAngebot("FC 26 Nintendo Switch 2", 19.09, "rebuy", zustand="refurbished"),
         ProduktAngebot("Goodnight Universe Nintendo Switch 2", 16.79, "rebuy", zustand="refurbished"),
         ProduktAngebot("Nintendo Switch 2 Konsole schwarz", 389.0, "rebuy", zustand="refurbished"),
         ProduktAngebot("Nintendo Switch 2 Konsole (Zustand gut)", 279.0, "backmarket", zustand="refurbished")]
    e = compare.produkt({"produkte": {}}, artikel, a)
    assert [r["preis"] for r in e["refurbished"]] == [279.0, 389.0]


def test_joycon_straps_kein_preisfehler():
    from preischecker.models import ProduktAngebot
    artikel = {"suche": "Nintendo Switch 2", "min_preis": 300}
    a = [ProduktAngebot("Nintendo Controller 10015103 / Switch 2 Joy-Con Straps Blau/Rot", 11.94, "mindfactory"),
         ProduktAngebot("Nintendo Switch 2 Joy-Con 2 Paar", 89.99, "mindfactory"),
         ProduktAngebot("Nintendo Switch 2 Konsole", 49.0, "amazon", "https://a"),
         ProduktAngebot("Nintendo Switch 2", 449.0, "saturn")]
    e = compare.produkt({"produkte": {"preisfehler_melden": True}}, artikel, a)
    assert [v["preis"] for v in e["verdacht"]] == [49.0]
    assert e["bester_preis"] == 449.0


def test_spiele_kein_preisfehler():
    from preischecker.sources.shops import preisfehler_kandidat
    from preischecker.models import ProduktAngebot
    art = {"suche": "Nintendo Switch 2", "min_preis": 300}
    for name in ["Dynasty Warriors: Origins - Nintendo Switch 2 - Beat 'em Up - PEGI 16",
                 "Mario Kart World - Nintendo Switch 2", "Hogwarts Legacy Deluxe Edition Nintendo Switch 2",
                 "Nintendo Switch 2 Game-Key Card Elden Ring"]:
        assert not preisfehler_kandidat(ProduktAngebot(name, 59.99, "proshop"), art), name
    assert preisfehler_kandidat(ProduktAngebot("Nintendo Switch 2 Konsole", 59.99, "proshop"), art)
    assert preisfehler_kandidat(ProduktAngebot("Nintendo Switch 2 - Konsole schwarz", 59.99, "proshop"), art)


def test_zubehoer_fremdmarke_kein_preisfehler():
    from preischecker.sources.shops import preisfehler_kandidat
    from preischecker.models import ProduktAngebot
    art = {"suche": "Nintendo Switch 2", "min_preis": 300}
    assert not preisfehler_kandidat(ProduktAngebot("Venom VS4957, Akku, Nintendo Switch 2, Black, Orange", 46.46,
                                                   "conrad"), art)
    assert not preisfehler_kandidat(ProduktAngebot("Hori Piranha Plant Kamera Nintendo Switch 2", 59.0, "conrad"), art)
    assert preisfehler_kandidat(ProduktAngebot("Nintendo Switch 2 Konsole", 59.0, "conrad"), art)
    assert preisfehler_kandidat(ProduktAngebot("NEU Nintendo Switch 2 Konsole", 59.0, "conrad"), art)


def test_preisfehler_standard_aus():
    from preischecker.models import ProduktAngebot
    a = [ProduktAngebot("Nintendo Switch 2 Konsole", 49.0, "amazon"), ProduktAngebot("Nintendo Switch 2", 449.0, "saturn")]
    e = compare.produkt({"produkte": {}}, {"suche": "Nintendo Switch 2", "min_preis": 300}, a)
    assert e["verdacht"] == [] and e["bester_preis"] == 449.0
