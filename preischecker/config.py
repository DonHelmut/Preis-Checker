from __future__ import annotations

import os
from pathlib import Path

import yaml

DEFAULT_PATH = Path(os.environ.get("PREISCHECKER_CONFIG", "config.yaml"))
DATA_DIR = Path(os.environ.get("PREISCHECKER_DATA", "data"))


def load_config(path: Path | str | None = None) -> dict:
    path = Path(path or DEFAULT_PATH)
    if not path.exists():
        raise SystemExit(f"Config fehlt: {path} (Vorlage: config.example.yaml)")
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("standort", {})
    cfg.setdefault("pruefung", {})
    cfg.setdefault("benachrichtigung", {})
    cfg.setdefault("browser", {})
    for key in ("strom", "internet"):
        cfg.setdefault(key, {"aktiv": False})
        cfg[key].setdefault("filter", {})
    cfg.setdefault("produkte", {"aktiv": False})
    return cfg
