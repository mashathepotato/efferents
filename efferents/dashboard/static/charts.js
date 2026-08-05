/* Efferents charts — lab-agnostic, spec-driven SVG charts.
 *
 * Framework contract: a lab (or example app) never hardcodes a chart. It
 * builds chart *specs* — plain objects — and hands them to a renderer that
 * measures its container and redraws on resize, so charts are never squished
 * or scaled-down bitmaps of a fixed-width SVG.
 *
 *   const specs = EfferentsCharts.specsFromRuns(runRecords, chartsConfig, {
 *     metric: "headline_metric",   // fallback when a run doesn't declare one
 *     param: "swept_param",
 *     maximize: true,
 *     color: "var(--series-1)",
 *   });
 *   EfferentsCharts.renderAll(containerEl, specs);
 *
 * `chartsConfig` is the lab-owned `charts:` list from its YAML config, e.g.:
 *
 *   charts:
 *     - metric: clean_fa_drop_k1_to_k3   # y — any numeric field of a run
 *       x: pool_n                        # x tick labels — "index", "param",
 *                                        # or any run field (default: param)
 *       x_label: pool size N             # axis caption (default: x field)
 *       type: line                       # any key in EfferentsCharts.types
 *       label: quorum precision drop     # heading (default: metric name)
 *       target: 0.20                     # optional reference line
 *       target_label: gate ≥ 0.20
 *       maximize: true                   # which point gets the "best" mark
 *
 * With no config, specs are inferred: runs are grouped by the (metric, param)
 * pair each run record declares, one chart per group — heterogeneous history
 * (a lab that changed metrics between cycles) becomes one chart per cycle.
 *
 * To branch out with a new chart shape, register a type — it receives the
 * spec and the measured pixel width and returns an SVG string:
 *
 *   EfferentsCharts.register("box", (spec, width) => { ... return svg; });
 *
 * Built-ins: line, bar, spark. Colors resolve through theme tokens with
 * plain fallbacks, so the same chart works inside and outside the research
 * theme. Interactivity stays host-owned: points carry data-tip attributes
 * (plus <title> fallbacks) for whatever tooltip the page already has.
 */
