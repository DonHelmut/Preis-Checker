"""Einstellungsseite: Formularfelder <-> config.yaml."""
from __future__ import annotations

from datetime import date
from datetime import time as dtime

from .sources.shops import KATEGORIEN, SHOPS

# (Pfad, Beschriftung, Typ, Hinweis)
ABSCHNITTE = [
    ("Adresse", "Für Strom- und Internet-Verfügbarkeit", [
        ("standort.plz", "PLZ", "text", ""),
        ("standort.ort", "Ort", "text", ""),
        ("standort.strasse", "Straße", "text", ""),
        ("standort.hausnummer", "Hausnummer", "text", ""),
    ]),
    ("Strom", "Werte stehen auf der letzten Rechnung", [
        ("strom.aktiv", "Strom vergleichen", "bool", ""),
        ("strom.anbieter", "Anbieter", "text", ""),
        ("strom.tarif", "Tarif", "text", ""),
        ("strom.verbrauch_kwh", "Verbrauch pro Jahr", "int", "kWh"),
        ("strom.arbeitspreis_ct", "Arbeitspreis", "float", "ct/kWh brutto"),
        ("strom.grundpreis_monat", "Grundpreis", "float", "€/Monat brutto"),
        ("strom.vertragsende", "Vertragsende", "date", "leer = unbefristet"),
        ("strom.kuendigungsfrist_wochen", "Kündigungsfrist", "int", "Wochen"),
        ("strom.filter.max_laufzeit_monate", "Max. Laufzeit neuer Tarif", "int", "Monate"),
        ("strom.filter.nur_oekostrom", "Nur Ökostrom", "bool", ""),
    ]),
    ("Internet", "", [
        ("internet.aktiv", "Internet vergleichen", "bool", ""),
        ("internet.anbieter", "Anbieter", "text", ""),
        ("internet.tarif", "Tarif", "text", ""),
        ("internet.preis_monat", "Aktueller Preis", "float", "€/Monat"),
        ("internet.download_mbit", "Aktuelle Geschwindigkeit", "int", "Mbit/s"),
        ("internet.vertragsende", "Vertragsende", "date", ""),
        ("internet.kuendigungsfrist_wochen", "Kündigungsfrist", "int", "Wochen"),
        ("internet.filter.min_download_mbit", "Mindestens", "int", "Mbit/s"),
        ("internet.filter.max_laufzeit_monate", "Max. Laufzeit", "int", "Monate"),
        ("internet.filter.bonus_einrechnen", "Bonus einrechnen", "bool", "auf Laufzeit umgelegt"),
    ]),
    ("Produkt-Suche: Optionen", "", [
        ("produkte.aktiv", "Produkte beobachten", "bool", ""),
        ("produkte.nur_lieferbar", "Nur lieferbare Angebote", "bool", ""),
        ("produkte.schnaeppchen_prozent", "Schnäppchen ab", "float", "% unter eigenem Durchschnitt / Shop-Rabatt"),
        ("produkte.markt_prozent", "Preisfehler ab", "float", "% unter anderen Shops"),
        ("produkte.parallel", "Gleichzeitige Abfragen", "int", "Browser-Tabs parallel (je ca. 250 MB RAM)"),
    ]),
    ("Prüfung", "", [
        ("pruefung.intervall_stunden", "Prüfen alle", "float", "Stunden (6 = 4× täglich)"),
        ("pruefung.benachrichtigen_ab_euro_jahr", "Vertrags-Meldung ab Ersparnis", "float", "€/Jahr"),
    ]),
    ("Benachrichtigung", "Leer lassen, was nicht genutzt wird", [
        ("benachrichtigung.ruhezeit", "Ruhezeit", "bool", "Keine Meldungen – weder Handy noch HA-Glocke"),
        ("benachrichtigung.ruhe_von", "Ruhezeit von", "time", ""),
        ("benachrichtigung.ruhe_bis", "Ruhezeit bis", "time", ""),
        ("benachrichtigung.ruhe_nachholen", "Danach nachholen", "bool",
         "Meldungen aus der Ruhezeit gesammelt zum Ende der Ruhezeit senden (sonst verwerfen)"),
        ("benachrichtigung.webhook_url", "Home-Assistant-Webhook", "text", "http://<ha-ip>:8123/api/webhook/preischecker"),
        ("benachrichtigung.ntfy_topic", "ntfy-Topic", "text", ""),
        ("benachrichtigung.telegram_bot_token", "Telegram Bot-Token", "password", ""),
        ("benachrichtigung.telegram_chat_id", "Telegram Chat-ID", "text", ""),
    ]),
]

