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
