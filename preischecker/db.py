from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from .config import DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS ergebnisse (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zeit TEXT NOT NULL,
    kategorie TEXT NOT NULL,
    aktuell_jahr REAL,
    bestes_jahr REAL,
    ersparnis_jahr REAL,
    fehler TEXT,
    daten TEXT
);
CREATE INDEX IF NOT EXISTS ergebnisse_kat ON ergebnisse (kategorie, id);

-- Jeder erkannte Preis je Shop und Prüflauf (Basis für Verlauf/Statistik)
CREATE TABLE IF NOT EXISTS preise (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zeit TEXT NOT NULL,
    suche TEXT NOT NULL,
    shop TEXT NOT NULL,
    name TEXT,
    preis REAL NOT NULL,
    url TEXT,
    lieferbar INTEGER,
    aktion INTEGER,
    alter_preis REAL
);
CREATE INDEX IF NOT EXISTS preise_suche_zeit ON preise (suche, zeit);

-- In der Ruhezeit zurückgehaltene Handy-Meldungen
CREATE TABLE IF NOT EXISTS nachrichten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zeit TEXT NOT NULL,
    text TEXT NOT NULL,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS shop_status (
    shop TEXT PRIMARY KEY,
    zeit TEXT,
    ok INTEGER,
    treffer INTEGER,
    dauer REAL,
    fehler TEXT,
    ok_gesamt INTEGER DEFAULT 0,
    fehler_gesamt INTEGER DEFAULT 0
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATA_DIR / "preischecker.db")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    spalten = {r["name"] for r in con.execute("PRAGMA table_info(preise)")}
    if "haendler" not in spalten:  # ab 1.1: tatsächlicher Händler bei Preisvergleichen
        con.execute("ALTER TABLE preise ADD COLUMN haendler TEXT")
    spalten = {r["name"] for r in con.execute("PRAGMA table_info(shop_status)")}
    if "letzte_sperre" not in spalten:  # ab 1.2.6: Shops nach einer Sperre schonender abfragen
        con.execute("ALTER TABLE shop_status ADD COLUMN letzte_sperre TEXT")
    return con


def speichern(ergebnis: dict, fehler: str | None = None) -> None:
    angebote = ergebnis.get("angebote") or []
    with connect() as con:
        con.execute(
            "INSERT INTO ergebnisse (zeit, kategorie, aktuell_jahr, bestes_jahr, ersparnis_jahr, fehler, daten)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                ergebnis["kategorie"],
                (ergebnis.get("aktuell") or {}).get("kosten_jahr"),
                (angebote[0].get("kosten_jahr", angebote[0].get("preis")) if angebote else None),
                ergebnis.get("beste_ersparnis_jahr"),
                fehler,
                json.dumps(ergebnis, ensure_ascii=False),
            ),
        )


def letzte(kategorie: str) -> dict | None:
    with connect() as con:
        row = con.execute(
            "SELECT * FROM ergebnisse WHERE kategorie=? ORDER BY id DESC LIMIT 1", (kategorie,)
        ).fetchone()
    if not row:
        return None
    return {**json.loads(row["daten"]), "zeit": row["zeit"], "fehler": row["fehler"]}


def nachricht_merken(text: str, payload: dict) -> None:
    with connect() as con:
        con.execute("INSERT INTO nachrichten (zeit, text, payload) VALUES (?, ?, ?)",
                    (datetime.now().isoformat(timespec="seconds"), text, json.dumps(payload, ensure_ascii=False)))


def nachrichten_abholen() -> list[dict]:
    """Gemerkte Meldungen holen und entfernen (älteste zuerst)."""
    with connect() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM nachrichten ORDER BY id").fetchall()]
        if rows:
            con.execute("DELETE FROM nachrichten WHERE id<=?", (rows[-1]["id"],))
    return rows


def shop_daten_entfernen(shop: str) -> dict:
    """Alle gespeicherten Preise eines Shops löschen (z. B. nach falsch gelesenen Preisen).

    Gespeicherte Ergebnisse werden ohne diesen Shop neu bewertet, damit Verlauf und Tiefstpreis stimmen.
    """
    geaendert = 0
    with connect() as con:
        geloescht = con.execute("DELETE FROM preise WHERE shop=?", (shop,)).rowcount
        for row in con.execute("SELECT id, daten FROM ergebnisse WHERE kategorie LIKE 'produkt:%'").fetchall():
            e = json.loads(row["daten"])
            rest = [a for a in e.get("angebote") or [] if a.get("shop") != shop]
            if len(rest) == len(e.get("angebote") or []):
                continue
            war_bester = e.get("bester_shop") == shop
            e["angebote"] = rest
            e["bester_preis"] = rest[0]["preis"] if rest else None
            e["bester_shop"] = rest[0]["shop"] if rest else None
            ziel = e.get("zielpreis")
            e["ziel_erreicht"] = bool(rest and ziel and rest[0]["preis"] <= ziel)
            if war_bester:  # Schnäppchen-Gründe bezogen sich auf den falschen Preis
                e["schnaeppchen"], e["gruende"] = False, []
            con.execute("UPDATE ergebnisse SET bestes_jahr=?, daten=? WHERE id=?",
                        (e["bester_preis"], json.dumps(e, ensure_ascii=False), row["id"]))
            geaendert += 1
    return {"preise_geloescht": geloescht, "ergebnisse_korrigiert": geaendert}