PRODUKT_FELDER = ["suche", "kategorie", "zielpreis", "min_preis", "max_preis", "darf_nicht_enthalten"]


def get(cfg: dict, pfad: str):
    for teil in pfad.split("."):
        if not isinstance(cfg, dict):
            return None
        cfg = cfg.get(teil)
    return cfg


def put(cfg: dict, pfad: str, wert) -> None:
    *eltern, letzter = pfad.split(".")
    for teil in eltern:
        cfg = cfg.setdefault(teil, {})
    if wert is None:
        cfg.pop(letzter, None)
    else:
        cfg[letzter] = wert


def _zahl(roh: str, typ: str):
    roh = roh.strip().replace(",", ".")
    if not roh:
        return None
    wert = float(roh)
    return int(wert) if typ == "int" else wert


def anzeigen(wert, typ: str) -> str:
    if wert is None:
        return ""
    if typ == "float" and isinstance(wert, float) and wert.is_integer():
        return str(int(wert))
    return str(wert)


def uebernehmen(cfg: dict, form) -> list[str]:
    """Schreibt Formularwerte in cfg. Gibt Fehlermeldungen zurück (cfg dann unverändert verwenden)."""
    fehler = []
    for _, _, felder in ABSCHNITTE:
        for pfad, label, typ, _ in felder:
            roh = form.get(pfad, "")
            try:
                if typ == "bool":
                    wert = pfad in form
                elif typ in ("int", "float"):
                    wert = _zahl(roh, typ)
                elif typ == "date":
                    wert = date.fromisoformat(roh).isoformat() if roh.strip() else None
                elif typ == "time":
                    wert = dtime.fromisoformat(roh.strip()).strftime("%H:%M") if roh.strip() else None
                else:
                    wert = roh.strip() or None
            except ValueError:
                fehler.append(f"{label}: ungültiger Wert „{roh}“")
                continue
            if typ == "password" and wert is None and get(cfg, pfad):
                continue  # leeres Passwortfeld = unverändert lassen
            put(cfg, pfad, wert)

    if "ha_dienste_feld" in form:  # nur wenn die Checkboxen angezeigt wurden
        put(cfg, "benachrichtigung.ha_dienste", form.getlist("ha_dienste") or None)
        put(cfg, "benachrichtigung.ha_dienst", None)
    if "quellen_feld" in form:
        put(cfg, "produkte.quellen", [k for k in SHOPS if f"quelle_{k}" in form] or None)
    liste = []
    spalten = {f: form.getlist(f"p_{f}") for f in PRODUKT_FELDER}
    for i, suche in enumerate(spalten["suche"]):
        suche = suche.strip()
        if not suche:
            continue
        artikel = {"suche": suche}
        kat = spalten["kategorie"][i] if i < len(spalten["kategorie"]) else ""
        if kat in KATEGORIEN and kat != "alle":
            artikel["kategorie"] = kat
        for f in ("zielpreis", "min_preis", "max_preis"):
            try:
                wert = _zahl(spalten[f][i] if i < len(spalten[f]) else "", "float")
            except ValueError:
                fehler.append(f"{suche} / {f}: ungültige Zahl")
                continue
            if wert is not None:
                artikel[f] = wert
        aus = [w.strip() for w in (spalten["darf_nicht_enthalten"][i] if i < len(spalten["darf_nicht_enthalten"]) else "").split(",") if w.strip()]
        if aus:
            artikel["darf_nicht_enthalten"] = aus
        alt = next((a for a in (get(cfg, "produkte.liste") or []) if a.get("suche") == suche), {})
        if alt.get("muss_enthalten"):
            artikel["muss_enthalten"] = alt["muss_enthalten"]
        liste.append(artikel)
    put(cfg, "produkte.liste", liste)
    return fehler
