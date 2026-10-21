from preischecker import compare, notify
from preischecker.models import ProduktAngebot
from preischecker.sources.shops import parse_produkt, preis

CFG = {"produkte": {"nur_lieferbar": True}}


def test_preis_formate():
    assert preis("ab € 599,00") == 599.0
    assert preis("649,00 €*") == 649.0
    assert preis("1.299,-") == 1299.0
    assert preis("statt 699,00 € jetzt 629,00 € zzgl. Versand 5,99 €") == 629.0
    assert preis("ab 25,00 € mtl. oder 579,00 €") == 579.0
    assert preis("UVP 799,00 €") is None


def test_parse_karte():
    a = parse_produkt({"text": "Top-Deal\nSapphire Pulse AMD Radeon RX 9070 XT 16GB GDDR6\n€ 629,00\nAuf Lager",
                       "href": "https://shop/x"}, "alternate")
    assert a.name == "Sapphire Pulse AMD Radeon RX 9070 XT 16GB GDDR6"
    assert a.preis == 629.0 and a.lieferbar is True and a.url == "https://shop/x"


def test_relevanz_und_ziel():
    artikel = {"suche": "RX 9070 XT", "zielpreis": 640, "min_preis": 450, "darf_nicht_enthalten": ["wasserkühler"]}
    angebote = [
        ProduktAngebot("Sapphire Pulse RX 9070 XT 16GB", 629, "alternate", lieferbar=True),
        ProduktAngebot("XFX Radeon RX9070XT", 649, "mindfactory"),
        ProduktAngebot("RX 9070 16GB", 549, "geizhals"),                  # kein XT
        ProduktAngebot("Wasserkühler für RX 9070 XT", 129, "alternate"),  # Zubehör
        ProduktAngebot("Asus TUF RX 9070 XT", 599, "alternate", lieferbar=False),
    ]
    e = compare.produkt(CFG, artikel, angebote)
    assert [a["preis"] for a in e["angebote"]] == [629, 649]
    assert e["ziel_erreicht"] and e["bester_preis"] == 629


def test_melden_nur_bei_neuem_tief():
    neu = {"ziel_erreicht": True, "bester_preis": 600}
    assert notify.produkt_melden({}, neu, None)
    assert notify.produkt_melden({}, neu, {"ziel_erreicht": False, "bester_preis": 700})
    assert not notify.produkt_melden({}, neu, {"ziel_erreicht": True, "bester_preis": 600})
    assert notify.produkt_melden({}, neu, {"ziel_erreicht": True, "bester_preis": 610})
    assert not notify.produkt_melden({}, {"ziel_erreicht": False, "bester_preis": 700}, None)
