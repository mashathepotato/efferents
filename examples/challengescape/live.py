"""Live metrics page for the Challengescape multi-lab demo.

A stdlib HTTP server that watches each lab's ``out/`` directory and serves a
single page which polls ``/api/state`` every 2 seconds — so while
``launch_overnight.sh`` (or a real overnight run) executes, the run tables,
metric charts, and status tiles update in place. Read-only: it never launches
or mutates anything.

Usage:
    .venv/bin/python examples/challengescape/live.py [--port 8890]
"""
from __future__ import annotations

import argparse
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
LABS = ROOT / "labs"

RUNNING_WINDOW_S = 15  # runs.jsonl touched this recently => "running"


def _verdict(review: Path) -> str:
    if not review.is_file():
        return "not yet reviewed"
    m = re.search(r"\*\*Verdict: (.*?)\*\*", review.read_text(), re.DOTALL)
    return " ".join(m.group(1).split()).rstrip(".") if m else "—"


def _lab_state(lab_dir: Path) -> dict:
    cfg = yaml.safe_load((lab_dir / "efferents.yaml").read_text())
    metric = cfg["metric"]
    maximize = bool(cfg.get("maximize", True))
    runs_file = lab_dir / "out" / "runs.jsonl"

    runs, status = [], "pending"
    if runs_file.is_file():
        for line in runs_file.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            runs.append({
                "run_id": r["run_id"],
                "param": r.get("param"),
                "value": r.get("value"),
                "metric_value": r.get(metric),
            })
        age = time.time() - runs_file.stat().st_mtime
        status = "running" if age < RUNNING_WINDOW_S else "complete"
    planned = len(cfg.get("sweep", {}).get("values", []) or [None])

    best = None
    scored = [r for r in runs if isinstance(r["metric_value"], (int, float))]
    if scored:
        best = (max if maximize else min)(scored, key=lambda r: r["metric_value"])

    return {
        "name": lab_dir.name,
        "goal": " ".join(str(cfg["goal"]).split()),
        "metric": metric,
        "maximize": maximize,
        "param": cfg.get("sweep", {}).get("param"),
        "status": status,
        "runs": runs,
        "runs_planned": planned,
        "best": best,
        "verdict": _verdict(lab_dir / "out" / "journal" / "005_review.md"),
    }


