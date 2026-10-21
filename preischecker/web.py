from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, url_for

from . import db, runner
from .config import DATA_DIR, load_config

log = logging.getLogger(__name__)


def create_app(config_path=None) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        cfg = load_config(config_path)
        daten = {}
        for kat in ("strom", "internet"):
            if cfg[kat].get("aktiv"):
                daten[kat] = {"letzte": db.letzte(kat), "verlauf": db.verlauf(kat)}
        produkte = []
        if cfg["produkte"].get("aktiv"):
            for artikel in cfg["produkte"].get("liste") or []:
                kat = f"produkt:{artikel['suche']}"
                verlauf = [v["bestes_jahr"] for v in db.verlauf(kat, 365) if v["bestes_jahr"] is not None]
                produkte.append({"artikel": artikel, "letzte": db.letzte(kat),
                                 "tiefst": min(verlauf) if verlauf else None})
        return render_template("index.html", daten=daten, produkte=produkte, laeuft=runner.laeuft(),
                               version=version_info())

    @app.post("/pruefen")
    def pruefen():
        cfg = load_config(config_path)
        threading.Thread(target=runner.pruefen, args=(cfg,), daemon=True).start()
        return redirect(url_for("index"))

    @app.get("/api/status")
    def status():
        cfg = load_config(config_path)
        produkte = {}
        for artikel in cfg["produkte"].get("liste") or []:
            e = db.letzte(f"produkt:{artikel['suche']}") or {}
            best = (e.get("angebote") or [{}])[0]
            produkte[artikel["suche"]] = {
                "bester_preis": e.get("bester_preis"), "shop": best.get("shop"), "name": best.get("name"),
                "url": best.get("url"),
                "anzeige": f"{best['preis']:.2f}".replace(".", ",") + f" € bei {best['shop']}" if best else None,
                "aktion": best.get("aktion", False), "alter_preis": best.get("alter_preis"),
                "rabatt_prozent": best.get("rabatt_prozent"),
                "zielpreis": artikel.get("zielpreis"), "ziel_erreicht": e.get("ziel_erreicht", False),
                "schnaeppchen": e.get("schnaeppchen", False), "gruende": e.get("gruende") or [],
                "durchschnitt": e.get("durchschnitt"), "zeit": e.get("zeit"), "fehler": e.get("fehler"),
                "top": [{k: a.get(k) for k in ("preis", "shop", "name", "url", "aktion")}
                        for a in (e.get("angebote") or [])[:5]],
            }
        return jsonify({kat: db.letzte(kat) for kat in ("strom", "internet")}
                       | {"produkte": produkte, "laeuft": runner.laeuft()})

    @app.post("/api/update")
    def update_anfordern():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "update.status").write_text("angefordert", encoding="utf-8")
        (DATA_DIR / "update.request").write_text(datetime.now().isoformat(), encoding="utf-8")
        if request.accept_mimetypes.accept_html and not request.is_json:
            return redirect(url_for("index"))
        return jsonify({"update": "angefordert"})

    @app.get("/api/update/status")
    def update_status():
        return (_lesen("update.status") or "unbekannt"), 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.get("/api/version")
    def version():
        return jsonify(version_info())

    return app


def _lesen(name: str) -> str | None:
    try:
        return (DATA_DIR / name).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def version_info() -> dict:
    return {"version": _lesen("version.txt"), "update": _lesen("update.status")}


def scheduler(config_path=None) -> None:
    while True:
        cfg = load_config(config_path)
        try:
            runner.pruefen(cfg)
        except Exception:
            log.exception("Geplante Prüfung fehlgeschlagen")
        time.sleep(float(cfg["pruefung"].get("intervall_stunden", 24)) * 3600)


def serve(config_path=None, host="0.0.0.0", port=8080, mit_scheduler=True) -> None:
    if mit_scheduler:
        threading.Thread(target=scheduler, args=(config_path,), daemon=True).start()
    create_app(config_path).run(host=host, port=port)
