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


def test_aktion_und_streichpreis():
    a = parse_produkt({"text": "Deal der Woche\nASUS Prime RX 9070 XT\nstatt 699,00 €\n579,00 €", "href": ""}, "mindfactory")
    assert a.preis == 579 and a.alter_preis == 699 and a.aktion
    assert a.to_dict()["rabatt_prozent"] == 17.2
    b = parse_produkt({"text": "ASUS Prime RX 9070 XT\n649,00 €", "href": ""}, "alternate")
    assert not b.aktion and b.alter_preis is None


CFG2 = {"produkte": {"nur_lieferbar": True, "schnaeppchen_prozent": 15, "markt_prozent": 25}}
ART = {"suche": "RX 9070 XT"}


def test_schnaeppchen_unter_verlauf():
    e = compare.produkt(CFG2, ART, [ProduktAngebot("RX 9070 XT", 520, "alternate")], verlauf=[650, 640, 660, 650])
    assert e["schnaeppchen"] and e["durchschnitt"] == 650 and "unter Ø" in e["gruende"][0]
    e = compare.produkt(CFG2, ART, [ProduktAngebot("RX 9070 XT", 620, "alternate")], verlauf=[650, 640, 660, 650])
    assert not e["schnaeppchen"]
    e = compare.produkt(CFG2, ART, [ProduktAngebot("RX 9070 XT", 400, "alternate")], verlauf=[650])
    assert not e["schnaeppchen"]  # zu wenig Verlauf


def test_schnaeppchen_preisfehler_ein_shop():
    angebote = [ProduktAngebot("RX 9070 XT A", 399, "kleinshop"), ProduktAngebot("RX 9070 XT B", 629, "alternate"),
                ProduktAngebot("RX 9070 XT C", 649, "mindfactory")]
    e = compare.produkt(CFG2, ART, angebote)
    assert e["schnaeppchen"] and e["bester_shop"] == "kleinshop" and "anderen Shops" in e["gruende"][0]


def test_meldetext():
    e = compare.produkt(CFG2, ART, [ProduktAngebot("RX 9070 XT", 520, "alternate", "https://x")], verlauf=[650] * 4)
    t = notify.produkt_text(e)
    assert t.startswith("Schnäppchen: RX 9070 XT") and "520.00 € bei Alternate" in t and "https://x" in t


def test_relevanz_wortgenau():
    from preischecker.sources.shops import enthaelt_suche
    w = ["Nintendo", "Switch", "2"]
    assert enthaelt_suche("Nintendo Switch 2, gray/gray, DE", w)
    assert enthaelt_suche("Nintendo Switch 2 Mario Kart World Bundle", w)
    assert not enthaelt_suche("Nintendo Switch V2 2022 Edition 32GB, neon red - neon blue", w)
    assert not enthaelt_suche("Nintendo Switch OLED 64GB", w)
    assert not enthaelt_suche("Nintendo Switch 2022", w)
    r = ["RX", "9070", "XT"]
    assert enthaelt_suche("16GB PowerColor Radeon RX 9070 XT Hellhound", r)
    assert enthaelt_suche("XFX Swift RX9070XT 16GB", r)
    assert not enthaelt_suche("Sapphire Pulse RX 9070 16GB", r)
    assert not enthaelt_suche("RX 90700 XT", r)


def test_shops_nach_kategorie():
    from preischecker.sources.shops import shops_fuer, aktive_shops
    cfg = {"produkte": {}}
    alle = aktive_shops(cfg)
    assert "mediamarkt" in alle and "conrad" not in alle  # Standard ohne Conrad/Proshop
    hw = shops_fuer(cfg, {"suche": "x", "kategorie": "hardware"})
    assert {"geizhals", "idealo", "mindfactory", "alternate"} <= set(hw) and "mediamarkt" not in hw
    el = shops_fuer(cfg, {"suche": "x", "kategorie": "elektronik"})
    assert {"mediamarkt", "saturn", "geizhals"} <= set(el) and "mindfactory" not in el
    cfg = {"produkte": {"quellen": ["geizhals"], "eigene_shops": {"meinshop": "https://m/{q}"}}}
    assert shops_fuer(cfg, {"suche": "x", "kategorie": "hardware"}) == {
        "geizhals": "https://geizhals.de/?fs={q}&hloc=de", "meinshop": "https://m/{q}"}