def verlauf(kategorie: str, limit: int = 60) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT zeit, aktuell_jahr, bestes_jahr, ersparnis_jahr, fehler FROM ergebnisse"
            " WHERE kategorie=? ORDER BY id DESC LIMIT ?",
            (kategorie, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def preise_speichern(suche: str, zeit: str, angebote: list[dict]) -> None:
    """Günstigstes Angebot je Shop speichern."""
    je_shop: dict[str, dict] = {}
    for a in angebote:
        if a["shop"] not in je_shop or a["preis"] < je_shop[a["shop"]]["preis"]:
            je_shop[a["shop"]] = a
    with connect() as con:
        con.executemany(
            "INSERT INTO preise (zeit, suche, shop, name, preis, url, lieferbar, aktion, alter_preis, haendler)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(zeit, suche, a["shop"], a.get("name"), a["preis"], a.get("url"),
              None if a.get("lieferbar") is None else int(a["lieferbar"]), int(bool(a.get("aktion"))),
              a.get("alter_preis"), a.get("haendler")) for a in je_shop.values()],
        )


def preisverlauf(suche: str, seit: str | None = None) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT zeit, shop, name, preis, url, aktion, haendler FROM preise WHERE suche=? AND zeit>=? ORDER BY zeit",
            (suche, seit or ""),
        ).fetchall()
    return [dict(r) for r in rows]


def shop_status_setzen(shop: str, ok: bool, treffer: int, dauer: float, fehler: str | None) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO shop_status (shop, zeit, ok, treffer, dauer, fehler, ok_gesamt, fehler_gesamt)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(shop) DO UPDATE SET zeit=excluded.zeit, ok=excluded.ok, treffer=excluded.treffer,"
            " dauer=excluded.dauer, fehler=excluded.fehler,"
            " ok_gesamt=ok_gesamt+excluded.ok_gesamt, fehler_gesamt=fehler_gesamt+excluded.fehler_gesamt",
            (shop, datetime.now().isoformat(timespec="seconds"), int(ok), treffer, round(dauer, 1), fehler,
             int(ok), int(not ok)),
        )
        if fehler and fehler.startswith("BlockiertError"):
            con.execute("UPDATE shop_status SET letzte_sperre=zeit WHERE shop=?", (shop,))


def gesperrte_shops(stunden: float) -> dict[str, str]:
    """Shops, die innerhalb der letzten `stunden` eine Bot-Sperre gemeldet haben: shop -> Zeitpunkt."""
    if stunden <= 0:
        return {}
    grenze = (datetime.now() - timedelta(hours=stunden)).isoformat(timespec="seconds")
    with connect() as con:
        rows = con.execute("SELECT shop, zeit FROM shop_status WHERE ok=0 AND fehler LIKE 'BlockiertError%' AND zeit>=?",
                           (grenze,)).fetchall()
    return {r["shop"]: r["zeit"] for r in rows}


def schonend_zurueckhalten(abstand_stunden: float, tage: int = 7) -> dict[str, str]:
    """Shops mit Sperre in den letzten `tage` Tagen, die zuletzt vor weniger als `abstand_stunden` abgefragt wurden.

    Liefert shop -> Zeitpunkt der letzten Abfrage. So wird ein empfindlicher Shop höchstens z. B. 1× täglich angefragt.
    """
    if abstand_stunden <= 0:
        return {}
    jetzt = datetime.now()
    sperre = (jetzt - timedelta(days=tage)).isoformat(timespec="seconds")
    abfrage = (jetzt - timedelta(hours=abstand_stunden)).isoformat(timespec="seconds")
    with connect() as con:
        rows = con.execute("SELECT shop, zeit FROM shop_status WHERE letzte_sperre>=? AND zeit>=?",
                           (sperre, abfrage)).fetchall()
    return {r["shop"]: r["zeit"] for r in rows}


def shop_status_alle() -> dict[str, dict]:
    with connect() as con:
        return {r["shop"]: dict(r) for r in con.execute("SELECT * FROM shop_status").fetchall()}

