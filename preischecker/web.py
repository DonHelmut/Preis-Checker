from __future__ import annotations

import logging
import threading
import time

from flask import Flask, jsonify, redirect, render_template, url_for

from . import db, runner
from .config import load_config

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
        return render_template("index.html", daten=daten, laeuft=runner.laeuft())

    @app.post("/pruefen")
    def pruefen():
        cfg = load_config(config_path)
        threading.Thread(target=runner.pruefen, args=(cfg,), daemon=True).start()
        return redirect(url_for("index"))

    @app.get("/api/status")
    def status():
        return jsonify({kat: db.letzte(kat) for kat in ("strom", "internet")} | {"laeuft": runner.laeuft()})

    return app


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
