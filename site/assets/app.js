/* Shared code for every page: header, helpers, the architecture diagram, and the charts.
   All numbers come from window.SITE / window.RUNS_*, which site/build_data.py writes from the real results. */
(function () {
  "use strict";
  const SVGNS = "http://www.w3.org/2000/svg";
  const APP = (window.APP = {});
  const AP_LABEL = { fixed: "Fixed pipeline", single: "Single agent", multi: "Multi-agent" };
  const AP_SHORT = { fixed: "fixed", single: "single", multi: "multi" };
  APP.AP_LABEL = AP_LABEL;
  APP.AP_SHORT = AP_SHORT;

  // ---------- small helpers ----------
  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k === "html") e.innerHTML = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(kid));
    return e;
  }
  function svg(tag, attrs, ...kids) {
    const e = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "text") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid) e.append(kid);
    return e;
  }
  APP.el = el;
  APP.svg = svg;
  APP.pct = (a, b) => (b ? Math.round((100 * a) / b) + "%" : "n/a");
  APP.money = (x) => (x == null ? "n/a" : x < 0.01 ? "$" + x.toFixed(4) : "$" + x.toFixed(x < 1 ? 3 : 2));
  APP.esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  APP.model = (key) => window.SITE.models.find((m) => m.key === key);
  APP.runs = (key) => window["RUNS_" + key.toUpperCase()] || [];
  APP.consoleLink = (s, model, ap, i) => `console.html#${s}/${model}/${ap}/${(i || 0) + 1}`;

  // ---------- tooltip ----------
  let tip;
  APP.tip = function (evt, html) {
    if (!tip) { tip = el("div", { class: "tooltip", role: "status" }); document.body.append(tip); }
    tip.innerHTML = html;
    tip.hidden = false;
    const pad = 14, r = tip.getBoundingClientRect();
    let x = evt.clientX + pad, y = evt.clientY + pad;
    if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - pad;
    if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - pad;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  };
  APP.untip = () => { if (tip) tip.hidden = true; };

  // ---------- header and footer ----------
  const PAGES = [["index.html", "Findings"], ["console.html", "Incident console"], ["results.html", "Results"], ["method.html", "How it works"]];
  APP.frame = function (current) {
    const mark = `<svg class="brand-mark" viewBox="0 0 26 26" aria-hidden="true">
      <rect x="1" y="1" width="24" height="24" rx="5" fill="var(--accent)"/>
      <rect x="5" y="5" width="8" height="8" fill="var(--surface)"/><rect x="13" y="13" width="8" height="8" fill="var(--surface)"/>
      <path d="M5 19.5h5l2-4 2 6 2-3h5" stroke="var(--accent)" stroke-width="1.6" fill="none" transform="translate(0 -1)"/></svg>`;
    const header = el("header", { class: "topbar" },
      el("div", { class: "topbar-inner" },
        el("a", { class: "brand", href: "index.html", html: mark + `<span><span class="brand-name">Incident Copilot</span><br><span class="brand-sub">AI triage on the Fianchetto chess platform</span><br><span class="brand-sub">Sharad Cornejo Altuzar · Capstone project RAG &amp; Agents</span></span>` }),
        el("nav", { class: "nav", "aria-label": "Pages" },
          PAGES.map(([href, label]) => el("a", { href, "aria-current": href === current ? "page" : null, text: label })))));
    document.body.prepend(header);
    // the console's sticky toolbar sits under the header, whatever height the header wraps to
    const setH = () => document.documentElement.style.setProperty("--topbar-h", header.offsetHeight + "px");
    setH();
    new ResizeObserver(setH).observe(header);
    const m = window.SITE.models;
    document.body.append(el("footer", {},
      el("div", { class: "wrap" },
        el("span", { text: "Sharad Cornejo Altuzar · Capstone project, AI Engineering cohort (RAG & Agents). All incidents, services and data are synthetic." }),
        el("span", { class: "mono", text: m.map((x) => `${x.label}: ${x.runs} runs, commit ${x.commit}`).join(" · ") }))));
  };

  // ---------- the board: wood grain and the fianchetto bishop ----------
  // Grain is procedural (stretched fractal noise turned into brown streaks over a base colour), so it costs no image
  // and follows the theme: maple in light mode, walnut in dark mode (colours in style.css).
  APP.wood = function (root, W, H, id) {
    const defs = root.querySelector("defs") || root.insertBefore(svg("defs"), root.firstChild);
    defs.append(
      svg("filter", { id: "grain-" + id, x: 0, y: 0, width: "100%", height: "100%", "color-interpolation-filters": "sRGB" },
        svg("feTurbulence", { type: "fractalNoise", baseFrequency: "0.0035 0.11", numOctaves: 4, seed: 11, result: "n" }),
        svg("feColorMatrix", { in: "n", type: "matrix", values: "0 0 0 0 0.24  0 0 0 0 0.13  0 0 0 0 0.05  1.9 0 0 0 -0.72" })),
      svg("filter", { id: "rings-" + id, x: 0, y: 0, width: "100%", height: "100%", "color-interpolation-filters": "sRGB" },
        svg("feTurbulence", { type: "turbulence", baseFrequency: "0.0012 0.018", numOctaves: 2, seed: 4, result: "r" }),
        svg("feColorMatrix", { in: "r", type: "matrix", values: "0 0 0 0 0.30  0 0 0 0 0.17  0 0 0 0 0.07  2.4 0 0 0 -0.35" })));
    root.append(
      svg("rect", { x: 0, y: 0, width: W, height: H, rx: 10, class: "wood-base" }),
      svg("rect", { x: 0, y: 0, width: W, height: H, rx: 10, filter: `url(#rings-${id})`, class: "wood-grain" }),
      svg("rect", { x: 0, y: 0, width: W, height: H, rx: 10, filter: `url(#grain-${id})`, class: "wood-grain" }),
      svg("rect", { x: 0.5, y: 0.5, width: W - 1, height: H - 1, rx: 10, class: "wood-edge" }));
  };

  // A carved bishop, the fianchetto piece. Drawn at (x, y) = top-left, about 100 x 150 units before scaling.
  APP.bishop = function (root, x, y, s = 1) {
    const g = svg("g", { class: "bishop", transform: `translate(${x},${y}) scale(${s})`, "aria-hidden": "true" });
    const title = svg("title", { text: "Fianchetto: the bishop developed onto the long diagonal" });
    g.append(title,
      svg("ellipse", { cx: 50, cy: 151, rx: 46, ry: 6, class: "bishop-shadow" }),
      svg("rect", { x: 8, y: 134, width: 84, height: 15, rx: 4, class: "bishop-body" }),
      svg("rect", { x: 17, y: 122, width: 66, height: 14, rx: 4, class: "bishop-body" }),
      svg("path", { d: "M31,122 C31,112 37,106 39,98 L61,98 C63,106 69,112 69,122 Z", class: "bishop-body" }),
      svg("rect", { x: 27, y: 90, width: 46, height: 10, rx: 4, class: "bishop-body" }),
      svg("path", { d: "M37,91 C21,77 24,50 50,28 C76,50 79,77 63,91 Z", class: "bishop-body" }),
      svg("path", { d: "M58,47 L44,70", class: "bishop-cut" }),
      svg("circle", { cx: 50, cy: 20, r: 9, class: "bishop-body" }),
      svg("path", { d: "M41,88 C33,76 35,58 47,40", class: "bishop-shine" }),
      svg("path", { d: "M22,136 L22,147", class: "bishop-shine" }));
    root.append(g);
    return g;
  };

  // ---------- architecture diagram ----------
  // Grid positions from site.js scaled into one viewBox. Boxes 172 x 54.
  const BW = 172, BH = 54;
  const X = (x) => 24 + x * 206, Y = (y) => 58 + (y + 0.2) * 90;
  APP.topoBox = (n) => ({ x: X(n.x), y: Y(n.y), cx: X(n.x) + BW / 2, cy: Y(n.y) + BH / 2 });

  APP.topology = function (host, opts = {}) {
    const S = window.SITE;
    const root = svg("svg", { viewBox: "0 0 1050 660", class: "topo", role: "img", "aria-label": "Fianchetto architecture: clients, edge, services, data stores and platform" });
    const defs = svg("defs", {},
      svg("pattern", { id: "hatch", width: 7, height: 7, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" },
        svg("rect", { width: 7, height: 7, fill: "var(--surface-2)" }), svg("line", { x1: 0, y1: 0, x2: 0, y2: 7, stroke: "var(--gap)", "stroke-width": 2, opacity: 0.5 })),
      svg("filter", { id: "glow", x: "-30%", y: "-40%", width: "160%", height: "180%" }, svg("feGaussianBlur", { stdDeviation: 7 })));
    root.append(defs);
    APP.wood(root, 1050, 660, "topo");
    // layer bands and column labels
    root.append(svg("rect", { x: 8, y: Y(4.35), width: 1034, height: 660 - Y(4.35) - 6, rx: 8, class: "wood-band" }));
    root.append(svg("text", { x: 20, y: Y(4.35) + 20, class: "topo-band", text: "PLATFORM" }));
    APP.bishop(root, 40, 500, 0.95);
    [["EDGE", 0.5], ["SERVICES", 2.5], ["DATA STORES · EXTERNAL", 4]].forEach(([t, x]) =>
      root.append(svg("text", { x: X(x) + BW / 2, y: 22, class: "topo-band", "text-anchor": "middle", text: t })));
    const byId = Object.fromEntries(S.nodes.map((n) => [n.id, n]));
    const edges = svg("g", { class: "topo-edges" });
    for (const [a, b] of S.edges) {
      const p = APP.topoBox(byId[a]), q = APP.topoBox(byId[b]);
      const dx = q.cx - p.cx;
      const d = Math.abs(dx) < 10
        ? `M${p.cx},${p.cy} L${q.cx},${q.cy}`
        : `M${p.cx},${p.cy} C${p.cx + dx * 0.5},${p.cy} ${q.cx - dx * 0.5},${q.cy} ${q.cx},${q.cy}`;
      edges.append(svg("path", { d, class: "topo-edge", "data-a": a, "data-b": b }));
    }
    root.append(edges);
    const nodeG = {};
    const nodes = svg("g", {});
    for (const n of S.nodes) {
      const b = APP.topoBox(n);
      const g = svg("g", { class: `topo-node layer-${n.layer}`, transform: `translate(${b.x},${b.y})`, tabindex: opts.onSelect ? 0 : null,
        role: opts.onSelect ? "button" : null, "aria-label": `${n.label}: ${n.detail}`, "data-id": n.id });
      g.append(svg("rect", { class: "glow", x: -6, y: -6, width: BW + 12, height: BH + 12, rx: 12, filter: "url(#glow)" }));
      g.append(svg("rect", { class: "box", width: BW, height: BH, rx: 6 }));
      g.append(svg("text", { class: "lbl", x: 11, y: 24, text: n.label }));
      g.append(svg("text", { class: "det", x: 12, y: 41, text: n.detail.length > 26 ? n.detail.slice(0, 25) + "…" : n.detail }));
      g.append(svg("g", { class: "badges", transform: "translate(0,-8)" }));
      g.append(svg("g", { class: "count" }));
      if (opts.onSelect) {
        g.addEventListener("click", () => opts.onSelect(n.id));
        g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); opts.onSelect(n.id); } });
      }
      nodeG[n.id] = g;
      nodes.append(g);
    }
    root.append(nodes);
    host.append(root);

    function badge(g, x, text, cls) {
      const w = text.length * 6.3 + 12;
      const b = svg("g", { class: "badge " + cls, transform: `translate(${x},-10)` },
        svg("rect", { width: w, height: 17, rx: 3 }), svg("text", { x: 6, y: 12.2, text }));
      g.append(b);
      return w + 4;
    }

    // states: {id: {cause, victim, alert, ambiguous, gap, blamed: "ok"|"wrong", looked: n, selected}}
    function update(states) {
      const max = Math.max(1, ...Object.values(states).map((s) => s.looked || 0));
      for (const [id, g] of Object.entries(nodeG)) {
        const s = states[id] || {};
        const cls = ["topo-node", `layer-${byId[id].layer}`];
        if (s.cause) cls.push("is-cause");
        if (s.ambiguous) cls.push("is-ambiguous");
        if (s.gap) cls.push("is-gap");
        if (s.victim) cls.push("is-victim");
        if (s.blamed) cls.push("is-blamed-" + s.blamed);
        if (s.looked) cls.push("is-looked");
        if (s.selected) cls.push("is-selected");
        g.setAttribute("class", cls.join(" "));
        g.querySelector(".glow").style.opacity = s.looked ? (0.3 + 0.7 * (s.looked / max)).toFixed(2) : 0;
        const bg = g.querySelector(".badges");
        bg.replaceChildren();
        let x = 0;
        if (s.alert) x += badge(bg, x, "ALERT", "b-alert");
        if (s.cause) x += badge(bg, x, "BROKE", "b-broke");
        if (s.ambiguous) x += badge(bg, x, "POSSIBLE CAUSE", "b-broke");
        if (s.gap) x += badge(bg, x, "DATA GAP", "b-gap");
        if (s.victim && !s.cause) x += badge(bg, x, "SYMPTOM", "b-victim");
        if (s.blamed === "ok") x += badge(bg, x, "AGENT ✓", "b-right");
        if (s.blamed === "wrong") x += badge(bg, x, "AGENT BLAMED", "b-blamed");
        const cg = g.querySelector(".count");
        cg.replaceChildren();
        if (s.looked) {
          const t = String(s.looked);
          cg.append(svg("circle", { cx: BW, cy: 0, r: 11 + (t.length - 1) * 3 }), svg("text", { x: BW, y: 4, "text-anchor": "middle", text: t }));
        }
        g.querySelector("rect.box").setAttribute("fill", s.gap ? "url(#hatch)" : "");
      }
    }
    function pulse(id) {
      const g = nodeG[id];
      if (!g) return;
      g.classList.remove("pulse");
      void g.getBoundingClientRect();
      g.classList.add("pulse");
    }
    return { update, pulse, root };
  };

  // States for one run on the diagram. `upto` limits the looked-at counts to the first steps (for the replay).
  APP.runStates = function (sc, run, upto, showTruth = true) {
    const st = {};
    const get = (id) => (st[id] = st[id] || {});
    if (sc.alert_node) get(sc.alert_node).alert = true;
    if (showTruth) {
      for (const id of sc.truth.cause || []) get(id).cause = true;
      for (const id of sc.truth.victim || []) get(id).victim = true;
      for (const id of sc.truth.ambiguous || []) get(id).ambiguous = true;
      for (const id of sc.truth.gap || []) get(id).gap = true;
    }
    if (run) {
      const steps = upto == null ? run.steps : run.steps.slice(0, upto);
      for (const s of steps) if (s.kind === "tool" && s.node) get(s.node).looked = (get(s.node).looked || 0) + 1;
      if (upto == null || upto >= run.steps.length) for (const id of run.blamed) get(id).blamed = run.ok ? "ok" : "wrong";
    }
    return st;
  };

  // ---------- charts ----------
  // Horizontal-free vertical bar chart with one bar per item; values 0..max. items: [{label, value, cls, note, tip}]
  APP.bars = function (host, items, { max = 1, height = 220, fmt = (v) => v, title = "" } = {}) {
    const W = 360, H = height, m = { t: 26, r: 8, b: 40, l: 34 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": title });
    for (const f of [0, 0.25, 0.5, 0.75, 1]) {
      const y = m.t + ih * (1 - f);
      s.append(svg("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, class: f === 0 ? "axisline" : "gridline" }));
      s.append(svg("text", { x: m.l - 6, y: y + 4, "text-anchor": "end", class: "tick", text: Math.round(f * max * 100) + "%" }));
    }
    const bw = Math.min(64, iw / items.length - 18);
    items.forEach((it, i) => {
      const cx = m.l + (iw / items.length) * (i + 0.5);
      const h = Math.max(0, (it.value / max) * ih);
      const y = m.t + ih - h;
      const r = Math.min(4, h / 2);
      const g = svg("g", { class: it.cls || "" });
      // rounded top only, anchored to the baseline
      g.append(svg("path", { d: `M${cx - bw / 2},${m.t + ih} V${y + r} Q${cx - bw / 2},${y} ${cx - bw / 2 + r},${y} H${cx + bw / 2 - r} Q${cx + bw / 2},${y} ${cx + bw / 2},${y + r} V${m.t + ih} Z`, fill: "var(--ap)" }));
      g.append(svg("text", { x: cx, y: y - 7, "text-anchor": "middle", class: "val", text: fmt(it.value) }));
      if (it.note) g.append(svg("text", { x: cx, y: m.t + ih + 15, "text-anchor": "middle", class: "tick", text: it.note }));
      g.append(svg("text", { x: cx, y: m.t + ih + 30, "text-anchor": "middle", text: it.label }));
      g.append(svg("rect", { x: cx - bw / 2 - 8, y: m.t, width: bw + 16, height: ih + 34, fill: "transparent",
        onmousemove: (e) => APP.tip(e, it.tip), onmouseleave: APP.untip }));
      s.append(g);
    });
    host.append(s);
  };

  // Stacked 100% bars: rows [{label, cls, parts:[{key, value, label}]}]; partStyles {key: {fill, label}}
  APP.stacked = function (host, rows, partStyles, { title = "" } = {}) {
    const W = 640, rowH = 34, m = { t: 8, r: 12, b: 26, l: 150 };
    const H = m.t + rows.length * rowH + m.b;
    const iw = W - m.l - m.r;
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": title });
    for (const f of [0, 0.25, 0.5, 0.75, 1]) {
      const x = m.l + iw * f;
      s.append(svg("line", { x1: x, x2: x, y1: m.t, y2: H - m.b + 4, class: "gridline" }));
      s.append(svg("text", { x, y: H - 6, "text-anchor": "middle", class: "tick", text: Math.round(f * 100) + "%" }));
    }
    rows.forEach((row, i) => {
      const y = m.t + i * rowH + 6, h = rowH - 12;
      const total = row.parts.reduce((a, p) => a + p.value, 0) || 1;
      s.append(svg("text", { x: m.l - 10, y: y + h / 2 + 4, "text-anchor": "end", text: row.label }));
      let x = m.l;
      row.parts.forEach((p) => {
        const w = (p.value / total) * iw;
        if (w <= 0) return;
        const st = partStyles[p.key];
        s.append(svg("rect", { x: x + 1, y, width: Math.max(0, w - 2), height: h, rx: 3, fill: st.fill,
          onmousemove: (e) => APP.tip(e, `<b>${row.label}</b><br>${st.label}: ${p.value} of ${total} runs (${APP.pct(p.value, total)})`), onmouseleave: APP.untip }));
        if (w > 34) s.append(svg("text", { x: x + w / 2, y: y + h / 2 + 4, "text-anchor": "middle", class: "inbar", style: `fill:${st.ink || "#fff"}`, text: p.value }));
        x += w;
      });
    });
    host.append(s);
  };

  // Cost (log x) vs held-out accuracy. points [{label, x, y, cls, tip, dx, dy}]
  APP.scatter = function (host, pts, { title = "" } = {}) {
    const W = 560, H = 320, m = { t: 16, r: 24, b: 44, l: 46 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const lx = (v) => Math.log10(v);
    const x0 = Math.floor(Math.min(...pts.map((p) => lx(p.x)))), x1 = Math.ceil(Math.max(...pts.map((p) => lx(p.x)))); // whole decades
    const sx = (v) => m.l + ((lx(v) - x0) / (x1 - x0)) * iw, sy = (v) => m.t + ih * (1 - v);
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": title });
    for (const f of [0, 0.25, 0.5, 0.75, 1]) {
      s.append(svg("line", { x1: m.l, x2: W - m.r, y1: sy(f), y2: sy(f), class: f === 0 ? "axisline" : "gridline" }));
      s.append(svg("text", { x: m.l - 8, y: sy(f) + 4, "text-anchor": "end", class: "tick", text: f * 100 + "%" }));
    }
    for (let e = x0; e <= x1; e++) {
      const v = Math.pow(10, e);
      s.append(svg("line", { x1: sx(v), x2: sx(v), y1: m.t, y2: m.t + ih, class: "gridline" }));
      s.append(svg("text", { x: sx(v), y: H - 24, "text-anchor": "middle", class: "tick", text: "$" + (e < 0 ? v.toFixed(-e) : v) }));
    }
    s.append(svg("text", { x: m.l + iw / 2, y: H - 4, "text-anchor": "middle", class: "tick", text: "cost per run, log scale (list price; local runs at hosted-equivalent price)" }));
    pts.forEach((p) => {
      const g = svg("g", { class: p.cls });
      g.append(svg("circle", { cx: sx(p.x), cy: sy(p.y), r: p.hollow ? 6 : 7, fill: p.hollow ? "var(--surface)" : "var(--ap)", stroke: p.hollow ? "var(--ap)" : "var(--surface)", "stroke-width": p.hollow ? 2.5 : 2 }));
      g.append(svg("text", { x: sx(p.x) + (p.dx ?? 11), y: sy(p.y) + (p.dy ?? 4), "text-anchor": (p.dx ?? 11) < 0 ? "end" : "start", class: "pt-label", text: p.label }));
      g.append(svg("circle", { cx: sx(p.x), cy: sy(p.y), r: 16, fill: "transparent", onmousemove: (e) => APP.tip(e, p.tip), onmouseleave: APP.untip }));
      s.append(g);
    });
    host.append(s);
  };

  // A metric panel: area + line, faint grid, endpoint dot, alert marker at t=0, deploy markers, hover crosshair.
  APP.sparkPanel = function (host, sc, key, win) {
    const m = sc.metrics[key];
    const vals = m[win];
    const span = win === "6h" ? 360 : 10080, step = win === "6h" ? 4 : 120;
    const W = 300, H = 112, p = { t: 10, r: 8, b: 20, l: 8 };
    const iw = W - p.l - p.r, ih = H - p.t - p.b;
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.12;
    lo = lo >= 0 ? Math.max(0, lo - pad) : lo - pad; // never below zero for counts, rates and percentages
    hi += pad;
    const tAt = (i) => sc.now_min - span + i * step; // minutes relative to the alert
    const sx = (t) => p.l + ((t - (sc.now_min - span)) / span) * iw;
    const sy = (v) => p.t + ih * (1 - (v - lo) / (hi - lo));
    const pts = vals.map((v, i) => [sx(tAt(i)), sy(v)]);
    const line = "M" + pts.map((q) => q.map((n) => n.toFixed(1)).join(",")).join(" L");
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart spark", role: "img", "aria-label": `${key} over ${win}` });
    for (const f of [0, 0.5, 1]) s.append(svg("line", { x1: p.l, x2: W - p.r, y1: p.t + ih * f, y2: p.t + ih * f, class: "gridline" }));
    s.append(svg("path", { d: `${line} L${pts.at(-1)[0]},${p.t + ih} L${pts[0][0]},${p.t + ih} Z`, class: "spark-area" }));
    for (const d of sc.deploys) {
      if (d.t_min < sc.now_min - span || d.t_min > sc.now_min) continue;
      const x = sx(d.t_min);
      s.append(svg("line", { x1: x, x2: x, y1: p.t, y2: p.t + ih, class: "deploy-mark" }));
      s.append(svg("text", { x: x + 3, y: p.t + 9, class: "deploy-lbl", text: d.id }));
    }
    const ax = sx(0);
    s.append(svg("line", { x1: ax, x2: ax, y1: p.t - 4, y2: p.t + ih, class: "alert-mark" }));
    s.append(svg("path", { d: line, class: "spark-line" }));
    s.append(svg("circle", { cx: pts.at(-1)[0], cy: pts.at(-1)[1], r: 3, class: "spark-end" }));
    const labelT = (t) => {
      const d = new Date(Date.parse(sc.alert.fired_at) + t * 60000);
      return win === "6h" ? d.toISOString().slice(11, 16) : d.toISOString().slice(5, 10);
    };
    s.append(svg("text", { x: p.l, y: H - 5, class: "tick", text: labelT(sc.now_min - span) }));
    s.append(svg("text", { x: W - p.r, y: H - 5, class: "tick", "text-anchor": "end", text: labelT(sc.now_min) + " UTC" }));
    const cross = svg("line", { y1: p.t, y2: p.t + ih, class: "crosshair", visibility: "hidden" });
    const dot = svg("circle", { r: 3.5, class: "spark-end", visibility: "hidden" });
    s.append(cross, dot);
    const hit = svg("rect", { x: p.l, y: 0, width: iw, height: H, fill: "transparent" });
    hit.addEventListener("mousemove", (e) => {
      const r = s.getBoundingClientRect();
      const fx = ((e.clientX - r.left) / r.width) * W;
      const i = Math.max(0, Math.min(vals.length - 1, Math.round(((fx - p.l) / iw) * (vals.length - 1))));
      cross.setAttribute("x1", pts[i][0]); cross.setAttribute("x2", pts[i][0]); cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", pts[i][0]); dot.setAttribute("cy", pts[i][1]); dot.setAttribute("visibility", "visible");
      const rel = tAt(i);
      APP.tip(e, `<b>${vals[i]}${m.unit ? " " + m.unit : ""}</b><br>${labelT(rel)}${win === "7d" ? " " + new Date(Date.parse(sc.alert.fired_at) + rel * 60000).toISOString().slice(11, 16) : ""} UTC · ${rel >= 0 ? "+" : ""}${Math.round(rel)} min vs alert`);
    });
    hit.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); APP.untip(); });
    s.append(hit);
    host.append(s);
    return { lo, hi, last: vals.at(-1) };
  };
})();
