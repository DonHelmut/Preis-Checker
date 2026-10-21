from __future__ import annotations

import argparse
import logging

from . import notify, runner
from .config import load_config


def _ausgabe(ergebnis: dict) -> None:
    if ergebnis["kategorie"].startswith("produkt:"):
        ziel = f" (Ziel {ergebnis['zielpreis']:.2f} €)" if ergebnis.get("zielpreis") else ""
        print(f"\n== {ergebnis['suche']}{ziel} ==")
        if ergebnis.get("fehler"):
            print(f"Hinweis: {ergebnis['fehler']}")
        for a in ergebnis["angebote"][:8]:
            print(f"  {a['preis']:>9.2f} €  {a['shop']:<12} {a['name'][:70]}")
        return
    akt = ergebnis["aktuell"]
    print(f"\n== {ergebnis['kategorie'].upper()} ==")
    print(f"Aktuell: {akt.get('anbieter')} {akt.get('tarif') or ''}: {akt['kosten_jahr']:.2f} €/Jahr")
    if akt.get("kuendigen_bis"):
        print(f"Kündigen bis: {akt['kuendigen_bis']}")
    if ergebnis.get("fehler"):
        print(f"FEHLER: {ergebnis['fehler']}")
    for a in ergebnis["angebote"][:10]:
        print(f"  {a['kosten_jahr']:>9.2f} €/Jahr  {a['ersparnis_jahr']:>+8.2f}  {a['anbieter']} {a.get('tarif') or ''}")


def main() -> None:
    p = argparse.ArgumentParser(prog="preischecker", description="Strom-/Internet-Verträge mit Check24 vergleichen")
    p.add_argument("-c", "--config", default=None, help="Pfad zur config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("pruefen", help="Einmal prüfen und Ergebnis ausgeben")
    run.add_argument("kategorie", nargs="*", choices=["strom", "internet", "produkte"])
    dbg = sub.add_parser("debug", help="Prüfen und Seite/Kacheln nach data/debug/ speichern")
    dbg.add_argument("kategorie", nargs="*", choices=["strom", "internet", "produkte"])
    srv = sub.add_parser("serve", help="Weboberfläche + regelmäßige Prüfung")
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8080)
    srv.add_argument("--ohne-scheduler", action="store_true")
    sub.add_parser("test-benachrichtigung", help="Testnachricht an alle konfigurierten Kanäle")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)

    if args.cmd in ("pruefen", "debug"):
        for e in runner.pruefen(cfg, args.kategorie or None, debug=args.cmd == "debug"):
            _ausgabe(e)
    elif args.cmd == "serve":
        from .web import serve
        serve(args.config, args.host, args.port, not args.ohne_scheduler)
    elif args.cmd == "test-benachrichtigung":
        cfg["pruefung"]["benachrichtigen_ab_euro_jahr"] = 0
        notify.senden(cfg, {
            "kategorie": "test", "beste_ersparnis_jahr": 123.0,
            "aktuell": {"anbieter": "Alt", "kosten_jahr": 1000.0},
            "angebote": [{"anbieter": "Neu", "tarif": "Test", "kosten_jahr": 877.0, "ersparnis_jahr": 123.0}],
        })
        print("Gesendet (Fehler siehe Log).")


if __name__ == "__main__":
    main()
