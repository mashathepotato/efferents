"""Live workspace for the Challengescape multi-lab demo.

A stdlib HTTP server that watches each lab's directory and serves a full-screen
single-page app polling ``/api/state`` every 2 seconds:

- **Overview** — one summary card per lab (the entrance: click to drill in),
  a network map of how the labs connect through shared-journal reviews and
  shared themes, and a "submit a new lab" button that hands you the terminal
  entry point for adding another challenge.
- **Lab detail** — status tiles, the metric-vs-parameter chart, the run table,
  and the lab's agent pipeline (student / executor / writer / supervisor-
  reviewer roles derived from the journal artifacts), each artifact readable
  inline.

Read-only: it never launches or mutates anything.

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
from urllib.parse import parse_qs, urlparse

import yaml

ROOT = Path(__file__).resolve().parent
LABS = ROOT / "labs"
REVIEWS = ROOT / "shared_journal" / "reviews"

RUNNING_WINDOW_S = 15  # runs.jsonl touched this recently => "running"

# Journal artifacts mapped to the agent role that produces them. For these
# offline labs the roles are derived from the recorded artifacts; a live lab
# (efferents start) runs the same roles as actual supervisor-student agents.
ARTIFACT_ROLES: list[tuple[str, str, str]] = [
    ("challenge.md", "Ingestion", "Challenge card"),
    ("questions_for_poc.md", "Outreach", "Questions for the challenge POC"),
    ("out/journal/001_hypothesis.md", "Student", "Hypothesis"),
    ("out/journal/002_experiment_plan.md", "Student", "Experiment plan"),
    ("out/journal/003_results.md", "Executor", "Results"),
    ("out/journal/004_research_memo.md", "Writer", "Research memo"),
    ("out/journal/004_reviewed_memo.md", "Writer", "Research memo"),
    ("out/journal/005_review.md", "Supervisor · Reviewer", "Intra-lab review"),
    ("out/journal/006_next_experiment_v2.md", "Student", "Revised plan (cross-lab adoption)"),
]

# Controlled vocabulary for the network map's theme edges: a lab is linked to a
# theme when its challenge card or goal mentions any of the keywords.
THEMES: dict[str, tuple[str, ...]] = {
    "climate": ("climate",),
    "time series": ("time series", "temporal", "autocorrelation", "rolling"),
    "early warning": ("early-warning", "early warning", "lead time", "tipping"),
    "trust & stability": ("trust", "stability", "interpretab"),
    "risk & decisions": ("risk", "false alarm", "false-alarm", "planner", "flag"),
    "forecasting": ("forecast",),
}


def _verdict(review: Path) -> str:
    if not review.is_file():
        return "not yet reviewed"
    m = re.search(r"\*\*Verdict: (.*?)\*\*", review.read_text(), re.DOTALL)
    return " ".join(m.group(1).split()).rstrip(".") if m else "—"


def _challenge_title(lab_dir: Path) -> str:
    card = lab_dir / "challenge.md"
    if card.is_file():
        m = re.search(r'^> \*\*"(.+?)"\*\*', card.read_text(), re.M | re.DOTALL)
        if m:
            # Quotes wrap across lines with a leading "> " continuation marker.
            return " ".join(t for t in m.group(1).split() if t != ">")
    return lab_dir.name


def _themes_for(lab_dir: Path, goal: str) -> list[str]:
    text = goal.lower()
    card = lab_dir / "challenge.md"
    if card.is_file():
        text += " " + card.read_text().lower()
    return [t for t, kws in THEMES.items() if any(k in text for k in kws)]


def _pipeline(lab_dir: Path) -> list[dict]:
    out = []
    for rel, role, title in ARTIFACT_ROLES:
        path = lab_dir / rel
        if path.is_file():
            out.append({
                "file": rel,
                "role": role,
                "title": title,
                "mtime": time.strftime("%H:%M:%S", time.localtime(path.stat().st_mtime)),
            })
    return out


def _lab_state(lab_dir: Path) -> dict:
    cfg = yaml.safe_load((lab_dir / "efferents.yaml").read_text())
    metric = cfg["metric"]
    maximize = bool(cfg.get("maximize", True))
    goal = " ".join(str(cfg["goal"]).split())
    runs_file = lab_dir / "out" / "runs.jsonl"

    runs, status = [], "pending"
    if runs_file.is_file():
        for line in runs_file.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            runs.append({
                "run_id": r["run_id"],
                "value": r.get("value"),
                "metric_value": r.get(metric),
            })
        age = time.time() - runs_file.stat().st_mtime
        status = "running" if age < RUNNING_WINDOW_S else "complete"

    best = None
    scored = [r for r in runs if isinstance(r["metric_value"], (int, float))]
    if scored:
        best = (max if maximize else min)(scored, key=lambda r: r["metric_value"])

    return {
        "name": lab_dir.name,
        "path": f"examples/challengescape/labs/{lab_dir.name}",
        "challenge": _challenge_title(lab_dir),
        "goal": goal,
        "metric": metric,
        "maximize": maximize,
        "param": cfg.get("sweep", {}).get("param"),
        "status": status,
        "runs": runs,
        "runs_planned": len(cfg.get("sweep", {}).get("values", []) or [None]),
        "best": best,
        "verdict": _verdict(lab_dir / "out" / "journal" / "005_review.md"),
        "pipeline": _pipeline(lab_dir),
        "themes": _themes_for(lab_dir, goal),
    }


def build_state() -> dict:
    labs = [_lab_state(d) for d in sorted(LABS.iterdir()) if d.is_dir()]
    reviews = []
    for review in sorted(REVIEWS.glob("*.md")):
        text = review.read_text()
        fm = dict(re.findall(r"^(\w+): (.+)$", text.split("---")[1], re.M)) \
            if text.startswith("---") else {}
        reviews.append({
            "file": review.name,
            "reviewer": fm.get("reviewer_lab", "?"),
            "reviewed": fm.get("reviewed_lab", "?"),
            "adopted": fm.get("status", "").startswith("adopted"),
        })
    # No timestamp in the payload: the client re-renders only when the payload
    # bytes change, so an idle lab must produce a byte-identical response.
    return {
        "labs": labs,
        "reviews": reviews,
        "themes": list(THEMES),
    }


def read_artifact(lab: str, rel: str) -> str | None:
    """Whitelisted artifact reader — only files this app itself lists."""
    if lab == "shared":
        if rel == "index.md" and (ROOT / "shared_journal" / "index.md").is_file():
            return (ROOT / "shared_journal" / "index.md").read_text()
        if re.fullmatch(r"[\w.\-]+\.md", rel) and (REVIEWS / rel).is_file():
            return (REVIEWS / rel).read_text()
        return None
    lab_dir = LABS / lab
    if not lab_dir.is_dir() or lab_dir.parent != LABS:
        return None
    if rel not in {entry[0] for entry in ARTIFACT_ROLES}:
        return None
    path = lab_dir / rel
    return path.read_text() if path.is_file() else None


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Challengescape labs — live</title>
<style>
  :root { color-scheme: light;
    --surface-1: #fcfcfb; --surface-2: #f2f1ee; --surface-3: #e9e8e3;
    --border: #e2e1dc;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #8a897f;
    --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a;
    --good: #008300; --warning: #c98500; --accent: #2a78d6;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) { color-scheme: dark;
      --surface-1: #1a1a19; --surface-2: #232322; --surface-3: #2c2c2a;
      --border: #3a3936;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8a897f;
      --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
      --good: #35a835; --warning: #c98500; --accent: #3987e5;
    }
  }
  :root[data-theme="dark"] { color-scheme: dark;
    --surface-1: #1a1a19; --surface-2: #232322; --surface-3: #2c2c2a;
    --border: #3a3936;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8a897f;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
    --good: #35a835; --warning: #c98500; --accent: #3987e5;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100vh; background: var(--surface-1);
    color: var(--text-primary);
    font: 14px/1.5 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
  #app { padding: 22px clamp(16px, 3vw, 44px) 48px; }
  header { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
    margin-bottom: 18px; }
  h1 { font-size: 19px; margin: 0; }
  .sub { color: var(--text-secondary); font-size: 13px; flex: 1; }
  .btn { background: var(--accent); color: #fff; border: 0; border-radius: 8px;
    padding: 8px 14px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .btn.ghost { background: transparent; color: var(--accent);
    border: 1px solid var(--accent); }
  a { color: var(--accent); text-decoration: none; }
  .grid { display: grid; gap: 16px;
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); }
  .card { background: var(--surface-2); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px 18px; }
  .card.click { cursor: pointer; transition: border-color .15s, transform .15s; }
  .card.click:hover { border-color: var(--accent); transform: translateY(-2px); }
  .card h2 { font-size: 14px; margin: 0; display: flex; align-items: center; gap: 8px; }
  .swatch { width: 10px; height: 10px; border-radius: 3px; flex: none; }
  .challenge { color: var(--text-secondary); font-size: 12.5px; font-style: italic;
    margin: 6px 0 10px; }
  .tiles { display: flex; gap: 14px; margin: 10px 0; flex-wrap: wrap; }
  .tile .v { font-size: 22px; font-weight: 650; font-variant-numeric: tabular-nums; }
  .tile .k { font-size: 10.5px; color: var(--text-muted); text-transform: uppercase;
    letter-spacing: .05em; }
  .status { display: inline-flex; align-items: center; gap: 6px; font-size: 13px;
    color: var(--text-secondary); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); }
  .running .dot { background: var(--warning); animation: pulse 1.2s infinite; }
  .complete .dot { background: var(--good); }
  @keyframes pulse { 50% { opacity: .3; } }
  svg text { fill: var(--text-secondary); font-size: 11px; }
  svg .grid-line { stroke: var(--border); }
  svg .axis { stroke: var(--border); }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px;
    font-variant-numeric: tabular-nums; margin-top: 8px; }
  th { text-align: left; color: var(--text-muted); font-weight: 500;
    border-bottom: 1px solid var(--border); padding: 4px 6px; }
  td { padding: 4px 6px; border-bottom: 1px solid var(--border); }
  tr.best td { font-weight: 650; }
  .verdict { font-size: 12.5px; color: var(--text-secondary); margin-top: 10px; }
  .themes { margin-top: 10px; }
  .chip { display: inline-block; background: var(--surface-3); border-radius: 20px;
    padding: 2px 10px; font-size: 11.5px; color: var(--text-secondary); margin: 2px 3px 0 0; }
  .section { margin-top: 26px; }
  .section > h2 { font-size: 15px; margin: 0 0 10px; }
  .pipeline { list-style: none; margin: 0; padding: 0; }
  .pipeline li { display: flex; gap: 10px; align-items: baseline; padding: 7px 0;
    border-bottom: 1px solid var(--border); font-size: 13px; flex-wrap: wrap; }
  .role { flex: none; width: 160px; font-weight: 600; font-size: 12px; }
  .pipeline .t { color: var(--text-muted); font-size: 11.5px; margin-left: auto; }
  .viewer { background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 10px; padding: 18px 22px; margin-top: 12px; max-height: 60vh;
    overflow: auto; font-size: 13.5px; }
  .viewer h1 { font-size: 17px; } .viewer h2 { font-size: 14.5px; }
  .viewer table { font-size: 12px; }
  .viewer code { background: var(--surface-3); border-radius: 4px; padding: 1px 5px;
    font-size: 12px; }
  .viewer blockquote { border-left: 3px solid var(--accent); margin: 8px 0;
    padding: 2px 12px; color: var(--text-secondary); }
  .back { font-size: 13px; }
  .net-wrap { overflow-x: auto; text-align: center; }
  .net-node { cursor: pointer; }
  #modal { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: none;
    align-items: center; justify-content: center; z-index: 20; }
  #modal .box { background: var(--surface-2); border: 1px solid var(--border);
    border-radius: 12px; max-width: 720px; width: calc(100% - 40px); padding: 22px 24px; }
  #modal h2 { margin: 0 0 8px; font-size: 16px; }
  #modal p { color: var(--text-secondary); font-size: 13px; }
  #modal pre { background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px; font-size: 12px; white-space: pre-wrap;
    max-height: 40vh; overflow: auto; }
  .modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
  #tooltip { position: fixed; pointer-events: none; background: var(--surface-2);
    border: 1px solid var(--border); border-radius: 6px; padding: 6px 9px;
    font-size: 12px; display: none; z-index: 30;
    box-shadow: 0 2px 8px rgba(0,0,0,.15); }
</style></head>
<body>
<div id="app"></div>
<div id="tooltip"></div>
<div id="modal"><div class="box">
  <h2>Submit a new lab</h2>
  <p>Copy this into a terminal session running your coding agent (Claude Code
     or similar) from the efferents repo root. Paste a Challengescape card in
     the marked spot — the agent scaffolds the lab, runs it, and it appears
     here on the next refresh.</p>
  <pre id="entrypoint">Read examples/challengescape/README.md and examples/challengescape/templates/.
Create a new lab under examples/challengescape/labs/lab_NN_&lt;slug&gt;/ for this
Challengescape challenge:

  &lt;PASTE THE CHALLENGE CARD HERE — title, description, point of contact&gt;

Follow the repo-adapter contract (train prints {"checkpoint": ...}, eval prints
{"metrics": {...}}), keep the data synthetic or public so it runs offline, add
a challenge.md and questions_for_poc.md from the templates, then run:

  .venv/bin/efferents run examples/challengescape/labs/&lt;new lab&gt; --approve \
      --out examples/challengescape/labs/&lt;new lab&gt;/out
  .venv/bin/python examples/challengescape/crosslab.py

Finally write an intra-lab review (005_review.md) and one cross-lab review,
following examples/challengescape/prompts/.</pre>
  <div class="modal-actions">
    <button class="btn ghost" onclick="closeModal()">Close</button>
    <button class="btn" onclick="copyEntry(this)">Copy to clipboard</button>
  </div>
</div></div>
<script>
const SERIES = ["--series-1", "--series-2", "--series-3", "--series-1", "--series-2"];
const REPO_URL = "https://github.com/mashathepotato/efferents";
const CHALLENGESCAPE_URL = "https://encode-challengescape.pillar.vc/";
const tooltip = document.getElementById("tooltip");
let STATE = null;
let lastPayload = "";      // re-render only when the state bytes change
let openArtifact = null;   // {lab, file} persisted across refreshes

const fmt = v => v == null ? "—" : (typeof v === "number" ? +v.toPrecision(4) : v);
const seriesFor = name =>
  SERIES[(STATE ? STATE.labs.findIndex(l => l.name === name) : 0) % SERIES.length];

/* ---------- tiny markdown renderer (headings, tables, lists, emphasis) --- */
function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function inline(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[(.+?)\]\((.+?)\)/g, "$1");
}
function renderMd(text) {
  const lines = text.split("\n");
  let html = "", i = 0, inList = false;
  if (lines[0] === "---") {                       // frontmatter → key/value block
    const end = lines.indexOf("---", 1);
    if (end > 0) {
      html += "<p>" + lines.slice(1, end).map(l => `<code>${esc(l)}</code>`).join(" ") + "</p>";
      i = end + 1;
    }
  }
  let para = [];
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  const flushPara = () => {
    if (para.length) { html += `<p>${inline(para.join(" "))}</p>`; para = []; }
  };
  for (; i < lines.length; i++) {
    const l = lines[i];
    if (/^\|/.test(l)) {                          // table
      closeList(); flushPara();
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i])) { rows.push(lines[i]); i++; }
      i--;
      html += "<table>" + rows.filter(r => !/^\|[\s\-|]+\|$/.test(r)).map((r, ri) => {
        const cells = r.split("|").slice(1, -1).map(c => inline(c.trim()));
        const tag = ri === 0 ? "th" : "td";
        return "<tr>" + cells.map(c => `<${tag}>${c}</${tag}>`).join("") + "</tr>";
      }).join("") + "</table>";
    } else if (/^#{1,4} /.test(l)) {
      closeList(); flushPara();
      const level = l.match(/^#+/)[0].length;
      html += `<h${level}>${inline(l.replace(/^#+ /, ""))}</h${level}>`;
    } else if (/^\s*[-*] /.test(l) || /^\s*\d+\. /.test(l)) {
      flushPara();
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(l.replace(/^\s*([-*]|\d+\.) /, ""))}</li>`;
    } else if (/^> /.test(l)) {
      closeList(); flushPara();
      html += `<blockquote>${inline(l.slice(2))}</blockquote>`;
    } else if (l.trim() === "") {
      closeList(); flushPara();
    } else if (inList && /^\s+/.test(l)) {         // wrapped list-item line
      html = html.replace(/<\/li>$/, ` ${inline(l.trim())}</li>`);
    } else {
      closeList();
      para.push(l.trim());
    }
  }
  closeList(); flushPara();
  return html;
}

/* ---------- metric chart ------------------------------------------------ */
function chart(lab, color, W, H) {
  const runs = lab.runs.filter(r => typeof r.metric_value === "number");
  const m = {t: 14, r: 16, b: 30, l: 52};
  if (!runs.length) return `<svg width="${W}" height="${H}" style="max-width:100%"><text x="${W/2}" y="${H/2}" text-anchor="middle">waiting for first run…</text></svg>`;
  const ys = runs.map(r => r.metric_value);
  let lo = Math.min(...ys), hi = Math.max(...ys);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
  const x = i => m.l + (runs.length === 1 ? 0.5 : i / (runs.length - 1)) * (W - m.l - m.r);
  const y = v => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
  let s = `<svg width="${W}" height="${H}" style="max-width:100%">`;
  for (let g = 0; g < 3; g++) {
    const gy = m.t + g * (H - m.t - m.b) / 2;
    s += `<line class="grid-line" x1="${m.l}" y1="${gy}" x2="${W - m.r}" y2="${gy}"/>`;
    s += `<text x="${m.l - 6}" y="${gy + 4}" text-anchor="end">${fmt(hi - g * (hi - lo) / 2)}</text>`;
  }
  s += `<line class="axis" x1="${m.l}" y1="${H - m.b}" x2="${W - m.r}" y2="${H - m.b}"/>`;
  s += `<path d="${runs.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r.metric_value)}`).join("")}"
        fill="none" stroke="var(${color})" stroke-width="2"/>`;
  const bestId = lab.best && lab.best.run_id;
  runs.forEach((r, i) => {
    const isBest = r.run_id === bestId;
    s += `<circle cx="${x(i)}" cy="${y(r.metric_value)}" r="${isBest ? 5.5 : 4.5}"
      fill="var(${color})" stroke="var(--surface-2)" stroke-width="2"
      data-tip="${r.run_id} · ${lab.param}=${r.value} · ${lab.metric}=${fmt(r.metric_value)}"/>`;
    if (isBest) s += `<text x="${x(i)}" y="${y(r.metric_value) - 10}" text-anchor="middle"
      style="fill:var(--text-primary);font-weight:650">${fmt(r.metric_value)}</text>`;
    s += `<text x="${x(i)}" y="${H - m.b + 15}" text-anchor="middle">${fmt(r.value)}</text>`;
  });
  s += `<text x="${(m.l + W - m.r) / 2}" y="${H - 3}" text-anchor="middle">${lab.param}</text>`;
  return s + "</svg>";
}

function sparkline(lab, color) {
  const runs = lab.runs.filter(r => typeof r.metric_value === "number");
  const W = 120, H = 34;
  if (runs.length < 2) return "";
  const ys = runs.map(r => r.metric_value);
  const lo = Math.min(...ys), hi = Math.max(...ys) || 1;
  const x = i => 2 + i / (runs.length - 1) * (W - 4);
  const y = v => 3 + (1 - (v - lo) / ((hi - lo) || 1)) * (H - 6);
  return `<svg width="${W}" height="${H}"><path fill="none" stroke="var(${color})"
    stroke-width="2" d="${runs.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r.metric_value)}`).join("")}"/></svg>`;
}

/* ---------- network map ------------------------------------------------- */
function networkMap(state) {
  const W = Math.min(940, document.body.clientWidth - 80), H = 400;
  const cx = W / 2, cy = H / 2;
  const labs = state.labs;
  const labPos = {};
  labs.forEach((lab, i) => {
    const a = -Math.PI / 2 + i * 2 * Math.PI / labs.length;
    labPos[lab.name] = [cx + 130 * Math.cos(a), cy + 105 * Math.sin(a)];
  });
  const themeNames = state.themes.filter(t => labs.some(l => l.themes.includes(t)));
  const themePos = {};
  themeNames.forEach((t, i) => {
    const a = -Math.PI / 2 + (i + 0.5) * 2 * Math.PI / themeNames.length;
    themePos[t] = [cx + Math.min(cx - 80, 320) * Math.cos(a), cy + 165 * Math.sin(a)];
  });
  let s = `<svg width="${W}" height="${H}" style="max-width:100%">`;
  labs.forEach(lab => lab.themes.forEach(t => {           // theme edges (muted)
    const [x1, y1] = labPos[lab.name], [x2, y2] = themePos[t];
    s += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"
          stroke="var(--border)" stroke-width="1.5"/>`;
  }));
  state.reviews.forEach(r => {                            // review edges (directed)
    const a = labPos[r.reviewer], b = labPos[r.reviewed];
    if (!a || !b) return;
    const mx = (a[0] + b[0]) / 2 + (a[1] - b[1]) * 0.22;
    const my = (a[1] + b[1]) / 2 + (b[0] - a[0]) * 0.22;
    const color = r.adopted ? "var(--good)" : "var(--text-muted)";
    s += `<path d="M${a[0]},${a[1]} Q${mx},${my} ${b[0]},${b[1]}" fill="none"
          stroke="${color}" stroke-width="${r.adopted ? 3 : 2}"
          data-tip="${r.reviewer} reviews ${r.reviewed}${r.adopted ? " — ADOPTED" : ""}"/>`;
    const t = 0.82;                                        // arrowhead near target
    const qx = (1-t)*(1-t)*a[0] + 2*(1-t)*t*mx + t*t*b[0];
    const qy = (1-t)*(1-t)*a[1] + 2*(1-t)*t*my + t*t*b[1];
    s += `<circle cx="${qx}" cy="${qy}" r="3.5" fill="${color}"/>`;
  });
  themeNames.forEach(t => {
    const [x, y] = themePos[t];
    s += `<g><circle cx="${x}" cy="${y}" r="7" fill="var(--surface-3)"
          stroke="var(--border)" stroke-width="1.5"/>
          <text x="${x}" y="${y - 12}" text-anchor="middle">${t}</text></g>`;
  });
  labs.forEach(lab => {
    const [x, y] = labPos[lab.name];
    const short = lab.name.replace(/^lab_\d+_/, "").replace(/_/g, " ");
    s += `<g class="net-node" onclick="location.hash='#/lab/${lab.name}'">
          <circle cx="${x}" cy="${y}" r="15" fill="var(${seriesFor(lab.name)})"
            stroke="var(--surface-2)" stroke-width="3"
            data-tip="${lab.name} — click to open"/>
          <text x="${x}" y="${y + 30}" text-anchor="middle"
            style="fill:var(--text-primary);font-weight:600">${short}</text></g>`;
  });
  s += "</svg>";
  return `<div class="net-wrap">${s}</div>
    <p style="color:var(--text-muted);font-size:12px;margin:6px 0 0">
    ● labs (click to open) · ○ shared themes · gray curves = cross-lab reviews ·
    <span style="color:var(--good);font-weight:600">green curve</span> = review adopted
    into the target lab's next experiment</p>`;
}

/* ---------- views ------------------------------------------------------- */
function overview(state) {
  return `
  <header>
    <h1>Challengescape labs — live</h1>
    <span class="sub">real runs, provenance-tracked · <span id="stamp"></span> ·
      sources: <a href="${REPO_URL}" target="_blank" rel="noopener">efferents repo ↗</a> ·
      <a href="${CHALLENGESCAPE_URL}" target="_blank" rel="noopener">Challengescape ↗</a> ·
      <a href="#" onclick="showSharedIndex();return false">shared journal</a></span>
    <button class="btn" onclick="openModal()">＋ Submit a new lab</button>
  </header>
  <div class="viewer" id="viewer" style="display:none;margin-bottom:16px"></div>
  <div class="grid">
    ${state.labs.map(lab => `
    <div class="card click" onclick="location.hash='#/lab/${lab.name}'">
      <h2><span class="swatch" style="background:var(${seriesFor(lab.name)})"></span>
        ${lab.name}</h2>
      <p class="challenge"><a href="${CHALLENGESCAPE_URL}" target="_blank" rel="noopener"
        onclick="event.stopPropagation()"
        title="Verbatim from the Encode Challengescape Climate section — open the source"
        >&ldquo;${lab.challenge}&rdquo; ↗</a></p>
      <div class="tiles">
        <div class="tile"><div class="v">${lab.best ? fmt(lab.best.metric_value) : "—"}</div>
          <div class="k">best ${lab.metric}</div></div>
        <div class="tile"><div class="v">${lab.runs.length}/${lab.runs_planned}</div>
          <div class="k">runs</div></div>
        <div class="tile"><div class="v">${lab.pipeline.length}</div>
          <div class="k">agent artifacts</div></div>
        <div class="tile"><div class="status ${lab.status}"><span class="dot"></span>
          ${lab.status}</div><div class="k">status</div></div>
      </div>
      ${sparkline(lab, seriesFor(lab.name))}
      <div class="themes">${lab.themes.map(t => `<span class="chip">${t}</span>`).join("")}</div>
      <div class="verdict">Open the lab → agents, journal, full chart</div>
    </div>`).join("")}
  </div>
  <div class="section card">
    <h2>Network map — how the labs connect</h2>
    ${networkMap(state)}
  </div>`;
}

function labDetail(state, name) {
  const lab = state.labs.find(l => l.name === name);
  if (!lab) return `<p>Unknown lab. <a href="#/">Back</a></p>`;
  const color = seriesFor(lab.name);
  const related = state.reviews.filter(r => r.reviewer === name || r.reviewed === name);
  return `
  <header>
    <span class="back"><a href="#/">← All labs</a></span>
    <h1><span class="swatch" style="background:var(${color});display:inline-block"></span>
      ${lab.name}</h1>
    <span class="sub"><span id="stamp"></span></span>
  </header>
  <p class="challenge" style="font-size:14px">
    <a href="${CHALLENGESCAPE_URL}" target="_blank" rel="noopener"
      title="Verbatim from the Encode Challengescape Climate section — open the source"
      >&ldquo;${lab.challenge}&rdquo; ↗</a>
    · <a href="#" onclick="showArtifact('${lab.name}','challenge.md');return false">challenge card</a></p>
  <p style="color:var(--text-secondary);max-width:900px">${lab.goal}</p>
  <p style="color:var(--text-muted);font-size:12px">source of truth:
    <code>${lab.path}/</code> ·
    <a href="${REPO_URL}" target="_blank" rel="noopener">repo ↗</a></p>
  <div class="tiles">
    <div class="tile"><div class="v">${lab.best ? fmt(lab.best.metric_value) : "—"}</div>
      <div class="k">best ${lab.metric}</div></div>
    <div class="tile"><div class="v">${lab.best ? lab.param + "=" + fmt(lab.best.value) : "—"}</div>
      <div class="k">best setting</div></div>
    <div class="tile"><div class="v">${lab.runs.length}/${lab.runs_planned}</div>
      <div class="k">runs</div></div>
    <div class="tile"><div class="status ${lab.status}"><span class="dot"></span>${lab.status}</div>
      <div class="k">status</div></div>
  </div>
  <div class="grid" style="grid-template-columns: minmax(340px, 1.1fr) minmax(360px, 1.6fr)">
    <div>
      <div class="card">${chart(lab, color, 430, 210)}
        <table><tr><th>run</th><th>${lab.param}</th><th>${lab.metric}</th></tr>
        ${lab.runs.map(r => `<tr class="${lab.best && r.run_id === lab.best.run_id ? "best" : ""}">
          <td>${r.run_id}</td><td>${fmt(r.value)}</td><td>${fmt(r.metric_value)}</td></tr>`).join("")}
        </table>
        <div class="verdict"><strong>Review verdict:</strong> ${lab.verdict}</div>
      </div>
      <div class="card" style="margin-top:16px">
        <h2>Cross-lab reviews involving this lab</h2>
        <ul class="pipeline">${related.map(r => `
          <li><span class="role">${r.reviewer === name ? "outgoing" : "incoming"}</span>
            <a onclick="showArtifact('shared','${r.file}');return false" href="#">
              ${r.reviewer} → ${r.reviewed}</a>
            ${r.adopted ? `<span class="chip" style="color:var(--good)">adopted</span>` : ""}
          </li>`).join("") || "<li>none yet</li>"}
        </ul>
      </div>
    </div>
    <div class="card">
      <h2>Agent pipeline</h2>
      <p style="color:var(--text-muted);font-size:12px">Supervisor–student roles
        derived from the recorded journal artifacts; a live lab
        (<code>efferents start</code>) runs these as real agents. Click to read.</p>
      <ul class="pipeline">
        ${lab.pipeline.map(p => `
        <li><span class="role">${p.role}</span>
          <a href="#" onclick="showArtifact('${lab.name}','${p.file}');return false">${p.title}</a>
          <span class="t">${p.mtime}</span></li>`).join("")}
      </ul>
      <div class="viewer" id="viewer" style="display:none"></div>
    </div>
  </div>`;
}

/* ---------- artifact viewer / modal / plumbing -------------------------- */
async function showArtifact(lab, file) {
  openArtifact = {lab, file};
  const viewer = document.getElementById("viewer");
  if (!viewer) return;
  viewer.style.display = "block";
  const path = lab === "shared"
    ? (file === "index.md" ? "examples/challengescape/shared_journal/index.md"
                           : `examples/challengescape/shared_journal/reviews/${file}`)
    : `examples/challengescape/labs/${lab}/${file}`;
  const res = await fetch(`/api/artifact?lab=${encodeURIComponent(lab)}&file=${encodeURIComponent(file)}`);
  viewer.innerHTML =
    `<p style="color:var(--text-muted);font-size:11.5px;margin:0 0 8px">
       source: <code>${path}</code></p>`
    + (res.ok ? renderMd(await res.text()) : "<p>artifact unavailable</p>");
}
function showSharedIndex() { showArtifact("shared", "index.md"); }
function openModal() { document.getElementById("modal").style.display = "flex"; }
function closeModal() { document.getElementById("modal").style.display = "none"; }
async function copyEntry(btn) {
  await navigator.clipboard.writeText(document.getElementById("entrypoint").textContent);
  btn.textContent = "Copied ✓";
  setTimeout(() => btn.textContent = "Copy to clipboard", 1500);
}
document.getElementById("modal").addEventListener("click", e => {
  if (e.target.id === "modal") closeModal();
});

function bindTooltips() {
  document.querySelectorAll("[data-tip]").forEach(el => {
    el.addEventListener("mousemove", e => {
      tooltip.style.display = "block";
      tooltip.textContent = el.dataset.tip;
      tooltip.style.left = (e.clientX + 12) + "px";
      tooltip.style.top = (e.clientY - 10) + "px";
    });
    el.addEventListener("mouseleave", () => tooltip.style.display = "none");
  });
}

function currentView() {
  const m = location.hash.match(/^#\/lab\/([\w\-]+)/);
  return m ? {view: "lab", name: m[1]} : {view: "overview"};
}

function setStamp(text) {
  const stamp = document.getElementById("stamp");
  if (stamp) stamp.textContent = text;
}

function render() {
  if (!STATE) return;
  const v = currentView();
  const app = document.getElementById("app");
  const y = window.scrollY;                      // don't yank the reader around
  app.innerHTML = v.view === "lab" ? labDetail(STATE, v.name) : overview(STATE);
  window.scrollTo(0, y);
  setStamp("live · updated " + new Date().toLocaleTimeString());
  bindTooltips();
  if (openArtifact && openArtifact.lab !== "shared"
      && (v.view !== "lab" || openArtifact.lab !== v.name)) openArtifact = null;
  if (openArtifact) showArtifact(openArtifact.lab, openArtifact.file);
}

window.addEventListener("hashchange", () => {
  openArtifact = null;
  render();
  window.scrollTo(0, 0);                         // a navigation SHOULD go to top
});

async function tick() {
  try {
    const res = await fetch("/api/state");
    const payload = await res.text();
    if (payload === lastPayload) {               // idle: touch nothing, keep scroll
      setStamp("live · no changes since " + new Date().toLocaleTimeString());
      return;
    }
    lastPayload = payload;
    STATE = JSON.parse(payload);
    render();
  } catch (e) {
    setStamp("reconnecting…");
  }
}
tick();
setInterval(tick, 3000);
</script>
</body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (stdlib API)
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            body, ctype = json.dumps(build_state()).encode(), "application/json"
        elif parsed.path == "/api/artifact":
            q = parse_qs(parsed.query)
            text = read_artifact(q.get("lab", [""])[0], q.get("file", [""])[0])
            if text is None:
                self.send_error(404)
                return
            body, ctype = text.encode(), "text/plain; charset=utf-8"
        elif parsed.path in ("/", "/index.html"):
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
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
    print(f"live workspace: http://127.0.0.1:{args.port}/  (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
