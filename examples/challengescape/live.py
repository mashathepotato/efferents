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

from efferents.dashboard.theme import embed_research_theme

ROOT = Path(__file__).resolve().parent
LABS = ROOT / "labs"
REVIEWS = ROOT / "shared_journal" / "reviews"
VENUE_DIR = ROOT / "venue"

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
    ("out/journal/006_next_experiment.md", "Student", "Next-experiment proposal"),
    ("out/journal/007_hypothesis_jump.md", "Supervisor · Student", "Hypothesis jump (autonomous)"),
    ("context/popper.md", "Charter", "Lab charter (design decisions)"),
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

    # Build-phase activity (authorship, recorded verdict passes, …) lives in
    # artifacts/, not in the sweep output — a lab writing artifacts is
    # "running" even when no sweep is executing.
    activity, phase = [], None
    art = lab_dir / "artifacts"
    if art.is_dir():
        sentinel = art / "BUILD_ACTIVE"
        if sentinel.is_file():
            status = "running"
            phase = sentinel.read_text().strip()
        now = time.time()
        for f in sorted(art.glob("*.jsonl")):
            lines = sum(1 for line in f.read_text().splitlines() if line.strip())
            recent = (now - f.stat().st_mtime) < 60
            activity.append({"name": f.name, "lines": lines, "live": recent})
            if recent:
                status = "running"
                phase = f"building: {f.name} ({lines} records)"

    best = None
    scored = [r for r in runs if isinstance(r["metric_value"], (int, float))]
    if scored:
        best = (max if maximize else min)(scored, key=lambda r: r["metric_value"])

    hypotheses = []
    for hyp in sorted((lab_dir / "popper-corpus").glob("*/hypothesis.md")):
        text = hyp.read_text()
        fm = {k: v for k, v in re.findall(r"^([\w_]+): (.+)$",
                                          text.split("---")[1], re.M)} \
            if text.startswith("---") else {}
        hypotheses.append({
            "slug": fm.get("slug", hyp.parent.name),
            "status": fm.get("status", "?"),
            "gate": fm.get("falsifiability_gate", "?"),
            "supersedes": fm.get("supersedes"),
            "supersedes_hash": fm.get("supersedes_hash"),
            "falsified": fm.get("falsified"),
            "file": f"popper-corpus/{hyp.parent.name}/hypothesis.md",
        })
    # Lineage order: follow supersedes links, roots first.
    hypotheses.sort(key=lambda h: (h["supersedes"] is not None, h["slug"]))

    return {
        "name": lab_dir.name,
        "path": f"examples/challengescape/labs/{lab_dir.name}",
        "hypotheses": hypotheses,
        "activity": activity,
        "phase": phase,
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
        "venue": _venue_state(),
    }


def _venue_state() -> dict | None:
    if not (VENUE_DIR / "venue.yaml").is_file():
        return None
    cfg = yaml.safe_load((VENUE_DIR / "venue.yaml").read_text())
    subs = []
    for status_file in sorted(VENUE_DIR.glob("submissions/sub-*/status.json")):
        s = json.loads(status_file.read_text())
        sub_dir = status_file.parent
        rel = f"submissions/{s['submission_id']}"
        s["files"] = {
            "manuscripts": [f"{rel}/{p.name}" for p in sorted(sub_dir.glob("manuscript_v*.md"))],
            "reviews": [f"{rel}/reviews/{p.name}" for p in sorted((sub_dir / "reviews").glob("r*_*.md"))],
            "decisions": [f"{rel}/{p.name}" for p in sorted(sub_dir.glob("decision_r*.md"))],
            "camera_ready": (f"proceedings/{s['submission_id']}.md"
                             if (VENUE_DIR / "proceedings" / f"{s['submission_id']}.md").is_file()
                             else None),
            "reproductions": [f"reproductions/{r['report']}"
                              for r in s["post_publication"]["reproductions"]],
        }
        subs.append(s)
    return {"name": cfg["name"], "board": cfg["board"], "submissions": subs}


