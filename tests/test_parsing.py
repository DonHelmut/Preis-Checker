from preischecker.sources.parsing import parse_internet, parse_strom

STROM = """TARIFTIPP
Musterenergie
Klimastrom 12
Arbeitspreis 26,49 ct/kWh
Grundpreis 11,90 €/Monat
Neukundenbonus 80,00 €
Preisgarantie 12 Monate
Vertragslaufzeit 12 Monate
Ökostrom
805,05 € im 1. Jahr"""

DSL = """Vodafone
GigaZuhause 250 Kabel
bis zu 250 Mbit/s
1.-6. Monat 19,99 €
ab 7. Monat 44,99 €
Anschlussgebühr 69,99 €
Bonus 100,00 €
Mindestlaufzeit 24 Monate"""


def test_strom():
    a = parse_strom(STROM)
    assert (a.anbieter, a.tarif) == ("Musterenergie", "Klimastrom 12")
    assert a.arbeitspreis_ct == 26.49 and a.grundpreis_monat == 11.90
    assert a.bonus == 80 and a.laufzeit_monate == 12 and a.preisgarantie_monate == 12
    assert a.oekostrom and a.jahrespreis_angezeigt == 805.05
    assert a.jahreskosten(2500) == round(2500 * 0.2649 + 12 * 11.9, 2)
    assert a.jahreskosten(2500, bonus_einrechnen=True) == round(2500 * 0.2649 + 12 * 11.9 - 80, 2)


def test_strom_nur_jahrespreis():
    a = parse_strom("Anbieter X\nTarif Y\n1.234,56 € pro Jahr\nBonus 100 €")
    assert a.jahrespreis_angezeigt == 1234.56
    assert a.jahreskosten(2500) == 1334.56


def test_internet():
    a = parse_internet(DSL)
    assert a.anbieter == "Vodafone" and a.download_mbit == 250
    assert (a.aktion_monate, a.preis_monat_start, a.preis_monat_regulaer) == (6, 19.99, 44.99)
    assert a.anschlussgebuehr == 69.99 and a.bonus == 100 and a.laufzeit_monate == 24
    erwartet = round((6 * 19.99 + 18 * 44.99 + 69.99 - 100) / 24, 2)
    assert a.durchschnitt_monat() == erwartet


def test_kein_angebot():
    assert parse_strom("Impressum Kontakt") is None
    assert parse_internet("nur Text 12,99 €") is None
