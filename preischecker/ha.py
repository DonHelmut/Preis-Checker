"""Home-Assistant-Anbindung, wenn als Add-on gestartet (SUPERVISOR_TOKEN vorhanden).

Legt Sensoren automatisch an (sensor.preischecker_*) und kann HA-Benachrichtigungsdienste aufrufen.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request

from .config import load_config
from .status import status_daten

log = logging.getLogger(__name__)
API = "http://supervisor/core/api"


def aktiv() -> bool:
    return bool(os.environ.get("SUPERVISOR_TOKEN"))


def _post(pfad: str, daten: dict) -> None:
    req = urllib.request.Request(
        API + pfad, data=json.dumps(daten).encode(), method="POST",
        headers={"Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}", "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=15).read()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower().replace("ä", "ae").replace("ö", "oe")
                  .replace("ü", "ue").replace("ß", "ss")).strip("_")


def sensoren(cfg: dict) -> list[tuple[str, object, dict]]:
    daten = status_daten(cfg)
    out = []
    for suche, p in daten["produkte"].items():
        attrs = {k: v for k, v in p.items() if k != "bester_preis"}
        attrs |= {"friendly_name": f"{suche} bester Preis", "unit_of_measurement": "€",
                  "icon": "mdi:tag-heart" if p["schnaeppchen"] else "mdi:tag", "device_class": "monetary"}
        out.append((f"sensor.preischecker_{slug(suche)}", p["bester_preis"] if p["bester_preis"] is not None else "unknown", attrs))
    for kat, name in (("strom", "Strom"), ("internet", "Internet")):
        e = daten.get(kat)
        if not e or not cfg[kat].get("aktiv"):
            continue
        best = (e.get("angebote") or [{}])[0]
        attrs = {"friendly_name": f"{name} Ersparnis", "unit_of_measurement": "€/Jahr", "icon": "mdi:piggy-bank",
                 "aktuell_kosten_jahr": e["aktuell"].get("kosten_jahr"), "kuendigen_bis": e["aktuell"].get("kuendigen_bis"),
                 "bester_anbieter": best.get("anbieter"), "bester_tarif": best.get("tarif"),
                 "bester_kosten_jahr": best.get("kosten_jahr"), "zeit": e.get("zeit"), "fehler": e.get("fehler")}
        wert = e.get("beste_ersparnis_jahr")
        out.append((f"sensor.preischecker_{kat}_ersparnis", wert if wert is not None else "unknown", attrs))
    return out


def sync(cfg: dict) -> None:
    if not aktiv():
        return
    for entity_id, state, attrs in sensoren(cfg):
        try:
            _post(f"/states/{entity_id}", {"state": state, "attributes": attrs})
        except Exception as e:
            log.warning("HA-Sensor %s: %s", entity_id, e)


def sync_schleife(config_path=None) -> None:
    """Sensoren regelmäßig neu setzen (gehen sonst nach HA-Neustart verloren)."""
    while True:
        try:
            sync(load_config(config_path))
        except Exception:
            log.exception("HA-Sync fehlgeschlagen")
        time.sleep(600)


def benachrichtigen(dienst: str, text: str) -> None:
    domain, _, service = dienst.partition(".")
    _post(f"/services/{domain}/{service}", {"title": "Preis-Checker", "message": text})
