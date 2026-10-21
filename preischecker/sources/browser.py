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

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

# Findet wiederholte Kacheln: Elemente mit Preis + Stichwort, die als
# Geschwister unter demselben Eltern-Element liegen. Liefert deren innerText.
FIND_CARDS_JS = r"""
({keyword, minLen}) => {
  const kw = new RegExp(keyword, 'i');
  const price = /(\d+[.,]\d{2}\s*€|€\s*\d+[.,]\d{2}|\d+,[-–])/;
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
    return {text: e.innerText, href: a ? a.href : ''};
  });
}
"""

COOKIE_BUTTONS = re.compile(r"^(alle akzeptieren|akzeptieren|geht klar|zustimmen|alles akzeptieren|einverstanden|ok)$", re.I)


@contextmanager
def browser_page(cfg: dict):
    bcfg = cfg.get("browser", {})
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("PREISCHECKER_CHROMIUM") or None,
            headless=bcfg.get("headless", True),
            args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(
            user_agent=UA,
            locale="de-DE",
            timezone_id="Europe/Berlin",
            viewport={"width": 1366, "height": 900},
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


def accept_cookies(page: Page) -> None:
    for frame in [page.main_frame, *page.frames]:
        try:
            btn = frame.get_by_role("button", name=COOKIE_BUTTONS)
            if btn.count():
                btn.first.click(timeout=3000)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


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
            btn.first.click()
            page.wait_for_timeout(600)
            feld = _erstes_feld(page, rx, patterns)
    if feld is None:
        return False
    feld.fill(value)
    return True


def pick_autocomplete(page: Page) -> None:
    page.wait_for_timeout(1200)
    opt = page.get_by_role("option")
    if opt.count():
        opt.first.click()
    else:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
    page.wait_for_timeout(500)


def submit(page: Page) -> None:
    btn = page.get_by_role("button", name=re.compile(r"vergleich|berechnen|suchen|prüfen|weiter|tarife", re.I))
    if btn.count():
        btn.first.click()
    else:
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
