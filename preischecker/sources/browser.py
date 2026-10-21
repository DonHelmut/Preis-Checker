"""Playwright-Hilfen: Browser starten, Cookie-Banner wegklicken, Ergebnisliste finden."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from ..config import DATA_DIR

# Findet wiederholte Kacheln: Elemente mit Preis + Stichwort, die als
# Geschwister unter demselben Eltern-Element liegen. Liefert deren innerText.
FIND_CARDS_JS = r"""
({keyword, minLen}) => {
  const kw = new RegExp(keyword, 'i');
  const price = /(\d+[.,]\d{2}\s*€|€\s*\d+[.,]\d{2}|\d+[,.][-–])/;
  const els = Array.from(document.querySelectorAll('body *'));
  const cand = new Set();
  for (const el of els) {
    const t = el.innerText || '';
    if (t.length < minLen || t.length > 4000) continue;
    if (!price.test(t) || !kw.test(t)) continue;
    cand.add(el);
  }
  const byParent = new Map();
  for (const el of cand) {
    const p = el.parentElement;
    if (!p) continue;
    byParent.set(p, (byParent.get(p) || []).concat([el]));
  }
  let best = [];
  for (const kids of byParent.values()) {
    if (kids.length > best.length) best = kids;
  }
  if (best.length < 2) return [];
  return best.map(e => {
    const a = e.tagName === 'A' ? e : e.querySelector('a[href]');
    // Händler-Logos (Preisvergleiche zeigen den Shop oft nur als Bild)
    const bilder = Array.from(e.querySelectorAll('img[alt], [title]'))
      .map(x => x.getAttribute('alt') || x.getAttribute('title') || '')
      .filter(x => x && x.length < 60).slice(0, 8);
    return {text: e.innerText, href: a ? a.href : '', bilder};
  });
}
"""

# Zustimmungs-Buttons in Cookie-Bannern („Alle akzeptieren“, „Geht klar“ (Check24), „Zustimmen“ …)
COOKIE_BUTTONS = re.compile(r"^\W*((alle|alles)\s+)?((cookies?|auswahl)\s+)?(akzeptieren|annehmen|zulassen|erlauben)\W*$"
                            r"|^\W*(geht klar|zustimmen|alle zustimmen|einverstanden|verstanden|ok|okay|accept all)\W*$", re.I)
_COOKIE_CONTAINER = "[class*='cookie' i], [id*='cookie' i], [class*='consent' i], [id*='consent' i], [id*='usercentrics' i]"


@contextmanager
def browser_page(cfg: dict):
    bcfg = cfg.get("browser", {})
    with sync_playwright() as p:
        exe = os.environ.get("PREISCHECKER_CHROMIUM")
        browser = p.chromium.launch(
            # Volles Chromium im neuen Headless-Modus: von Bot-Schutz (Cloudflare & Co.) schwerer zu erkennen
            channel=None if exe else "chromium",
            executable_path=exe or None,
            headless=bcfg.get("headless", True),
            args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
        )
        haupt = browser.version.split(".")[0]
        ctx = browser.new_context(
            # Zur echten Browser-Version passend, ohne "HeadlessChrome"
            user_agent=f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                       f"Chrome/{haupt}.0.0.0 Safari/537.36",
            locale="de-DE",
            timezone_id="Europe/Berlin",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.6"},
        )
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = ctx.new_page()
        page.set_default_timeout(bcfg.get("timeout_sekunden", 60) * 1000)
        page._json_responses = []  # type: ignore[attr-defined]

        def on_response(resp):
            if "json" in (resp.headers.get("content-type") or ""):
                try:
                    page._json_responses.append({"url": resp.url, "body": resp.json()})  # type: ignore[attr-defined]
                except Exception:
                    pass

        page.on("response", on_response)
        try:
            yield page
        finally:
            browser.close()


_SCHUTZSEITE = re.compile(r"nur einen moment|just a moment|attention required|checking your browser|bot detected|human verification"
                          r"|verify you are human|pardon our interruption"
                          r"|access denied|zugriff verweigert|captcha|sicherheitsüberprüfung", re.I)


# Captcha-Seiten ohne eindeutigen Titel (z. B. Turnstile-Formular). Captchas werden nie gelöst,
# der Shop gilt dann als gesperrt und wird eine Weile pausiert.
_CAPTCHA_SELEKTOR = ".cf-turnstile, #captcha_form, iframe[src*='captcha'], iframe[src*='challenges.cloudflare.com']"


def schutzseite_abwarten(page: Page, sekunden: int = 20) -> bool:
    """Wartet, bis eine Bot-Schutz-Zwischenseite (z. B. Cloudflare) von selbst weiterleitet.

    Liefert False, wenn die Schutzseite bleibt.
    """
    ende = time.time() + sekunden
    while time.time() < ende:
        try:
            if not _SCHUTZSEITE.search(page.title() or "") and not page.locator(_CAPTCHA_SELEKTOR).count():
                return True
        except Exception:
            pass
        page.wait_for_timeout(1000)
    return False


def accept_cookies(page: Page, warten_s: float = 1.5) -> bool:
    """Cookie-Banner wegklicken. Wartet kurz, weil viele Banner erst nach dem Laden erscheinen."""
    ende = time.time() + warten_s
    while True:
        for frame in [page.main_frame, *page.frames]:
            try:
                kandidaten = [frame.get_by_role("button", name=COOKIE_BUTTONS),
                              frame.locator(_COOKIE_CONTAINER).locator("button, a, [role=button]")
                              .filter(has_text=COOKIE_BUTTONS)]
                for btn in kandidaten:
                    for i in range(min(btn.count(), 3)):
                        if btn.nth(i).is_visible():
                            btn.nth(i).click(timeout=3000)
                            page.wait_for_timeout(500)
                            return True
            except Exception:
                continue
        if time.time() >= ende:
            return False
        page.wait_for_timeout(500)


def _editierbar(loc) -> bool:
    try:
        return loc.is_visible() and loc.evaluate(
            "e => ['INPUT', 'TEXTAREA'].includes(e.tagName) || e.isContentEditable")
    except Exception:
        return False


def _erstes_feld(page: Page, rx: re.Pattern, patterns: list[str]):
    kandidaten = [page.get_by_label(rx), page.get_by_placeholder(rx)]
    kandidaten += [page.locator(f"input[name*='{n}' i], input[id*='{n}' i]") for n in patterns]
    for loc in kandidaten:
        for i in range(min(loc.count(), 5)):
            if _editierbar(loc.nth(i)):
                return loc.nth(i)
    return None


def fill_first(page: Page, patterns: list[str], value: str) -> bool:
    """Füllt das erste Eingabefeld, dessen Label/Placeholder/Name passt.

    Ist das Feld hinter einem Button versteckt ("Verbrauch bearbeiten"), wird der erst geklickt.
    """
    rx = re.compile("|".join(patterns), re.I)
    feld = _erstes_feld(page, rx, patterns)
    if feld is None:
        btn = page.get_by_role("button", name=rx)
        if btn.count() and btn.first.is_visible():
            _klicken(page, btn.first)
            page.wait_for_timeout(600)
            feld = _erstes_feld(page, rx, patterns)
    if feld is None:
        return False
    feld.fill(value)
    return True


def _klicken(page: Page, loc, timeout_ms: int = 8000) -> bool:
    """Klickt; liegt etwas darüber (offene Vorschlagsliste o. Ä.), erst Escape, dann noch ein Versuch."""
    for _ in range(2):
        try:
            loc.click(timeout=timeout_ms)
            return True
        except Exception:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
    return False


def _sichtbar(loc):
    for i in range(min(loc.count(), 5)):
        if loc.nth(i).is_visible():
            return loc.nth(i)
    return None


def pick_autocomplete(page: Page, text: str | None = None) -> None:
    """Ersten Vorschlag übernehmen. Check24 zeigt die Orte als Buttons in einer Liste („71404 Korb“)."""
    page.wait_for_timeout(1200)
    kandidaten = [page.get_by_role("option")]
    if text:
        kandidaten.append(page.locator("li").filter(has_text=text).locator("button, a, [role=button]"))
        kandidaten.append(page.locator("li").filter(has_text=text))
    for loc in kandidaten:
        treffer = _sichtbar(loc)
        if treffer is not None and _klicken(page, treffer, 4000):
            break
    else:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
    page.wait_for_timeout(500)


def oeffnen(page: Page, name: str) -> bool:
    """Button klicken, hinter dem ein Formular-Dialog steckt (z. B. „Adresse“ bei Check24 DSL)."""
    btn = _sichtbar(page.get_by_role("button", name=re.compile(name, re.I)))
    if btn is None or not _klicken(page, btn, 4000):
        return False
    page.wait_for_timeout(600)
    return True


def bestaetigen(page: Page) -> bool:
    """Eingabe-Overlay schließen („Übernehmen“ bei Check24), sonst gilt der eingetippte Wert nicht."""
    btn = _sichtbar(page.get_by_role("button", name=re.compile(r"^\W*(übernehmen|bestätigen|fertig)\W*$", re.I)))
    if btn is None:
        return False
    _klicken(page, btn, 4000)
    page.wait_for_timeout(500)
    return True


def submit(page: Page) -> None:
    accept_cookies(page, warten_s=0)  # spät eingeblendete Banner blockieren sonst den Klick
    btn = _sichtbar(page.get_by_role("button", name=re.compile(r"vergleich|berechnen|suchen|prüfen|weiter|tarife", re.I)))
    if btn is None or not _klicken(page, btn):
        page.keyboard.press("Enter")


def wait_for_cards(page: Page, keyword: str, timeout_s: int = 60, min_len: int = 60,
                   min_cards: int = 3) -> list[dict]:
    """Liefert [{"text": ..., "href": ...}] der erkannten Ergebnis-Kacheln."""
    arg = {"keyword": keyword, "minLen": min_len}
    deadline = time.time() + timeout_s
    cards: list[dict] = []
    while time.time() < deadline:
        cards = page.evaluate(FIND_CARDS_JS, arg)
        if len(cards) >= min_cards:
            break
        page.wait_for_timeout(1500)
    # Nachladen durch Scrollen
    for _ in range(4):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1200)
    more = page.evaluate(FIND_CARDS_JS, arg)
    return more if len(more) > len(cards) else cards


MAX_DEBUG = 40


def dump_debug(page: Page, name: str, cards: list[dict]) -> Path:
    basis = DATA_DIR / "debug"
    out = basis / f"{name}-{datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    for alt in sorted(basis.iterdir(), key=lambda p: p.stat().st_mtime)[:-MAX_DEBUG]:
        shutil.rmtree(alt, ignore_errors=True)
    try:
        page.screenshot(path=str(out / "seite.png"), full_page=True)
    except Exception:
        pass
    (out / "seite.html").write_text(page.content(), encoding="utf-8")
    (out / "url.txt").write_text(page.url, encoding="utf-8")
    (out / "kacheln.txt").write_text("\n\n=====\n\n".join(f"{c['href']}\n{c['text']}" for c in cards), encoding="utf-8")
    (out / "json.json").write_text(
        json.dumps(getattr(page, "_json_responses", []), ensure_ascii=False, indent=1, default=str)[:20_000_000],
        encoding="utf-8",
    )
    return out