def test_ablehnungsgruende_und_bundles():
    from preischecker.sources.shops import ablehnungsgrund
    art = {"suche": "Sonos Beam Gen 2", "min_preis": 250, "darf_nicht_enthalten": ["halterung"]}
    def g(name, preis=449):
        return ablehnungsgrund(ProduktAngebot(name, preis, "x"), art)
    assert g("Sonos Beam (Gen 2) Soundbar schwarz") is None
    assert g("Sonos Beam (Gen 2) + Era 100 SL Soundbar-System") == "Set/Bundle"
    assert g("Sonos Beam Gen 2 Wandhalterung") == "enthält „halterung“"
    assert g("Sonos Beam Gen 2", 99) == "unter Mindestpreis"
    assert g("Sonos Arc Ultra") == "Suchwörter fehlen"
    assert ablehnungsgrund(ProduktAngebot("Sonos Beam Gen 2 + Sub Mini Set", 900, "x"), art | {"bundles": True}) is None


def test_galaxus_preisformat():
    assert preis("Sonos Beam Gen 2\n449.–\nMorgen geliefert") == 449.0
    assert preis("1.299.–") == 1299.0


def test_haendler_aus_angebotszeile():
    from preischecker.sources.shops import haendler_aus_karte
    assert haendler_aus_karte({"text": "€ 449,00\nVersand ab € 4,99\nAlternate\nlagernd", "bilder": []}) == "Alternate"
    assert haendler_aus_karte({"text": "€ 452,90\nauf Lager", "bilder": ["Händlerlogo MediaMarkt"]}) == "MediaMarkt"
    assert haendler_aus_karte({"text": "459,00 €\nkaufen bei technik-shop24.de\n2-3 Werktage"}) == "technik-shop24.de"
    assert haendler_aus_karte({"text": "Gesamtpreis 449,00 €\nzum Shop"}) is None
    assert haendler_aus_karte({"text": "bei geizhals.de vergleichen 449,00 €"}) is None
    # frühester Treffer im Text gewinnt, "Motto" ist nicht Otto
    assert haendler_aus_karte({"text": "Motto-Deal\nCyberport 449,00 €\nauch bei Amazon"}) == "Cyberport"


def test_anbieter_anzeige():
    from preischecker.sources.shops import anbieter
    assert anbieter({"shop": "geizhals", "haendler": "Alternate"}) == "Alternate (über Geizhals)"
    assert anbieter({"shop": "amazon", "haendler": None}) == "Amazon"
    assert anbieter(ProduktAngebot("x", 1, "idealo", haendler="Otto")) == "Otto (über idealo)"


def test_nettopreise_werden_hochgerechnet():
    # Conrad für Geschäftskunden: 402,52 € zzgl. MwSt. = 479,00 € für Privatkunden
    conrad_b2b = "Nintendo Switch 2 256 GB Schwarz\nGesamt (402,52 € / Stück)\n402,52 €\nzzgl. MwSt. & Kostenfreier Versand"
    assert preis(conrad_b2b) == 479.0
    conrad_privat = "Nintendo Switch 2 256 GB Schwarz\nGesamt (479,00 € / Stück)\n479,00 €\ninkl. MwSt. & Kostenfreier Versand"
    assert preis(conrad_privat) == 479.0
    # Beide angegeben → Bruttopreis
    assert preis("Sonos Beam Gen 2\n377,31 € netto\n449,00 € inkl. MwSt.") == 449.0
    assert preis("RX 9070 XT\n699,00 € exkl. MwSt.\n831,81 € brutto") == 831.81
    # „zzgl. Versand“ ist kein Nettopreis
    assert preis("Sonos Beam Gen 2\n449,00 €\nzzgl. Versand 4,99 €") == 449.0


def test_netto_direkt_hinter_preis():
    # Proshop: Brutto ohne „inkl.“, darunter der Nettopreis mit „exkl. MwSt.“
    proshop = "ASRock RX 9070 XT Steel Legend Dark 16GB\nAUF LAGER\n861,17 €\n723,67 € exkl. MwSt.\nBestellen"
    assert preis(proshop) == 861.17
    # Kleiner Betrag daneben (Bundle-Zubehör) darf nicht als Nettopreis gelten
    assert preis(proshop + "\nDieses Bundle enthält: Spiel 59,99 €") == 861.17