def build_state() -> dict:
    labs = [_lab_state(d) for d in sorted(LABS.iterdir()) if d.is_dir()]
    reviews = []
    for review in sorted((ROOT / "shared_journal" / "reviews").glob("*.md")):
        text = review.read_text()
        fm = {
            k: v for k, v in re.findall(r"^(\w+): (.+)$", text.split("---")[1], re.M)
        } if text.startswith("---") else {}
        reviews.append({
            "file": review.name,
            "reviewer": fm.get("reviewer_lab", "?"),
            "reviewed": fm.get("reviewed_lab", "?"),
            "status": fm.get("status", ""),
        })
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "labs": labs,
        "reviews": reviews,
    }


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Challengescape labs — live</title>
<style>
  .viz-root {
    color-scheme: light;
    --surface-1: #fcfcfb; --surface-2: #f2f1ee; --border: #e2e1dc;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #8a897f;
    --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a;
    --good: #008300; --warning: #c98500;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) .viz-root {
      color-scheme: dark;
      --surface-1: #1a1a19; --surface-2: #232322; --border: #3a3936;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8a897f;
      --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
      --good: #35a835; --warning: #c98500;
    }
  }
  :root[data-theme="dark"] .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19; --surface-2: #232322; --border: #3a3936;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8a897f;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
    --good: #35a835; --warning: #c98500;
  }
  * { box-sizing: border-box; }
  body { margin: 0; }
  .viz-root {
    min-height: 100vh; background: var(--surface-1); color: var(--text-primary);
    font: 14px/1.45 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    padding: 20px; max-width: 1180px; margin: 0 auto;
  }
  h1 { font-size: 18px; margin: 0 0 2px; }
  .sub { color: var(--text-secondary); margin: 0 0 18px; font-size: 13px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; }
  .card { background: var(--surface-2); border: 1px solid var(--border);
          border-radius: 10px; padding: 14px 16px; }
  .card h2 { font-size: 14px; margin: 0; }
  .goal { color: var(--text-secondary); font-size: 12px; margin: 4px 0 10px; min-height: 3em; }
  .tiles { display: flex; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
  .tile { flex: 1 1 90px; }
  .tile .v { font-size: 21px; font-weight: 650; font-variant-numeric: tabular-nums; }
  .tile .k { font-size: 11px; color: var(--text-muted); text-transform: uppercase;
             letter-spacing: .04em; }
  .status { display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
            color: var(--text-secondary); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); }
  .running .dot { background: var(--warning); animation: pulse 1.2s infinite; }
  .complete .dot { background: var(--good); }
  @keyframes pulse { 50% { opacity: .3; } }
  svg text { fill: var(--text-secondary); font-size: 11px; }
  svg .grid-line { stroke: var(--border); stroke-width: 1; }
  svg .axis { stroke: var(--border); }
  table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px;
          font-variant-numeric: tabular-nums; }
  th { text-align: left; color: var(--text-muted); font-weight: 500;
       border-bottom: 1px solid var(--border); padding: 3px 6px; }
  td { padding: 3px 6px; border-bottom: 1px solid var(--border); }
  tr.best td { font-weight: 650; }
  .verdict { font-size: 12px; color: var(--text-secondary); margin-top: 8px; }
  .reviews { margin-top: 20px; }
  .reviews h2 { font-size: 14px; }
  .reviews li { font-size: 13px; color: var(--text-secondary); margin: 3px 0; }
  .adopted { color: var(--good); font-weight: 600; }
  #tooltip { position: fixed; pointer-events: none; background: var(--surface-2);
             border: 1px solid var(--border); border-radius: 6px; padding: 6px 9px;
             font-size: 12px; display: none; z-index: 10; color: var(--text-primary);
             box-shadow: 0 2px 8px rgba(0,0,0,.15); }
</style></head>
<body><div class="viz-root">
  <h1>Challengescape labs — live</h1>
  <p class="sub">Three autonomous labs · real runs, provenance-tracked ·
    updates every 2s · <span id="stamp">connecting…</span></p>
  <div class="grid" id="labs"></div>
  <div class="reviews card"><h2>Cross-lab reviews</h2><ul id="reviews"></ul></div>
  <div id="tooltip"></div>
<script>
const SERIES = ["--series-1", "--series-2", "--series-3"];
const tooltip = document.getElementById("tooltip");

function fmt(v) {
  if (v == null) return "—";
  return typeof v === "number" ? +v.toPrecision(4) : v;
}

