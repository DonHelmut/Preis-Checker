from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml

DEFAULT_PATH = Path(os.environ.get("PREISCHECKER_CONFIG", "config.yaml"))
DATA_DIR = Path(os.environ.get("PREISCHECKER_DATA", "data"))
EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "config.example.yaml"


def load_raw(path: Path | str | None = None) -> dict:
    """Config wie in der Datei (ohne Defaults). Legt sie beim ersten Start aus der Vorlage an."""
    path = Path(path or DEFAULT_PATH)
    if not path.exists():
        if not EXAMPLE_PATH.exists():
            raise SystemExit(f"Config fehlt: {path} (Vorlage: config.example.yaml)")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(EXAMPLE_PATH, path)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_raw(cfg: dict, path: Path | str | None = None) -> None:
    path = Path(path or DEFAULT_PATH)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    tmp.replace(path)


def load_config(path: Path | str | None = None) -> dict:
    cfg = load_raw(path)
    cfg.setdefault("standort", {})
    cfg.setdefault("pruefung", {})
    n = cfg.setdefault("benachrichtigung", {})
    for k, v in (("ruhezeit", True), ("ruhe_von", "22:00"), ("ruhe_bis", "07:00"), ("ruhe_nachholen", True)):
        n.setdefault(k, v)
    cfg.setdefault("browser", {})
    for key in ("strom", "internet"):
        cfg.setdefault(key, {"aktiv": False})
        cfg[key].setdefault("filter", {})
    p = cfg.setdefault("produkte", {"aktiv": False})
    p.setdefault("sperre_pause_stunden", 24)
    p.setdefault("empfindlich_abstand_stunden", 20)
    p.setdefault("haendler_ausschliessen", ["ebay", "kleinanzeigen"])
    return cfg