def test_name_idealo_titel_statt_technikzeile():
    from preischecker.sources.shops import parse_produkt, passt
    karte = {"href": "https://www.idealo.de/x", "text": "Sonos Beam (Gen.2)\n\nSoundbar ohne Subwoofer, 3.0, WLAN, HDMI, "
             "LAN Netzwerk (Ethernet), Multiroom\n\nNote ∅ 1,8\n443\n66 Angebote\nab437,99 €\nProduktdetails"}
    a = parse_produkt(karte, "idealo", "Sonos Beam Gen 2")
    assert a.name == "Sonos Beam (Gen.2)" and a.preis == 437.99
    assert passt(a, {"suche": "Sonos Beam Gen 2", "min_preis": 350})
    # Set mit Sub Mini bleibt als Bundle draußen
    s = parse_produkt({"text": "Sonos Beam (Gen.2) + Sub Mini 3.1 Entertainment Set Black\n\nSoundbar ohne Subwoofer, 3.0, "
                               "WLAN, HDMI\n\nab803,90 €"}, "idealo", "Sonos Beam Gen 2")
    assert not passt(s, {"suche": "Sonos Beam Gen 2", "min_preis": 350})


def test_finanzierung_ist_kein_preis():
    # MediaMarkt: Zinssatz, Monatsrate, Mindestrate und Gesamtbetrag dürfen nicht als Preis gelten
    mm = ("SONOS Beam (Gen 2) Soundbar, Schwarz\n-16% UVP 549,– €\n459,99 €\nFinanzierung eff. Zins p.a. 10,90 %\n"
          "18 mtl. Raten 27,70 € monatlich\nGesamtbetrag: 498,60 €\n0% effektiver Jahreszins, mind. 9,10 €")
    assert preis(mm) == 459.99


def test_refurbished_hinweis_und_suchzeile():
    from preischecker.sources.shops import parse_produkt, passt
    mm = ("SONOS Beam Gen.2, Soundbar, Schwarz\n-16%\nUVP 549,– €\n549,00€\n459,99 €\n459,99€\ninkl. MwSt.\n"
          "Bezahle in 18 Raten à 27,70 € (eff. Zins. P.a. 10,90 %)** Gesamtpreis 498,60 €\n"
          "Zusätzlich neue und refurbished Angebote ab 407,99 € erhältlich")
    assert preis(mm) == 459.99
    # Proshop: Suchseite wiederholt den Suchbegriff, gefunden wurde aber nur ein Sub 4
    karte = {"text": "Startseite\nSonos Beam Gen 2\n1 Produkte\nSonos SUB 4 - White\nWireless-Subwoofer Sonos Sub 4 "
                     "liefert tiefen, dynamischen Bass der nächsten Generation\n799,00 €"}
    a = parse_produkt(karte, "proshop", "Sonos Beam Gen 2")
    assert not passt(a, {"suche": "Sonos Beam Gen 2"})
    # echter Treffer, dessen Titel genau dem Suchbegriff entspricht, bleibt erhalten
    b = parse_produkt({"text": "Sonos Beam Gen 2\n449,00 €"}, "proshop", "Sonos Beam Gen 2")
    assert b.name == "Sonos Beam Gen 2" and passt(b, {"suche": "Sonos Beam Gen 2"})


def test_refurbished_als_eigenes_angebot():
    from preischecker.sources.shops import nebenangebote, parse_produkt
    karte = {"href": "https://mm/beam", "text": "SONOS Beam Gen.2, Soundbar, Schwarz\n459,99 €\ninkl. MwSt.\n"
             "Zusätzlich neue und refurbished Angebote ab 407,99 € erhältlich"}
    neu = parse_produkt(karte, "mediamarkt", "Sonos Beam Gen 2")
    [ref] = nebenangebote(karte, neu)
    assert neu.preis == 459.99 and ref.preis == 407.99 and ref.zustand == "refurbished"
    assert ref.name.endswith("(neu oder refurbished)") and ref.url == "https://mm/beam"
    assert nebenangebote({"text": "Beam\n459,99 €"}, neu) == []