def read_artifact(lab: str, rel: str) -> str | None:
    """Whitelisted artifact reader — only files this app itself lists."""
    if lab == "shared":
        if rel == "index.md" and (ROOT / "shared_journal" / "index.md").is_file():
            return (ROOT / "shared_journal" / "index.md").read_text()
        if re.fullmatch(r"[\w.\-]+\.md", rel) and (REVIEWS / rel).is_file():
            return (REVIEWS / rel).read_text()
        return None
    if lab == "venue":
        path = (VENUE_DIR / rel).resolve()
        if (path.is_file() and path.suffix in (".md", ".yaml", ".jsonl")
                and path.is_relative_to(VENUE_DIR)):
            return path.read_text()
        return None
    lab_dir = LABS / lab
    if not lab_dir.is_dir() or lab_dir.parent != LABS:
        return None
    allowed = rel in {entry[0] for entry in ARTIFACT_ROLES} or \
        re.fullmatch(r"popper-corpus/[\w\-]+/hypothesis\.md", rel)
    if not allowed:
        return None
    path = lab_dir / rel
    return path.read_text() if path.is_file() else None


PAGE = embed_research_theme(r"""<!doctype html>
<html lang="en" data-efferents-theme="__EFFERENTS_RESEARCH_THEME_ID__"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Challengescape labs — live</title>
<style>
  /*__EFFERENTS_RESEARCH_THEME_CSS__*/
  :root {
    --surface-1: var(--bg);
    --surface-2: var(--panel);
    --surface-3: var(--panel-raised);
    --border: var(--line);
    --text-primary: var(--fg);
    --text-secondary: var(--muted);
    --text-muted: var(--dim);
    --series-1: var(--signal);
    --series-2: var(--warning);
    --series-3: var(--cyan);
    --good: var(--signal);
    --accent: var(--signal);
  }
  html, body { min-height: 100vh; }
  #app {
    width: min(1500px, 100%);
    margin: 0 auto;
    padding: 20px clamp(14px, 2.6vw, 38px) 52px;
  }
  header {
    display: grid;
    grid-template-columns: auto auto minmax(180px, 1fr) auto auto;
    align-items: center;
    gap: 14px;
    min-height: 54px;
    margin-bottom: 14px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--line);
  }
  header::before {
    display: grid;
    width: 36px;
    height: 36px;
    place-items: center;
    color: var(--signal);
    content: "ℯ";
    font: 500 29px/1 var(--display);
    font-style: italic;
    letter-spacing: 0;
  }
  h1 {
    margin: 0;
    font: 500 16px/1.25 var(--display);
    letter-spacing: -.02em;
  }
  .sub {
    min-width: 0;
    overflow: hidden;
    color: var(--muted);
    font: 9px/1.5 var(--mono);
    letter-spacing: .025em;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .btn {
    min-height: 32px;
    padding: 8px 12px;
    border: 1px solid var(--signal);
    border-radius: 0;
    background: var(--signal);
    color: #fff;
    cursor: pointer;
    font: 650 9px/1 var(--mono);
    letter-spacing: .07em;
    text-transform: uppercase;
  }
  :root[data-theme="dark"] .btn { color: var(--bg); }
  .btn:hover { background: var(--signal-strong); }
  .btn.ghost {
    border-color: var(--line);
    background: transparent;
    color: var(--muted);
  }
  .btn.ghost:hover { border-color: var(--signal); color: var(--signal); }
  a { color: var(--cyan); text-decoration: none; }
  a:hover { color: var(--signal); }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 1px;
    padding: 1px;
    background: var(--line);
  }
  .card {
    min-width: 0;
    padding: 18px;
    border: 1px solid var(--line);
    border-radius: 0;
    background: var(--panel);
    box-shadow: none;
  }
  .grid > .card { border: 0; }
  .card.click { cursor: pointer; transition: background-color .14s, box-shadow .14s; }
  .card.click:hover {
    background: var(--panel-raised);
    box-shadow: inset 2px 0 0 var(--signal);
  }
  .card h2 {
    display: flex;
    align-items: center;
    gap: 9px;
    margin: 0;
    font: 650 10px/1.35 var(--mono);
    letter-spacing: .065em;
    text-transform: uppercase;
  }
  .swatch { width: 7px; height: 7px; flex: none; }
  .challenge {
    max-width: 1050px;
    margin: 13px 0 16px;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.55;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    margin: 14px 0;
    border: solid var(--line);
    border-width: 1px 0;
  }
  .tile { min-width: 0; padding: 12px; border-left: 1px solid var(--line-soft); }
  .tile:first-child { border-left: 0; }
  .tile .v {
    overflow: hidden;
    color: var(--fg);
    font: 520 clamp(20px, 2.4vw, 32px)/1 var(--mono);
    letter-spacing: -.045em;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tile .k {
    margin-top: 7px;
    color: var(--dim);
    font: 8px/1.25 var(--mono);
    letter-spacing: .08em;
    text-transform: uppercase;
  }
  .status {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: var(--muted);
    font: 9px/1 var(--mono);
    text-transform: uppercase;
  }
  .dot { width: 6px; height: 6px; border: 1px solid currentColor; border-radius: 50%; }
  .running .dot { background: var(--warning); animation: pulse 1.2s infinite; }
  .complete .dot { background: var(--good); }
  @keyframes pulse { 50% { opacity: .3; } }
  svg text { fill: var(--muted); font: 9px/1 var(--mono); }
  svg .grid-line, svg .axis { stroke: var(--line); }
  table {
    width: 100%;
    margin-top: 10px;
    border-collapse: collapse;
    font: 10px/1.45 var(--mono);
    font-variant-numeric: tabular-nums;
  }
  th, td {
    padding: 9px 10px;
    border-bottom: 1px solid var(--line-soft);
    text-align: left;
  }
  th {
    background: var(--panel-raised);
    color: var(--dim);
    font-size: 8px;
    font-weight: 500;
    letter-spacing: .075em;
    text-transform: uppercase;
  }
  td { color: var(--muted); vertical-align: top; }
  tr.best td { font-weight: 650; }
  tr.best { background: var(--signal-soft); box-shadow: inset 2px 0 0 var(--signal); }
  .verdict { margin-top: 12px; color: var(--muted); font: 9px/1.5 var(--mono); }
  .themes { margin-top: 10px; }
  .chip {
    display: inline-block;
    margin: 2px 3px 0 0;
    padding: 3px 7px;
    border: 1px solid var(--line);
    border-radius: 0;
    background: transparent;
    color: var(--muted);
    font: 8px/1.25 var(--mono);
    letter-spacing: .035em;
    text-transform: uppercase;
  }
  .section { margin-top: 12px; }
  .section > h2 { margin: 0 0 12px; }
  .pipeline { list-style: none; margin: 0; padding: 0; }
  .pipeline li {
    display: grid;
    grid-template-columns: 160px minmax(0, 1fr) auto;
    align-items: baseline;
    gap: 10px;
    padding: 9px 0;
    border-bottom: 1px solid var(--line-soft);
    font-size: 12px;
  }
  .role {
    color: var(--dim);
    font: 8px/1.4 var(--mono);
    letter-spacing: .065em;
    text-transform: uppercase;
  }
  .pipeline .t { margin-left: auto; color: var(--dim); font: 8px/1.5 var(--mono); }
  .viewer {
    max-height: 60vh;
    margin-top: 12px;
    overflow: auto;
    padding: 20px;
    border: 1px solid var(--line);
    border-radius: 0;
    background: var(--bg);
    font-size: 13px;
  }
  .viewer h1 { font-size: 18px; text-transform: none; }
  .viewer h2 { margin-top: 24px; font-size: 14px; }
  .viewer table { font-size: 10px; }
  .viewer code { padding: 1px 4px; border-radius: 0; background: var(--panel-raised); }
  .viewer blockquote {
    margin: 12px 0;
    padding: 6px 12px;
    border-left: 2px solid var(--signal);
    color: var(--muted);
  }
  .back { font: 9px/1 var(--mono); text-transform: uppercase; }
  .net-wrap { overflow-x: auto; text-align: center; }
  .net-node { cursor: pointer; }
  #modal {
    position: fixed;
    inset: 0;
    z-index: 30;
    display: none;
    align-items: center;
    justify-content: center;
    background: rgba(9, 34, 50, .48);
    backdrop-filter: blur(3px);
  }
  #modal .box {
    width: min(760px, calc(100% - 28px));
    padding: 26px;
    border: 1px solid var(--line);
    border-radius: 0;
    background: var(--panel);
    box-shadow: var(--shadow);
  }
  #modal h2 { margin: 0 0 10px; font: 650 13px/1.3 var(--mono); text-transform: uppercase; }
  #modal p { color: var(--muted); font-size: 13px; }
  #modal pre {
    max-height: 44vh;
    overflow: auto;
    padding: 15px;
    border: 1px solid var(--line);
    border-radius: 0;
    background: var(--bg);
    color: var(--muted);
    font: 10px/1.55 var(--mono);
    white-space: pre-wrap;
  }
  .modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
  #tooltip {
    position: fixed;
    z-index: 40;
    display: none;
    padding: 6px 9px;
    border: 1px solid var(--line);
    border-radius: 0;
    background: var(--panel);
    color: var(--muted);
    box-shadow: var(--shadow);
    font: 9px/1.4 var(--mono);
    pointer-events: none;
  }
  @media (max-width: 760px) {
    #app { padding-inline: 10px; }
    header { grid-template-columns: auto minmax(0, 1fr) auto; }
    header .sub { grid-column: 1 / -1; grid-row: 2; }
    .grid { grid-template-columns: 1fr; }
    .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .tile:nth-child(odd) { border-left: 0; }
    .pipeline li { grid-template-columns: 112px minmax(0, 1fr); }
    .pipeline .t { display: none; }
    table { min-width: 620px; }
    .card { overflow-x: auto; }
  }
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

FIRST run the popper-probe intake dialogue WITH ME on this challenge — do not
skip it or self-play it: I choose the framing, you probe it until the gate
passes. Save the gated hypothesis, and record the dialogue's design decisions
plus my initial direction verbatim in the lab's context/popper.md charter
(template: templates/popper.md; guidance, not rules).

Then follow the repo-adapter contract (train prints {"checkpoint": ...}, eval
prints {"metrics": {...}}), keep the data synthetic or public so it runs
offline, add a challenge.md and questions_for_poc.md from the templates, and
run:

  .venv/bin/efferents run examples/challengescape/labs/&lt;new lab&gt; --approve \
      --out examples/challengescape/labs/&lt;new lab&gt;/out
  .venv/bin/python examples/challengescape/crosslab.py

Finally write an intra-lab review (005_review.md) and one cross-lab review,
following examples/challengescape/prompts/.

Do not create a bespoke dashboard for this lab. It appears in the existing
Challengescape live workspace. Any extension to an example HTML app must use
efferents.dashboard.theme.embed_research_theme so it inherits the canonical
research-lab UI.</pre>
  <div class="modal-actions">
    <button class="btn ghost" onclick="closeModal()">Close</button>
    <button class="btn" onclick="copyEntry(this)">Copy to clipboard</button>
  </div>
</div></div>
<script>
const SERIES = ["--series-1", "--series-2", "--series-3", "--series-1", "--series-2"];
const REPO_URL = "https://github.com/mashathepotato/efferents";
const CHALLENGESCAPE_URL = "https://encode-challengescape.pillar.vc/";
const THEME_KEY = "efferents-theme";
const tooltip = document.getElementById("tooltip");
let STATE = null;
let lastPayload = "";      // re-render only when the state bytes change
let openArtifact = null;   // {lab, file} persisted across refreshes

const fmt = v => v == null ? "—" : (typeof v === "number" ? +v.toPrecision(4) : v);
const seriesFor = name =>
  SERIES[(STATE ? STATE.labs.findIndex(l => l.name === name) : 0) % SERIES.length];

function setTheme(theme) {
  document.documentElement.dataset.theme = theme === "dark" ? "dark" : "light";
  try { localStorage.setItem(THEME_KEY, document.documentElement.dataset.theme); } catch (_) {}
  syncThemeButton();
}
function initTheme() {
  let stored = "light";
  try { stored = localStorage.getItem(THEME_KEY) || "light"; } catch (_) {}
  document.documentElement.dataset.theme = stored === "dark" ? "dark" : "light";
}
function toggleTheme() {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}
function syncThemeButton() {
  const button = document.getElementById("theme-button");
  if (!button) return;
  const dark = document.documentElement.dataset.theme === "dark";
  button.textContent = dark ? "Light" : "Dark";
  button.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
}
initTheme();

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
    <button id="theme-button" class="btn ghost" onclick="toggleTheme()"
      aria-label="Switch to dark theme">Dark</button>
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
      ${lab.phase ? `<div style="font-size:12px;color:var(--warning);margin-bottom:6px">⚙ ${lab.phase}</div>` : ""}
      ${sparkline(lab, seriesFor(lab.name))}
      ${hypLine(lab)}
      <div class="themes">${lab.themes.map(t => `<span class="chip">${t}</span>`).join("")}</div>
      <div class="verdict">Open the lab → agents, journal, full chart</div>
    </div>`).join("")}
  </div>
  ${venueSection(state)}
  <div class="section card">
    <h2>Network map — how the labs connect</h2>
    ${networkMap(state)}
  </div>`;
}

/* ---------- hypothesis lineage ------------------------------------------ */
function hypLine(lab) {
  const hs = lab.hypotheses || [];
  if (!hs.length) return "";
  const retired = hs.filter(h => h.status === "retired").length;
  const active = hs.find(h => h.status === "active");
  return `<div style="font-size:12px;color:var(--text-secondary);margin-top:8px">
    hypothesis: ${active ? `<strong>${active.slug}</strong>` : "none active"}
    ${retired ? `<span class="chip" style="color:var(--series-2)">${retired} falsified → jumped</span>` : ""}
  </div>`;
}

function lineageSection(lab) {
  const hs = lab.hypotheses || [];
  if (!hs.length) return "";
  const chips = hs.map(h => {
    const color = h.status === "active" ? "var(--good)"
                : h.status === "retired" ? "var(--series-2)" : "var(--warning)";
    const label = h.status === "retired" ? "✗ falsified" : h.status;
    return `<a href="#" onclick="showArtifact('${lab.name}','${h.file}');return false"
      class="chip" style="border:1px solid ${color};color:var(--text-primary)">
      ${h.slug} <span style="color:${color};font-weight:600">${label}</span></a>`;
  }).join(` <span style="color:var(--text-muted)">→</span> `);
  const jump = hs.find(h => h.supersedes);
  return `<div class="card" style="margin-bottom:16px">
    <h2>Hypothesis lineage</h2>
    <p style="margin:8px 0 4px">${chips}</p>
    ${jump ? `<p style="color:var(--text-muted);font-size:11.5px;margin:6px 0 0">
      autonomous jump after kill-condition fired — successor cites its
      predecessor by content hash
      <code>${(jump.supersedes_hash || "").slice(0, 26)}…</code> ·
      <a href="#" onclick="showArtifact('${lab.name}','out/journal/007_hypothesis_jump.md');return false">jump record</a></p>` : ""}
  </div>`;
}

/* ---------- venue ------------------------------------------------------- */
function stateChip(s) {
  const color = s === "accepted" ? "var(--good)"
              : s === "reject" ? "var(--series-2)"
              : "var(--warning)";
  return `<span class="chip" style="color:${color};font-weight:600">${s.replace("_", " ")}</span>`;
}

function venueSection(state) {
  const v = state.venue;
  if (!v) return "";
  const rows = v.submissions.map(s => {
    const f = s.files;
    const paper = f.camera_ready
      ? `<a href="#" onclick="showArtifact('venue','${f.camera_ready}');return false"><strong>${s.title}</strong></a>`
      : `<a href="#" onclick="showArtifact('venue','${f.manuscripts[f.manuscripts.length-1]}');return false">${s.title}</a>`;
    const reviews = f.reviews.map(p => {
      const m = p.match(/r(\d+)_(\w+)\.md$/);
      return `<a href="#" onclick="showArtifact('venue','${p}');return false">r${m[1]} ${m[2]}</a>`;
    }).join(" · ");
    const decisions = f.decisions.map((p, i) =>
      `<a href="#" onclick="showArtifact('venue','${p}');return false">decision r${i+1}</a>`).join(" · ");
    const pp = s.post_publication;
    const ppText = pp.reproductions.length
      ? pp.reproductions.map((r, i) =>
          `<a href="#" onclick="showArtifact('venue','${f.reproductions[i]}');return false">
             ${r.verdict} by ${r.by}</a>`).join("; ")
      : (s.state === "accepted" ? "no reproductions yet" : "—");
    return `<tr>
      <td>${paper}<br><span style="color:var(--text-muted);font-size:11.5px">${s.submission_id}
        · ${s.lab_id}${s.below_gain_gate ? " · flagged: below gain gate" : ""}</span></td>
      <td>${stateChip(s.state)}<br><span style="color:var(--text-muted);font-size:11.5px">
        round ${s.round}</span></td>
      <td style="font-size:12px">${reviews}<br>${decisions}</td>
      <td style="font-size:12px">${ppText}</td></tr>`;
  }).join("");
  return `
  <div class="section card">
    <h2>${v.name}</h2>
    <p style="color:var(--text-muted);font-size:12.5px;margin:6px 0 10px">
      Real journal lifecycle: submit (methodology + machine-executable
      reproduction recipe) → board review (${v.board.join(" / ")}) → revision
      rounds → deterministic accept/reject → proceedings. Labs that build on a
      paper reproduce it first — <code>venue.py reproduce</code> re-executes
      the paper's recipe and compares every metric.
      <a href="#" onclick="showArtifact('venue','proceedings/index.md');return false">proceedings index</a> ·
      <a href="#" onclick="showArtifact('venue','venue.yaml');return false">venue policy</a> ·
      <a href="#" onclick="showArtifact('venue','ledger.jsonl');return false">event ledger</a></p>
    <table>
      <tr><th>paper</th><th>state</th><th>reviews & decisions</th><th>post-publication</th></tr>
      ${rows}
    </table>
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
    <button id="theme-button" class="btn ghost" onclick="toggleTheme()"
      aria-label="Switch to dark theme">Dark</button>
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
  ${lineageSection(lab)}
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
  ${lab.phase ? `<div style="font-size:13px;color:var(--warning);margin-bottom:8px">⚙ ${lab.phase}</div>` : ""}
  ${(lab.activity || []).length ? `<p style="color:var(--text-muted);font-size:12px">
    artifacts: ${lab.activity.map(a => `${a.name} <strong>${a.lines}</strong>${a.live ? " ●" : ""}`).join(" · ")}</p>` : ""}
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
    : lab === "venue" ? `examples/challengescape/venue/${file}`
    : `examples/challengescape/labs/${lab}/${file}`;
  const res = await fetch(`/api/artifact?lab=${encodeURIComponent(lab)}&file=${encodeURIComponent(file)}`);
  const body = res.ok
    ? (file.endsWith(".md") ? renderMd(await res.text())
       : `<pre style="font-size:12px;overflow-x:auto">${esc(await res.text())}</pre>`)
    : "<p>artifact unavailable</p>";
  viewer.innerHTML =
    `<p style="color:var(--text-muted);font-size:11.5px;margin:0 0 8px">
       source: <code>${path}</code></p>` + body;
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
  syncThemeButton();
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
""")


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