(function (root) {
  "use strict";

  const TEXT = "var(--dim, #8494a7)";
  const GRID = "var(--line-soft, #e6ebf1)";
  const AXIS = "var(--line, #d4dbe4)";
  const BG = "var(--panel, #ffffff)";
  const ACCENT = "var(--orange, #f06c00)";
  const TARGET = "var(--danger, #ae4148)";

  const esc = (s) => String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const fmt = (v) => (v == null || (typeof v === "number" && !isFinite(v)))
    ? "—"
    : (typeof v === "number" ? String(+v.toPrecision(4)) : String(v));
  const isNum = (v) => typeof v === "number" && isFinite(v);

  function niceTicks(lo, hi, count) {
    if (lo === hi) { lo -= 1; hi += 1; }
    const span = hi - lo;
    const mag = Math.pow(10, Math.floor(Math.log10(span / Math.max(1, count))));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag)
      .find((s) => span / s <= count) || 10 * mag;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) {
      out.push(+v.toPrecision(12));
    }
    return out;
  }

  /* Shared geometry: y domain, margins sized to the y labels, scales, and the
   * grid/axis/target furniture every axis-bearing chart type starts from. */
  function frame(spec, width) {
    const pts = spec.points || [];
    const H = Math.max(150, Math.min(340, Math.round(
      width * (spec.aspect || 0.42))));
    const ys = pts.map((p) => p.y).filter(isNum);
    if (spec.target && isNum(spec.target.value)) ys.push(spec.target.value);
    // Bars encode value as length, so their domain must include zero —
    // a truncated bar axis turns small deltas into visual cliffs.
    if (spec.type === "bar" && spec.zeroBase !== false) ys.push(0);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    if (!ys.length) { lo = 0; hi = 1; }
    if (lo === hi) { lo -= Math.abs(lo) * 0.1 || 1; hi += Math.abs(hi) * 0.1 || 1; }
    const pad = (hi - lo) * 0.12;
    const yTicks = niceTicks(lo - pad, hi + pad, Math.max(2, Math.round(H / 60)));
    lo = Math.min(lo - pad, yTicks[0]);
    hi = Math.max(hi + pad, yTicks[yTicks.length - 1]);
    const labelW = Math.max(...yTicks.map((t) => fmt(t).length), 2) * 6.6;
    const m = {
      t: 12,
      r: 14,
      b: spec.xLabel ? 44 : 30,
      l: Math.min(86, 14 + labelW),
    };
    const plotW = width - m.l - m.r;
    const x = (i) => m.l + (pts.length < 2 ? 0.5 : i / (pts.length - 1)) * plotW;
    const band = pts.length ? plotW / pts.length : plotW;
    const xBand = (i) => m.l + (i + 0.5) * band;
    const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
    return { W: width, H, m, plotW, band, x, xBand, y, yTicks, pts };
  }

  function furniture(spec, g) {
    let s = "";
    g.yTicks.forEach((t) => {
      s += `<line x1="${g.m.l}" y1="${g.y(t)}" x2="${g.W - g.m.r}" y2="${g.y(t)}"
        stroke="${GRID}" stroke-width="1"/>`;
      s += `<text x="${g.m.l - 7}" y="${g.y(t) + 3.5}" text-anchor="end"
        fill="${TEXT}" font-size="10">${fmt(t)}</text>`;
    });
    s += `<line x1="${g.m.l}" y1="${g.H - g.m.b}" x2="${g.W - g.m.r}"
      y2="${g.H - g.m.b}" stroke="${AXIS}" stroke-width="1"/>`;
    if (spec.target && isNum(spec.target.value)) {
      const ty = g.y(spec.target.value);
      s += `<line x1="${g.m.l}" y1="${ty}" x2="${g.W - g.m.r}" y2="${ty}"
        stroke="${TARGET}" stroke-width="1" stroke-dasharray="3 4"/>`;
      s += `<text x="${g.W - g.m.r}" y="${ty - 5}" text-anchor="end"
        fill="${TARGET}" font-size="9">${esc(spec.target.label ||
          "target " + fmt(spec.target.value))}</text>`;
    }
    if (spec.xLabel) {
      s += `<text x="${(g.m.l + g.W - g.m.r) / 2}" y="${g.H - 4}"
        text-anchor="middle" fill="${TEXT}" font-size="10"
        letter-spacing=".05em">${esc(spec.xLabel)}</text>`;
    }
    return s;
  }

  /* Draw every x label only when they fit; otherwise thin them out. */
  function xLabels(g, xOf) {
    const every = Math.max(1, Math.ceil(
      (g.pts.length * 46) / Math.max(1, g.plotW)));
    return g.pts.map((p, i) => (i % every || p.xTick == null) ? "" :
      `<text x="${xOf(i)}" y="${g.H - g.m.b + 15}" text-anchor="middle"
        fill="${TEXT}" font-size="10">${esc(fmt(p.xTick))}</text>`).join("");
  }

  const tipAttr = (p) => (p.label ? `data-tip="${esc(p.label)}"` : "");
  const tipChild = (p) => (p.label ? `<title>${esc(p.label)}</title>` : "");

  function open(spec, g) {
    return `<svg width="${g.W}" height="${g.H}" viewBox="0 0 ${g.W} ${g.H}"
      role="img" aria-label="${esc(spec.title || spec.yLabel || "chart")}"
      style="display:block;max-width:100%">`;
  }

  function empty(spec, width) {
    const H = 150;
    return `<svg width="${width}" height="${H}" viewBox="0 0 ${width} ${H}"
      role="img" aria-label="no data" style="display:block;max-width:100%">
      <text x="${width / 2}" y="${H / 2}" text-anchor="middle" fill="${TEXT}"
        font-size="10" letter-spacing=".07em">WAITING FOR FIRST RUN</text>
      </svg>`;
  }

  const types = {};
  function register(name, fn) { types[name] = fn; }

  register("line", (spec, width) => {
    const g = frame(spec, width);
    if (!g.pts.length) return empty(spec, width);
    const color = spec.color || "var(--mustard, #d4a017)";
    let s = open(spec, g) + furniture(spec, g);
    s += `<path fill="none" stroke="${color}" stroke-width="1.8"
      d="${g.pts.map((p, i) => `${i ? "L" : "M"}${g.x(i)},${g.y(p.y)}`).join("")}"/>`;
    g.pts.forEach((p, i) => {
      const best = p.best;
      s += `<circle cx="${g.x(i)}" cy="${g.y(p.y)}" r="${best ? 5 : 3.5}"
        fill="${best ? ACCENT : BG}" stroke="${best ? ACCENT : color}"
        stroke-width="1.8" ${tipAttr(p)}>${tipChild(p)}</circle>`;
      if (best) {
        s += `<text x="${g.x(i)}" y="${g.y(p.y) - 10}" text-anchor="middle"
          fill="${ACCENT}" font-size="11" font-weight="650">${fmt(p.y)}</text>`;
      }
    });
    return s + xLabels(g, g.x) + "</svg>";
  });

  register("bar", (spec, width) => {
    const g = frame(spec, width);
    if (!g.pts.length) return empty(spec, width);
    const color = spec.color || "var(--mustard, #d4a017)";
    const w = Math.max(3, g.band * 0.62);
    const y0 = g.y(Math.max(0, g.yTicks[0]));
    let s = open(spec, g) + furniture(spec, g);
    g.pts.forEach((p, i) => {
      const yv = g.y(p.y);
      s += `<rect x="${g.xBand(i) - w / 2}" y="${Math.min(yv, y0)}"
        width="${w}" height="${Math.max(1, Math.abs(y0 - yv))}"
        fill="${p.best ? ACCENT : color}" ${tipAttr(p)}>${tipChild(p)}</rect>`;
    });
    return s + xLabels(g, g.xBand) + "</svg>";
  });

  /* Axis-free miniature for cards and list rows. */
  register("spark", (spec, width) => {
    const pts = (spec.points || []).filter((p) => isNum(p.y));
    const W = Math.min(width, spec.width || 140), H = 34;
    if (pts.length < 2) return "";
    const ys = pts.map((p) => p.y);
    const lo = Math.min(...ys), hi = Math.max(...ys);
    const x = (i) => 2 + (i / (pts.length - 1)) * (W - 4);
    const y = (v) => 3 + (1 - (v - lo) / ((hi - lo) || 1)) * (H - 6);
    return `<svg width="${W}" height="${H}" role="img" aria-label="trend">
      <path fill="none" stroke="${spec.color || "var(--mustard, #d4a017)"}"
        stroke-width="1.8"
        d="${pts.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.y)}`).join("")}"/>
      </svg>`;
  });

  /* ---- spec builders ---------------------------------------------------- */

  function markBest(points, maximize) {
    if (!points.length) return points;
    const pick = maximize === false ? Math.min : Math.max;
    const best = pick(...points.map((p) => p.y));
    const i = points.findIndex((p) => p.y === best);
    if (i >= 0) points[i] = Object.assign({}, points[i], { best: true });
    return points;
  }

  function pointsFor(rows, metric, xField, param) {
    return rows.filter((r) => isNum(r[metric])).map((r, i) => {
      const xTick = xField === "index" ? i
        : (xField && xField !== "param") ? r[xField]
        : (r.value != null ? r.value : i);
      const pname = r.param || param;  // a run's own declared param wins
      return {
        y: r[metric],
        xTick,
        label: [
          r.run_id,
          pname && r.value != null ? `${pname}=${fmt(r.value)}` : null,
          `${metric}=${fmt(r[metric])}`,
        ].filter(Boolean).join(" · "),
      };
    });
  }

  function specsFromRuns(runs, charts, defaults) {
    const d = defaults || {};
    const rows = (runs || []).filter((r) => r && typeof r === "object");

    if (Array.isArray(charts) && charts.length) {
      return charts.filter((c) => c && c.metric).map((c) => {
        const param = c.x && c.x !== "index" && c.x !== "param" ? c.x : d.param;
        const maximize = c.maximize == null ? d.maximize : !!c.maximize;
        return {
          type: c.type || "line",
          title: c.label || c.metric,
          yLabel: c.metric,
          xLabel: c.x_label ||
            (c.x === "index" ? "run" : (param || d.param || "run")),
          color: c.color || d.color,
          target: isNum(c.target)
            ? { value: c.target, label: c.target_label }
            : null,
          points: markBest(pointsFor(rows, c.metric, c.x, param), maximize),
        };
      });
    }

    // No config: one chart per (metric, param) pair the run records declare.
    const groups = new Map();
    rows.forEach((r) => {
      const metric = r.metric || d.metric;
      if (!metric || !isNum(r[metric])) return;
      const param = r.param || d.param || "run";
      const key = `${metric} ${param}`;
      if (!groups.has(key)) groups.set(key, { metric, param, rows: [] });
      groups.get(key).rows.push(r);
    });
    return Array.from(groups.values()).map((grp) => ({
      type: "line",
      title: grp.metric,
      yLabel: grp.metric,
      xLabel: grp.param,
      color: d.color,
      points: markBest(pointsFor(grp.rows, grp.metric, null, grp.param),
        d.maximize),
    }));
  }

  /* ---- mounting --------------------------------------------------------- */

  function render(el, spec) {
    const draw = () => {
      const width = Math.max(240, el.clientWidth || 320);
      const type = types[spec.type] || types.line;
      el.innerHTML = type(spec, width);
    };
    draw();
    if (root.ResizeObserver && !el.__efcResize) {
      let timer = null;
      const ro = new ResizeObserver(() => {
        clearTimeout(timer);
        timer = setTimeout(draw, 120);
      });
      ro.observe(el);
      el.__efcResize = ro;
    }
  }

  /* One <figure class="efc-chart"> per spec; the host styles the grid. */
  function renderAll(el, specs) {
    el.innerHTML = "";
    specs.forEach((spec) => {
      const fig = document.createElement("figure");
      fig.className = "efc-chart";
      if (spec.title) {
        const cap = document.createElement("figcaption");
        cap.className = "efc-caption";
        cap.textContent = spec.title;
        fig.appendChild(cap);
      }
      const body = document.createElement("div");
      body.className = "efc-body";
      fig.appendChild(body);
      el.appendChild(fig);
      render(body, spec);
    });
  }

  root.EfferentsCharts = {
    types, register, render, renderAll, specsFromRuns, fmt,
  };
})(typeof window !== "undefined" ? window : globalThis);
