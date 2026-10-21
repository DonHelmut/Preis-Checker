/* Preis-Checker – Diagramme, Live-Fortschritt, Tabellen-Sortierung. Ohne externe Bibliotheken. */
(() => {
  "use strict";
  const BASIS = document.body.dataset.base || "/";
  const NS = "http://www.w3.org/2000/svg";
  const eurFmt = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
  const eurKurz = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
  const datumFmt = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit" });
  const zeitFmt = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  const eur = v => eurFmt.format(v);
  const farbe = name => getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();

  function el(tag, attrs = {}, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  }

  // "Schöne" Achsenwerte (1, 2, 2.5, 5 × 10^n)
  function ticks(min, max, anzahl = 5) {
    if (max <= min) { max = min + 1; }
    const roh = (max - min) / anzahl;
    const mag = Math.pow(10, Math.floor(Math.log10(roh)));
    const schritt = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= roh) || 10 * mag;
    const out = [];
    for (let v = Math.ceil(min / schritt) * schritt; v <= max + 1e-9; v += schritt) out.push(+v.toFixed(6));
    return out;
  }

  // Wert einer Stufenlinie zum Zeitpunkt t (letzter Punkt ≤ t)
  function wertBei(punkte, t) {
    let lo = 0, hi = punkte.length - 1, treffer = null;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (punkte[mid].t <= t) { treffer = punkte[mid]; lo = mid + 1; } else hi = mid - 1;
    }
    return treffer;
  }

  // ---------- Sparklines ----------
  function sparkline(box) {
    const werte = JSON.parse(box.dataset.spark || "[]");
    box.textContent = "";
    if (werte.length < 2) {
      box.innerHTML = '<div class="muted klein" style="height:100%;display:flex;align-items:center">Verlauf entsteht mit jeder Prüfung</div>';
      return;
    }
    const w = box.clientWidth || 260, h = box.clientHeight || 52, pad = 5;
    const min = Math.min(...werte), max = Math.max(...werte), span = max - min || 1;
    const x = i => pad + (i / (werte.length - 1)) * (w - 2 * pad);
    const y = v => h - pad - ((v - min) / span) * (h - 2 * pad);
    const svg = el("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}`, "aria-hidden": "true" }, box);
    let d = `M${x(0)},${y(werte[0])}`;
    werte.forEach((v, i) => { if (i) d += `H${x(i)}V${y(v)}`; });
    const gid = "g" + Math.random().toString(36).slice(2);
    const grad = el("linearGradient", { id: gid, x1: 0, x2: 0, y1: 0, y2: 1 }, el("defs", {}, svg));
    el("stop", { offset: "0", "stop-color": farbe("accent"), "stop-opacity": ".18" }, grad);
    el("stop", { offset: "1", "stop-color": farbe("accent"), "stop-opacity": "0" }, grad);
    el("path", { d: `${d}V${h}H${x(0)}Z`, fill: `url(#${gid})` }, svg);
    el("path", { d, fill: "none", stroke: farbe("accent"), "stroke-width": 2, "stroke-linejoin": "round" }, svg);
    const ix = werte.indexOf(min);
    el("circle", { cx: x(ix), cy: y(min), r: 2.5, fill: farbe("good") }, svg);
    el("circle", { cx: x(werte.length - 1), cy: y(werte[werte.length - 1]), r: 4, fill: farbe("accent"), stroke: farbe("surface"), "stroke-width": 2 }, svg);
  }

  // ---------- Preisverlauf (Detailseite) ----------
  function preisChart(box) {
    const daten = JSON.parse(document.getElementById(box.dataset.quelle).textContent);
    const serien = daten.serien.map(s => ({ ...s, punkte: s.punkte.map(p => ({ t: new Date(p[0]).getTime(), v: p[1], shop: p[2] })) }))
                               .filter(s => s.punkte.length);
    const versteckt = new Set(serien.filter(s => s.key !== "best").length > 4 ? serien.slice(5).map(s => s.key) : []);
    let tage = Number(box.dataset.tage || 30);
    const flaeche = box.querySelector(".flaeche");
    const tip = box.querySelector(".tooltip");
    const legende = document.querySelector(box.dataset.legende);
    const segment = document.querySelector(box.dataset.segment);

    if (!serien.length) { flaeche.innerHTML = '<div class="leer">Noch kein Verlauf. Er entsteht automatisch mit jeder Prüfung.</div>'; return; }

    // Legende (Farbe = Identität, Text in Textfarbe)
    if (legende) {
      serien.forEach(s => {
        const b = document.createElement("button");
        b.type = "button";
        b.setAttribute("aria-pressed", String(!versteckt.has(s.key)));
        const i = document.createElement("i");
        i.style.background = `var(--${s.farbe})`;
        if (s.key === "best") i.style.height = "3.5px";
        b.append(i, document.createTextNode(s.name));
        b.addEventListener("click", () => {
          versteckt.has(s.key) ? versteckt.delete(s.key) : versteckt.add(s.key);
          b.setAttribute("aria-pressed", String(!versteckt.has(s.key)));
          zeichnen();
        });
        legende.appendChild(b);
      });
    }
    if (segment) {
      segment.querySelectorAll("button").forEach(b => {
        b.setAttribute("aria-pressed", String(Number(b.dataset.tage) === tage));
        b.addEventListener("click", () => {
          tage = Number(b.dataset.tage);
          segment.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
          zeichnen();
        });
      });
    }

    function zeichnen() {
      flaeche.querySelector("svg")?.remove();
      const W = flaeche.clientWidth || 600, H = W < 520 ? 240 : 320;
      const m = { l: 58, r: 18, t: 14, b: 30 };
      const alleT = serien.flatMap(s => s.punkte.map(p => p.t));
      const tMax = Math.max(...alleT, Date.now());
      const tMinDaten = Math.min(...alleT);
      const tMin = tage ? Math.max(tMax - tage * 864e5, tMinDaten) : tMinDaten;
      const sicht = serien.filter(s => !versteckt.has(s.key)).map(s => {
        const vor = wertBei(s.punkte, tMin);
        const pts = s.punkte.filter(p => p.t >= tMin);
        if (vor && (!pts.length || pts[0].t > tMin)) pts.unshift({ ...vor, t: tMin });
        return { ...s, sicht: pts };
      }).filter(s => s.sicht.length);
      const werte = sicht.flatMap(s => s.sicht.map(p => p.v));
      if (daten.ziel) werte.push(daten.ziel);
      if (!werte.length) return;
      let yMin = Math.min(...werte), yMax = Math.max(...werte);
      const pad = (yMax - yMin) * .12 || yMax * .05 || 1;
      yMin -= pad; yMax += pad;
      const yt = ticks(yMin, yMax, 5);
      yMin = Math.min(yMin, yt[0]); yMax = Math.max(yMax, yt[yt.length - 1]);
      const t0 = tMin, t1 = tMax > tMin ? tMax : tMin + 36e5;
      const x = t => m.l + (t - t0) / (t1 - t0) * (W - m.l - m.r);
      const y = v => m.t + (1 - (v - yMin) / (yMax - yMin)) * (H - m.t - m.b);

      const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img",
                              "aria-label": "Preisverlauf" });
      flaeche.appendChild(svg);
      const ax = el("g", { class: "ax" }, svg);
      yt.forEach(v => {
        el("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: farbe("grid"), "stroke-width": 1 }, ax);
        const t = el("text", { x: m.l - 10, y: y(v) + 4, "text-anchor": "end" }, ax);
        t.textContent = `${eurKurz.format(v)} €`;
      });
      el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: farbe("axis") }, ax);
      const anzahlX = Math.max(2, Math.min(6, Math.floor((W - m.l - m.r) / 90)));
      for (let i = 0; i <= anzahlX; i++) {
        const t = t0 + (t1 - t0) * i / anzahlX;
        const txt = el("text", { x: x(t), y: H - 9, "text-anchor": i === 0 ? "start" : i === anzahlX ? "end" : "middle" }, ax);
        txt.textContent = datumFmt.format(new Date(t));
      }
      if (daten.ziel) {
        el("line", { x1: m.l, x2: W - m.r, y1: y(daten.ziel), y2: y(daten.ziel), stroke: farbe("ink-2"),
                     "stroke-width": 1.25, "stroke-dasharray": "5 5", opacity: .7 }, svg);
        const zt = el("text", { x: W - m.r, y: y(daten.ziel) - 6, "text-anchor": "end", fill: farbe("ink-2"), "font-size": 11.5 }, svg);
        zt.textContent = `Ziel ${eur(daten.ziel)}`;
      }
      // Shops zuerst, Bestpreis oben
      [...sicht].sort((a, b) => (a.key === "best") - (b.key === "best")).forEach(s => {
        let d = `M${x(s.sicht[0].t)},${y(s.sicht[0].v)}`;
        s.sicht.forEach((p, i) => { if (i) d += `H${x(p.t)}V${y(p.v)}`; });
        if (s.key === "best") d += `H${x(t1)}`;
        el("path", { d, fill: "none", stroke: `var(--${s.farbe})`, "stroke-width": s.key === "best" ? 2.75 : 2,
                     "stroke-linejoin": "round", opacity: s.key === "best" ? 1 : .9 }, svg);
      });
      const best = sicht.find(s => s.key === "best");
      if (best) {
        const l = best.sicht[best.sicht.length - 1];
        el("circle", { cx: x(t1), cy: y(l.v), r: 4.5, fill: `var(--best)`, stroke: farbe("surface"), "stroke-width": 2 }, svg);
        const min = best.sicht.reduce((a, b) => (b.v < a.v ? b : a));
        el("circle", { cx: x(min.t), cy: y(min.v), r: 4, fill: farbe("good"), stroke: farbe("surface"), "stroke-width": 2 }, svg);
      }

      // Hover-Ebene: Fadenkreuz rastet auf Messzeitpunkte ein, Tooltip zeigt alle Linien
      const zeiten = [...new Set(sicht.flatMap(s => s.sicht.map(p => p.t)))].sort((a, b) => a - b);
      const kreuz = el("line", { y1: m.t, y2: H - m.b, stroke: farbe("axis"), "stroke-width": 1, opacity: 0 }, svg);
      const marker = el("g", {}, svg);
      const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent", tabindex: 0 }, svg);
      let idx = zeiten.length - 1;
      function zeige(i) {
        idx = Math.max(0, Math.min(zeiten.length - 1, i));
        const t = zeiten[idx];
        kreuz.setAttribute("x1", x(t)); kreuz.setAttribute("x2", x(t)); kreuz.setAttribute("opacity", 1);
        marker.textContent = "";
        tip.textContent = "";
        const kopf = document.createElement("div"); kopf.className = "t"; kopf.textContent = zeitFmt.format(new Date(t));
        tip.appendChild(kopf);
        sicht.map(s => ({ s, p: wertBei(s.sicht, t) })).filter(r => r.p).sort((a, b) => a.p.v - b.p.v).forEach(({ s, p }) => {
          el("circle", { cx: x(t), cy: y(p.v), r: 4, fill: `var(--${s.farbe})`, stroke: farbe("surface"), "stroke-width": 2 }, marker);
          const r = document.createElement("div"); r.className = "r";
          const sp = document.createElement("span"); const i = document.createElement("i");
          i.style.background = `var(--${s.farbe})`;
          sp.append(i, document.createTextNode(s.key === "best" && p.shop ? `Bestpreis (${p.shop})` : s.name));
          const b = document.createElement("b"); b.textContent = eur(p.v);
          r.append(sp, b); tip.appendChild(r);
        });
        tip.classList.add("an");
        const bx = x(t) + 16, tw = tip.offsetWidth;
        tip.style.left = `${bx + tw > W ? x(t) - tw - 16 : bx}px`;
        tip.style.top = `${m.t + 6}px`;
      }
      function weg() { kreuz.setAttribute("opacity", 0); marker.textContent = ""; tip.classList.remove("an"); }
      hit.addEventListener("pointermove", e => {
        const r = svg.getBoundingClientRect();
        const t = t0 + (e.clientX - r.left - m.l) / (W - m.l - m.r) * (t1 - t0);
        let best = 0;
        zeiten.forEach((z, i) => { if (Math.abs(z - t) < Math.abs(zeiten[best] - t)) best = i; });
        zeige(best);
      });
      hit.addEventListener("pointerleave", weg);
      hit.addEventListener("focus", () => zeige(idx));
      hit.addEventListener("blur", weg);
      hit.addEventListener("keydown", e => {
        if (e.key === "ArrowLeft") { zeige(idx - 1); e.preventDefault(); }
        if (e.key === "ArrowRight") { zeige(idx + 1); e.preventDefault(); }
      });
    }
    zeichnen();
    new ResizeObserver(() => zeichnen()).observe(flaeche);
  }

  // ---------- Live-Fortschritt ----------
  function fortschritt() {
    const box = document.getElementById("fortschritt");
    if (!box) return;
    const url = box.dataset.url ? BASIS + box.dataset.url : BASIS + "api/fortschritt";
    let warAktiv = box.classList.contains("an");
    async function abfragen() {
      try {
        const r = await fetch(url, { cache: "no-store" });
        if (!r.ok) return;
        const d = await r.json();
        const f = d.fortschritt || d;
        const aktiv = d.status ? d.status === "laeuft" : (f.aktiv || d.laeuft);
        box.classList.toggle("an", !!aktiv);
        box.querySelector(".balken > span").style.width = `${f.prozent || 0}%`;
        box.querySelector(".zahl").textContent = f.gesamt ? `${f.fertig} von ${f.gesamt}` : "";
        box.querySelector(".phase").textContent = f.phase || "Prüfung läuft";
        const l = box.querySelector(".laufend");
        l.textContent = "";
        (f.laufend || []).forEach(t => { const s = document.createElement("span"); s.textContent = t; l.appendChild(s); });
        document.querySelectorAll("[data-pruefen]").forEach(b => { b.disabled = !!aktiv; });
        if (warAktiv && !aktiv) { location.reload(); return; }
        warAktiv = !!aktiv;
      } catch (e) { /* nächster Versuch */ }
      setTimeout(abfragen, warAktiv ? 1500 : 6000);
    }
    abfragen();
  }

  // ---------- Tabellen sortieren ----------
  function sortierbar(tabelle) {
    tabelle.querySelectorAll("th[data-sort]").forEach((th, spalte) => {
      th.addEventListener("click", () => {
        const idx = [...th.parentNode.children].indexOf(th);
        const auf = !th.classList.contains("sortiert-auf");
        tabelle.querySelectorAll("th").forEach(x => x.classList.remove("sortiert-auf", "sortiert-ab"));
        th.classList.add(auf ? "sortiert-auf" : "sortiert-ab");
        const tb = tabelle.tBodies[0];
        const zeilen = [...tb.rows];
        const wert = r => { const c = r.cells[idx]; const v = c?.dataset.wert ?? c?.textContent.trim() ?? ""; const n = parseFloat(v); return isNaN(n) ? v.toLowerCase() : n; };
        zeilen.sort((a, b) => { const x = wert(a), y = wert(b); return (x > y ? 1 : x < y ? -1 : 0) * (auf ? 1 : -1); });
        zeilen.forEach(z => tb.appendChild(z));
      });
    });
  }

  document.querySelectorAll("[data-spark]").forEach(b => { sparkline(b); new ResizeObserver(() => sparkline(b)).observe(b); });
  document.querySelectorAll("[data-chart]").forEach(preisChart);
  document.querySelectorAll("table.sortierbar").forEach(sortierbar);
  fortschritt();

  // Produktzeilen in den Einstellungen
  document.querySelectorAll("[data-neue-zeile]").forEach(btn => btn.addEventListener("click", () => {
    const tb = document.querySelector(btn.dataset.neueZeile);
    const tpl = document.getElementById("produkt-zeile");
    tb.appendChild(tpl.content.cloneNode(true));
  }));
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-zeile-weg]");
    if (b) b.closest("tr").remove();
  });
})();
