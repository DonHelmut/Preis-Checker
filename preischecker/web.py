from __future__ import annotations

import logging
import multiprocessing
import threading
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for

from . import ansicht, ha, notify, runner, settings, worker
from .sources import shops as shops_modul
from .config import DATA_DIR, load_config, load_raw, save_raw
from .sources.shops import GRUPPEN_NAMEN, KATEGORIEN, SHOP_LISTE, SHOPS, anbieter, shop_name
from .status import status_daten

log = logging.getLogger(__name__)
SUCHEN: dict[str, dict] = {}  # Schnellsuchen im Speicher, neueste zuletzt
DIAGNOSEN: dict[str, dict] = {}


class IngressPrefix:
    """Home-Assistant-Ingress: Pfad-Präfix aus X-Ingress-Path übernehmen."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_INGRESS_PATH")
        if prefix:
            environ["SCRIPT_NAME"] = prefix.rstrip("/")
        return self.app(environ, start_response)


# ---------- Formatierung für Templates ----------

def eur(wert, nachkomma: int = 2) -> str:
    if wert is None:
        return "–"
    s = f"{wert:,.{nachkomma}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def prozent(wert, vorzeichen: bool = True) -> str:
    if wert is None:
        return "–"
    s = f"{wert:+.1f}" if vorzeichen else f"{wert:.1f}"
    return s.replace(".", ",").replace("-", "−") + " %"


def zeit_rel(z) -> str:
    if not z:
        return "noch nie"
    t = z if isinstance(z, datetime) else datetime.fromisoformat(str(z))
    d = datetime.now() - t
    if d < timedelta(seconds=0):
        d = -d
        if d < timedelta(minutes=1):
            return "gleich"
        if d < timedelta(hours=1):
            return f"in {int(d.total_seconds() // 60)} Min."
        return "in " + f"{d.total_seconds() / 3600:.1f}".replace(".", ",") + " Std."
    if d < timedelta(minutes=1):
        return "gerade eben"
    if d < timedelta(hours=1):
        return f"vor {int(d.total_seconds() // 60)} Min."
    if d < timedelta(days=1):
        return f"vor {int(d.total_seconds() // 3600)} Std."
    if d < timedelta(days=30):
        return f"vor {d.days} Tag{'en' if d.days > 1 else ''}"
    return t.strftime("%d.%m.%Y")


def datum(z) -> str:
    if not z:
        return "–"
    t = datetime.fromisoformat(str(z))
    return t.strftime("%d.%m.%Y") if len(str(z)) <= 10 else t.strftime("%d.%m.%Y %H:%M")


def create_app(config_path=None) -> Flask:
    app = Flask(__name__)
    app.wsgi_app = IngressPrefix(app.wsgi_app)
    app.jinja_env.globals.update(get=settings.get, anzeigen=settings.anzeigen, shop_name=shop_name, anbieter=anbieter,
                                 KATEGORIEN=KATEGORIEN)
    app.jinja_env.filters.update(eur=eur, prozent=prozent, zeit_rel=zeit_rel, datum=datum)

    def basis_daten() -> dict:
        return {"fortschritt": runner.FORTSCHRITT.als_dict(), "addon": ha.aktiv(), "version": version_info(),
                "naechste": runner.NAECHSTE_PRUEFUNG["zeit"]}

    # ---------- Seiten ----------

    @app.get("/")
    def index():
        cfg = load_config(config_path)
        karten = [ansicht.produkt_karte(cfg, a) for a in cfg["produkte"].get("liste") or []] \
            if cfg["produkte"].get("aktiv") else []
        vertraege = [v for v in (ansicht.vertrag_karte(cfg, k) for k in ("strom", "internet")) if v]
        zeiten = [k["letzte"].get("zeit") for k in karten if k["letzte"].get("zeit")]
        zeiten += [v["letzte"]["zeit"] for v in vertraege if v["letzte"]]
        return render_template(
            "index.html", seite="index", karten=karten, vertraege=vertraege,
            shops=ansicht.shop_uebersicht(cfg), letzte_pruefung=max(zeiten) if zeiten else None,
            schnaeppchen=sum(1 for k in karten if k["letzte"].get("schnaeppchen") or k["letzte"].get("ziel_erreicht")),
            **basis_daten())

    @app.get("/produkt/<s>")
    def produkt(s):
        cfg = load_config(config_path)
        artikel = ansicht.artikel_nach_slug(cfg, s)
        if not artikel:
            abort(404)
        return render_template("produkt.html", seite="index", d=ansicht.produkt_detail(cfg, artikel), **basis_daten())

    @app.post("/produkt/<s>/ziel")
    def produkt_ziel(s):
        cfg = load_raw(config_path)
        artikel = next((a for a in (cfg.get("produkte") or {}).get("liste") or [] if ha.slug(a["suche"]) == s), None)
        if artikel is None:
            abort(404)
        for f in ("zielpreis", "min_preis"):
            if f in request.form:
                try:
                    wert = settings._zahl(request.form[f], "float")
                except ValueError:
                    continue
                if wert:
                    artikel[f] = wert
                else:
                    artikel.pop(f, None)
        if request.form.get("kategorie") in KATEGORIEN:
            artikel["kategorie"] = request.form["kategorie"]
        save_raw(cfg, config_path)
        return redirect(url_for("produkt", s=s))

    @app.post("/produkt/<s>/entfernen")
    def produkt_entfernen(s):
        cfg = load_raw(config_path)
        p = cfg.get("produkte") or {}
        p["liste"] = [a for a in p.get("liste") or [] if ha.slug(a["suche"]) != s]
        save_raw(cfg, config_path)
        return redirect(url_for("index"))

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

    @app.post("/test-benachrichtigung")
    def test_benachrichtigung():
        cfg = load_raw(config_path)
        fehler = settings.uebernehmen(cfg, request.form)
        if fehler:
            return einstellungen_seite(cfg, fehler=fehler), 400
        save_raw(cfg, config_path)
        notify.test(load_config(config_path))
        return einstellungen_seite(load_raw(config_path), test=True)

    def einstellungen_seite(cfg, **extra):
        extra.setdefault("fehler", [])
        gruppen = {}
        for s in SHOP_LISTE:
            gruppen.setdefault(GRUPPEN_NAMEN[s.gruppen[0]], []).append(s)
        aktiv = list(ansicht.aktive_shops(load_config(config_path)))
        return render_template("einstellungen.html", seite="einstellungen", cfg=cfg, abschnitte=settings.ABSCHNITTE,
                               shop_gruppen=gruppen, aktive_quellen=aktiv, ha_dienste=ha.notify_dienste(),
                               gewaehlte_dienste=notify.ha_dienste(cfg.get("benachrichtigung") or {}),
                               **basis_daten(), **extra)

    @app.post("/pruefen")
    def pruefen():
        cfg = load_config(config_path)
        threading.Thread(target=runner.pruefen, args=(cfg,), daemon=True).start()
        time.sleep(0.3)  # damit die Seite den Lauf schon anzeigt
        return redirect(url_for("index"))

    # ---------- Schnellsuche ----------

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
        if request.form.get("kategorie") in KATEGORIEN:
            artikel["kategorie"] = request.form["kategorie"]
        sid = uuid.uuid4().hex[:10]
        fortschritt = runner.Fortschritt()
        SUCHEN[sid] = {"artikel": artikel, "status": "laeuft", "start": datetime.now(), "fortschritt": fortschritt}
        while len(SUCHEN) > 20:
            SUCHEN.pop(next(iter(SUCHEN)))
        cfg = load_config(config_path)

        def lauf():
            try:
                SUCHEN[sid]["ergebnis"] = runner.schnellsuche(cfg, artikel, fortschritt)
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
        return render_template("suche.html", seite="suche", s=s, sid=sid,
                               sf=s["fortschritt"].als_dict(), **basis_daten())

    @app.get("/api/suche/<sid>")
    def suche_status(sid):
        s = SUCHEN.get(sid)
        if not s:
            abort(404)
        return jsonify({"status": s["status"], "fortschritt": s["fortschritt"].als_dict()})

    @app.post("/beobachten")
    def beobachten():
        q = request.form.get("q", "").strip()
        if not q:
            return redirect(url_for("index"))
        cfg = load_raw(config_path)
        produkte = cfg.get("produkte") or {}
        cfg["produkte"] = produkte
        liste = produkte.get("liste") or []
        produkte["liste"] = liste
        produkte["aktiv"] = True
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
        if request.form.get("kategorie") in KATEGORIEN:
            artikel["kategorie"] = request.form["kategorie"]
        save_raw(cfg, config_path)
        return redirect(url_for("produkt", s=ha.slug(artikel["suche"])))

    # ---------- API ----------

    @app.get("/api/fortschritt")
    def fortschritt():
        return jsonify(runner.FORTSCHRITT.als_dict() | {"laeuft": runner.laeuft()})

    @app.get("/api/status")
    def status():
        return jsonify(status_daten(load_config(config_path)) | {"laeuft": runner.laeuft()})

    @app.get("/api/produkt/<s>")
    def api_produkt(s):
        cfg = load_config(config_path)
        artikel = ansicht.artikel_nach_slug(cfg, s)
        if not artikel:
            abort(404)
        d = ansicht.produkt_detail(cfg, artikel)
        return jsonify({"artikel": artikel, "kennzahlen": d["k"], "shops": d["vergleich"], "chart": d["chart"]})

    @app.get("/api/shops")
    def api_shops():
        return jsonify(ansicht.shop_uebersicht(load_config(config_path)))

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

    @app.post("/api/pruefen")
    def api_pruefen():
        if runner.laeuft():
            return jsonify({"gestartet": False, "grund": "läuft bereits"})
        threading.Thread(target=runner.pruefen, args=(load_config(config_path),), daemon=True).start()
        return jsonify({"gestartet": True})

    @app.get("/api/diagnose")
    def api_diagnose():
        """Einen Shop live durchsuchen (im Hintergrund) und jedes erkannte Angebot mit Filter-Ergebnis zeigen.

        Antwort: {"id": …}; Ergebnis unter /api/diagnose/<id> abholen.
        """
        cfg = load_config(config_path)
        shop, q = request.args.get("shop", ""), request.args.get("q", "").strip()
        urls = ansicht.aktive_shops(cfg) | {k: v.url for k, v in SHOPS.items()}
        if request.args.get("url"):  # andere Such-URL ausprobieren, {q}/{p} = Suchbegriff
            urls[shop] = request.args["url"]
        if shop not in urls or not q:
            return jsonify({"fehler": "shop und q angeben", "shops": sorted(urls)}), 400
        artikel = next((a for a in cfg["produkte"].get("liste") or [] if a["suche"].lower() == q.lower()), {"suche": q})
        did = uuid.uuid4().hex[:10]
        DIAGNOSEN[did] = {"status": "laeuft", "shop": shop, "suche": q, "artikel": artikel}
        while len(DIAGNOSEN) > 20:
            DIAGNOSEN.pop(next(iter(DIAGNOSEN)))

        def lauf():
            try:
                with ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn")) as pool:
                    _, _, gefunden, fehler, dauer = pool.submit(
                        worker.auftrag, cfg, q, shop, urls[shop], True, artikel).result(timeout=240)
                neuester = max((DATA_DIR / "debug").glob(f"{shop}-*"), key=lambda p: p.stat().st_mtime, default=None)
                DIAGNOSEN[did] |= {
                    "status": "fertig", "fehler": fehler, "dauer": round(dauer, 1),
                    "seite": {"titel": _seitentitel(neuester / "seite.html"), "url": _lesen_datei(neuester / "url.txt"),
                              "kacheln": (_lesen_datei(neuester / "kacheln.txt") or "")[:3000]} if neuester else None,
                    "angebote": [{"name": a.name, "preis": a.preis, "lieferbar": a.lieferbar, "url": a.url,
                                  "haendler": a.haendler, "grund": shops_modul.ablehnungsgrund(a, artikel)}
                                 for a in gefunden]}
            except Exception as e:
                DIAGNOSEN[did] |= {"status": "fehler", "fehler": f"{type(e).__name__}: {e}"}

        threading.Thread(target=lauf, daemon=True).start()
        return jsonify({"id": did})

    @app.get("/api/diagnose/<did>")
    def api_diagnose_ergebnis(did):
        if did not in DIAGNOSEN:
            abort(404)
        return jsonify(DIAGNOSEN[did])

    @app.get("/api/debug")
    def api_debug():
        basis = DATA_DIR / "debug"
        if not basis.exists():
            return jsonify([])
        out = []
        for d in sorted(basis.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:40]:
            out.append({"name": d.name, "url": _lesen_datei(d / "url.txt"),
                        "kacheln": (_lesen_datei(d / "kacheln.txt") or "")[:4000],
                        "titel": _seitentitel(d / "seite.html")})
        return jsonify(out)

    @app.get("/api/debug/<name>/<datei>")
    def api_debug_datei(name, datei):
        if datei not in ("seite.png", "seite.html", "kacheln.txt", "url.txt") or "/" in name or ".." in name:
            abort(404)
        pfad = DATA_DIR / "debug" / name / datei
        if not pfad.exists():
            abort(404)
        return send_file(pfad.resolve())

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


def _lesen_datei(pfad: Path) -> str | None:
    try:
        return pfad.read_text(encoding="utf-8")
    except OSError:
        return None


def _seitentitel(pfad: Path) -> str | None:
    html = _lesen_datei(pfad) or ""
    a, b = html.find("<title"), html.find("</title>")
    if a < 0 or b < 0:
        return None
    return html[html.find(">", a) + 1:b].strip()[:200]


def _lesen(name: str) -> str | None:
    try:
        return (DATA_DIR / name).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def version_info() -> dict:
    return {"version": _lesen("version.txt"), "update": _lesen("update.status")}


def scheduler(config_path=None) -> None:
    while True:
        try:
            runner.pruefen(load_config(config_path))
        except Exception:
            log.exception("Geplante Prüfung fehlgeschlagen")
        intervall = float(load_config(config_path)["pruefung"].get("intervall_stunden", 24)) * 3600
        runner.NAECHSTE_PRUEFUNG["zeit"] = datetime.now() + timedelta(seconds=intervall)
        time.sleep(intervall)


def serve(config_path=None, host="0.0.0.0", port=8080, mit_scheduler=True) -> None:
    if mit_scheduler:
        threading.Thread(target=scheduler, args=(config_path,), daemon=True).start()
    if ha.aktiv():
        threading.Thread(target=ha.sync_schleife, args=(config_path,), daemon=True).start()
    create_app(config_path).run(host=host, port=port, threaded=True)
