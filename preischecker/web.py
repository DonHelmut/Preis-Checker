from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, url_for

from . import db, ha, notify, runner, settings
from .status import status_daten
from .config import DATA_DIR, load_config, load_raw, save_raw

log = logging.getLogger(__name__)
SUCHEN: dict[str, dict] = {}  # Schnellsuchen im Speicher, neueste zuletzt


class IngressPrefix:
    """Home-Assistant-Ingress: Pfad-Präfix aus X-Ingress-Path übernehmen."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_INGRESS_PATH")
        if prefix:
            environ["SCRIPT_NAME"] = prefix.rstrip("/")
        return self.app(environ, start_response)


def create_app(config_path=None) -> Flask:
    app = Flask(__name__)
    app.wsgi_app = IngressPrefix(app.wsgi_app)
    app.jinja_env.globals.update(get=settings.get, anzeigen=settings.anzeigen)

    def einstellungen_seite(cfg, **extra):
        extra.setdefault("fehler", [])
        return render_template("einstellungen.html", cfg=cfg, abschnitte=settings.ABSCHNITTE,
                               quellen=settings.QUELLEN, ha_dienste=ha.notify_dienste(),
                               gewaehlte_dienste=notify.ha_dienste(cfg.get("benachrichtigung") or {}), **extra)

    @app.get("/einstellungen")
    def einstellungen():
        return einstellungen_seite(load_raw(config_path), gespeichert=request.args.get("ok") == "1")

    @app.post("/einstellungen")
    def einstellungen_speichern():
        cfg = load_raw(config_path)
        fehler = settings.uebernehmen(cfg, request.form)
        if fehler:
            return einstellungen_seite(cfg, fehler=fehler), 400
        save_raw(cfg, config_path)
        return redirect(url_for("einstellungen", ok=1))

    @app.get("/api/einstellungen")
    def api_einstellungen():
        cfg = load_raw(config_path)
        n = cfg.get("benachrichtigung") or {}
        if n.get("telegram_bot_token"):
            n["telegram_bot_token"] = "***"
        return jsonify(cfg)

    @app.post("/api/einstellungen")
    def api_einstellungen_setzen():
        """JSON wird in die Config gemischt (verschachtelte Abschnitte einzeln, Listen ersetzt)."""
        neu = request.get_json(force=True, silent=True)
        if not isinstance(neu, dict):
            return jsonify({"fehler": "JSON-Objekt erwartet"}), 400
        cfg = load_raw(config_path)
        _mischen(cfg, neu)
        save_raw(cfg, config_path)
        return jsonify(cfg)

    @app.post("/test-benachrichtigung")
    def test_benachrichtigung():
        cfg = load_raw(config_path)
        fehler = settings.uebernehmen(cfg, request.form)
        if fehler:
            return einstellungen_seite(cfg, fehler=fehler), 400
        save_raw(cfg, config_path)
        notify.test(load_config(config_path))
        return einstellungen_seite(load_raw(config_path), test=True)

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
                               version=version_info(), addon=ha.aktiv())

    @app.post("/suche")
    def suche_starten():
        q = request.form.get("q", "").strip()
        if not q:
            return redirect(url_for("index"))
        artikel = {"suche": q}
        try:
            min_preis = settings._zahl(request.form.get("min_preis", ""), "float")
        except ValueError:
            min_preis = None
        if min_preis:
            artikel["min_preis"] = min_preis
        sid = uuid.uuid4().hex[:10]
        SUCHEN[sid] = {"artikel": artikel, "status": "laeuft", "start": datetime.now()}
        while len(SUCHEN) > 20:
            SUCHEN.pop(next(iter(SUCHEN)))
        cfg = load_config(config_path)

        def lauf():
            try:
                SUCHEN[sid]["ergebnis"] = runner.schnellsuche(cfg, artikel)
                SUCHEN[sid]["status"] = "fertig"
            except Exception as e:
                log.exception("Schnellsuche fehlgeschlagen")
                SUCHEN[sid] |= {"status": "fehler", "fehler": f"{type(e).__name__}: {e}"}

        threading.Thread(target=lauf, daemon=True).start()
        return redirect(url_for("suche_anzeigen", sid=sid))

    @app.get("/suche/<sid>")
    def suche_anzeigen(sid):
        s = SUCHEN.get(sid)
        if not s:
            return redirect(url_for("index"))
        return render_template("suche.html", s=s, sid=sid)

    @app.post("/beobachten")
    def beobachten():
        q = request.form.get("q", "").strip()
        if q:
            cfg = load_raw(config_path)
            liste = cfg.setdefault("produkte", {}).setdefault("liste", []) or []
            cfg["produkte"]["liste"] = liste
            cfg["produkte"]["aktiv"] = True
            artikel = next((a for a in liste if a.get("suche", "").lower() == q.lower()), None)
            if artikel is None:
                artikel = {"suche": q}
                liste.append(artikel)
            for f in ("zielpreis", "min_preis"):
                try:
                    wert = settings._zahl(request.form.get(f, ""), "float")
                except ValueError:
                    wert = None
                if wert:
                    artikel[f] = wert
            save_raw(cfg, config_path)
        return redirect(url_for("index"))

    @app.post("/pruefen")
    def pruefen():
        cfg = load_config(config_path)
        threading.Thread(target=runner.pruefen, args=(cfg,), daemon=True).start()
        return redirect(url_for("index"))

    @app.get("/api/status")
    def status():
        return jsonify(status_daten(load_config(config_path)) | {"laeuft": runner.laeuft()})

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


def _mischen(ziel: dict, neu: dict) -> None:
    for k, v in neu.items():
        if isinstance(v, dict) and isinstance(ziel.get(k), dict):
            _mischen(ziel[k], v)
        elif v is None:
            ziel.pop(k, None)
        else:
            ziel[k] = v


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
    if ha.aktiv():
        threading.Thread(target=ha.sync_schleife, args=(config_path,), daemon=True).start()
    create_app(config_path).run(host=host, port=port)
