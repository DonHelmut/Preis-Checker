from __future__ import annotations

import json
import sqlite3
from datetime import datetime

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
            "INSERT INTO preise (zeit, suche, shop, name, preis, url, lieferbar, aktion, alter_preis)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(zeit, suche, a["shop"], a.get("name"), a["preis"], a.get("url"),
              None if a.get("lieferbar") is None else int(a["lieferbar"]), int(bool(a.get("aktion"))),
              a.get("alter_preis")) for a in je_shop.values()],
        )


def preisverlauf(suche: str, seit: str | None = None) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT zeit, shop, name, preis, url, aktion FROM preise WHERE suche=? AND zeit>=? ORDER BY zeit",
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


def shop_status_alle() -> dict[str, dict]:
    with connect() as con:
        return {r["shop"]: dict(r) for r in con.execute("SELECT * FROM shop_status").fetchall()}