function chart(lab, color) {
  const runs = lab.runs.filter(r => typeof r.metric_value === "number");
  const W = 320, H = 150, m = {t: 12, r: 14, b: 26, l: 46};
  if (!runs.length) return `<svg width="${W}" height="${H}"><text x="${W/2}" y="${H/2}" text-anchor="middle">waiting for first run…</text></svg>`;
  const ys = runs.map(r => r.metric_value);
  let lo = Math.min(...ys), hi = Math.max(...ys);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
  const x = i => m.l + (runs.length === 1 ? 0.5 : i / (runs.length - 1)) * (W - m.l - m.r);
  const y = v => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
  let s = `<svg width="${W}" height="${H}" style="max-width:100%">`;
  for (let g = 0; g < 3; g++) {
    const gy = m.t + g * (H - m.t - m.b) / 2;
    const gv = hi - g * (hi - lo) / 2;
    s += `<line class="grid-line" x1="${m.l}" y1="${gy}" x2="${W - m.r}" y2="${gy}"/>`;
    s += `<text x="${m.l - 6}" y="${gy + 4}" text-anchor="end">${fmt(gv)}</text>`;
  }
  s += `<line class="axis" x1="${m.l}" y1="${H - m.b}" x2="${W - m.r}" y2="${H - m.b}"/>`;
  const path = runs.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r.metric_value)}`).join("");
  s += `<path d="${path}" fill="none" stroke="var(${color})" stroke-width="2"/>`;
  const bestId = lab.best && lab.best.run_id;
  runs.forEach((r, i) => {
    const isBest = r.run_id === bestId;
    s += `<circle cx="${x(i)}" cy="${y(r.metric_value)}" r="${isBest ? 5.5 : 4.5}"
      fill="var(${color})" stroke="var(--surface-2)" stroke-width="2"
      data-tip="${r.run_id} · ${lab.param}=${r.value} · ${lab.metric}=${fmt(r.metric_value)}"/>`;
    if (isBest) s += `<text x="${x(i)}" y="${y(r.metric_value) - 10}" text-anchor="middle"
      style="fill:var(--text-primary);font-weight:650">${fmt(r.metric_value)}</text>`;
    s += `<text x="${x(i)}" y="${H - m.b + 14}" text-anchor="middle">${fmt(r.value)}</text>`;
  });
  s += `<text x="${(m.l + W - m.r) / 2}" y="${H - 2}" text-anchor="middle">${lab.param}</text>`;
  return s + "</svg>";
}

function render(state) {
  document.getElementById("stamp").textContent = "updated " + new Date().toLocaleTimeString();
  const labsEl = document.getElementById("labs");
  labsEl.innerHTML = state.labs.map((lab, i) => `
    <div class="card">
      <h2>${lab.name}</h2>
      <p class="goal">${lab.goal}</p>
      <div class="tiles">
        <div class="tile"><div class="v">${lab.best ? fmt(lab.best.metric_value) : "—"}</div>
          <div class="k">best ${lab.metric}</div></div>
        <div class="tile"><div class="v">${lab.runs.length}/${lab.runs_planned}</div>
          <div class="k">runs</div></div>
        <div class="tile"><div class="status ${lab.status}"><span class="dot"></span>${lab.status}</div>
          <div class="k">status</div></div>
      </div>
      ${chart(lab, SERIES[i % SERIES.length])}
      <table><tr><th>run</th><th>${lab.param}</th><th>${lab.metric}</th></tr>
        ${lab.runs.map(r => `<tr class="${lab.best && r.run_id === lab.best.run_id ? "best" : ""}">
          <td>${r.run_id}</td><td>${fmt(r.value)}</td><td>${fmt(r.metric_value)}</td></tr>`).join("")}
      </table>
      <div class="verdict"><strong>Review:</strong> ${lab.verdict}</div>
    </div>`).join("");
  document.getElementById("reviews").innerHTML = state.reviews.map(r => `
    <li><strong>${r.reviewer}</strong> → ${r.reviewed}
      ${r.status ? `<span class="adopted">· ${r.status}</span>` : ""}</li>`).join("")
    || "<li>none yet</li>";
  labsEl.querySelectorAll("circle[data-tip]").forEach(c => {
    c.addEventListener("mousemove", e => {
      tooltip.style.display = "block";
      tooltip.textContent = c.dataset.tip;
      tooltip.style.left = (e.clientX + 12) + "px";
      tooltip.style.top = (e.clientY - 10) + "px";
    });
    c.addEventListener("mouseleave", () => tooltip.style.display = "none");
  });
}

async function tick() {
  try {
    const res = await fetch("/api/state");
    render(await res.json());
  } catch (e) {
    document.getElementById("stamp").textContent = "reconnecting…";
  }
}
tick();
setInterval(tick, 2000);
</script>
</div></body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (stdlib API)
        if self.path == "/api/state":
            body = json.dumps(build_state()).encode()
            ctype = "application/json"
        elif self.path in ("/", "/index.html"):
            body = PAGE.encode()
            ctype = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8890)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _Handler)
    print(f"live dashboard: http://127.0.0.1:{args.port}/  (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
