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
                angebote[0]["kosten_jahr"] if angebote else None,
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
