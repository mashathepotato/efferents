# efferents Web Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three read-only visual surfaces to efferents — a static landing page, a local lab dashboard (`efferents serve`), and a reusable journal feed renderer — without changing the model-A terminal/agent flow or the daemon.

**Architecture:** A pure feed renderer (`efferents/journal/feed.py`) turns paper markdown into feed-card data. A file reader (`efferents/dashboard/reader.py`) reads an existing lab dir into plain dicts. A stdlib `http.server` (`efferents/dashboard/server.py`) serves a vanilla-JS dashboard plus `/api/*` JSON endpoints that poll those readers. A new `efferents serve` CLI subcommand starts it. The landing page is a standalone static site under `web/landing/`. Everything is read-only; popper-probe and launching stay in the terminal.

**Tech Stack:** Python ≥3.10, stdlib `http.server` (zero new deps), pydantic 2 (already a dep), vanilla HTML/CSS/JS (no build step), pytest.

**Reference spec:** `docs/superpowers/specs/2026-06-11-efferents-web-surfaces-design.md`

**Branch:** `feat/web-surfaces` (already created).

---

## File Structure

| File | Responsibility |
|------|----------------|
| `efferents/journal/__init__.py` | package marker |
| `efferents/journal/feed.py` | `FeedCard` model + `render_feed(paths)` — pure, the local→git seam |
| `efferents/dashboard/__init__.py` | package marker |
| `efferents/dashboard/reader.py` | read a lab dir → dicts for each endpoint (no HTTP) |
| `efferents/dashboard/server.py` | stdlib http.server: static page + `/api/*` JSON |
| `efferents/dashboard/static/dashboard.html` | dashboard page shell |
| `efferents/dashboard/static/dashboard.css` | dashboard styles |
| `efferents/dashboard/static/dashboard.js` | polling + render |
| `efferents/cli.py` (modify) | add `serve` subcommand |
| `web/landing/index.html` | static landing page |
| `web/landing/style.css` | landing styles |
| `tests/test_feed.py` | feed renderer unit tests |
| `tests/test_dashboard_reader.py` | reader unit tests |
| `tests/test_dashboard_server.py` | server endpoint smoke tests |
| `tests/test_cli_serve.py` | CLI `serve` wiring test |
| `tests/test_landing.py` | landing guard test |

### Data contracts (used across tasks — keep names exact)

`FeedCard` (pydantic `BaseModel`): `lab_id: str`, `campaign_id: str`, `title: str`, `summary: str`, `novelty_claim: str`, `status: str`, `published_at: str`.

`reader.read_state(lab_root) ->` `{"lab_id", "domain", "status", "budget": {"spent", "cap"}, "hypothesis": {"question", "claim", "falsifier", "student"}}`

`reader.read_runs(lab_root, n=30) ->` `{"headline": {"column", "direction"}, "runs": [{"run_id", "started_at", "value"}], "series": [{"started_at", "value"}]}`

`reader.read_papers(lab_root) ->` `list[dict]` (FeedCard dicts, newest first)

`reader.read_activity(lab_root, n=20) ->` `list[{"timestamp", "title", "body"}]` (newest first)

Endpoints: `GET /` (dashboard.html), `GET /api/state`, `GET /api/runs`, `GET /api/papers`, `GET /api/activity`, `GET /static/<file>`.

---

## Task 1: Feed renderer (`efferents/journal/feed.py`)

**Files:**
- Create: `efferents/journal/__init__.py`
- Create: `efferents/journal/feed.py`
- Test: `tests/test_feed.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_feed.py`:

```python
from pathlib import Path

from efferents.journal.feed import FeedCard, render_feed

VALID_PAPER = """---
lab_id: smoke-coefficient
domain: synthetic
campaign_id: camp-1
hypothesis_hash: "sha256:{h}"
hypothesis_path: popper-corpus/x/hypothesis.md
metric_provenance:
  - name: synthetic_loss
    value: 0.031
    runs: ["a3f1"]
    seeds: [0]
novelty_claim: Coefficient near 0.79 minimizes synthetic loss.
published_at: 2026-06-09
status: preprint
---

# Optimal coefficient for synthetic loss

## Motivation
Body text.
""".format(h="0" * 64)


def _write(p: Path, text: str) -> Path:
    p.write_text(text)
    return p


def test_render_feed_parses_valid_paper(tmp_path):
    paper = _write(tmp_path / "camp-1.md", VALID_PAPER)
    cards = render_feed([paper])
    assert len(cards) == 1
    card = cards[0]
    assert isinstance(card, FeedCard)
    assert card.lab_id == "smoke-coefficient"
    assert card.campaign_id == "camp-1"
    assert card.title == "Optimal coefficient for synthetic loss"
    assert card.summary == "Coefficient near 0.79 minimizes synthetic loss."
    assert card.status == "preprint"
    assert card.published_at == "2026-06-09"


def test_render_feed_sorts_newest_first(tmp_path):
    older = VALID_PAPER.replace("2026-06-09", "2026-06-01").replace("camp-1", "camp-old")
    newer = VALID_PAPER.replace("2026-06-09", "2026-06-10").replace("camp-1", "camp-new")
    p_old = _write(tmp_path / "camp-old.md", older)
    p_new = _write(tmp_path / "camp-new.md", newer)
    cards = render_feed([p_old, p_new])
    assert [c.campaign_id for c in cards] == ["camp-new", "camp-old"]


def test_render_feed_skips_malformed(tmp_path):
    bad = _write(tmp_path / "bad.md", "no frontmatter here")
    missing = _write(tmp_path / "missing.md", "---\nlab_id: x\n---\n\nbody")
    good = _write(tmp_path / "camp-1.md", VALID_PAPER)
    cards = render_feed([bad, missing, good])
    assert [c.campaign_id for c in cards] == ["camp-1"]


def test_render_feed_title_falls_back_to_novelty_claim(tmp_path):
    no_heading = VALID_PAPER.replace("# Optimal coefficient for synthetic loss\n\n", "")
    paper = _write(tmp_path / "camp-1.md", no_heading)
    cards = render_feed([paper])
    assert cards[0].title == "Coefficient near 0.79 minimizes synthetic loss."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_feed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'efferents.journal'`

- [ ] **Step 3: Write the implementation**

Create `efferents/journal/__init__.py` (empty file).

Create `efferents/journal/feed.py`:

```python
"""Journal feed renderer: paper markdown files -> feed-card data.

Pure and side-effect-free. It is handed a list of paper file paths and knows
nothing about where they come from (a local lab/paper/ dir now, a cloned
efferents-journal git repo later). That ignorance is the seam between the
local-first build and the git-backed shared journal.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

_REQUIRED = ("lab_id", "campaign_id", "novelty_claim", "published_at", "status")


class FeedCard(BaseModel):
    lab_id: str
    campaign_id: str
    title: str
    summary: str
    novelty_claim: str
    status: str
    published_at: str


def render_feed(paper_paths: list[Path]) -> list[FeedCard]:
    """Parse paper markdown files into feed cards, newest-first.

    Malformed papers (no frontmatter, missing required fields, bad YAML) are
    skipped, never raised.
    """
    cards: list[FeedCard] = []
    for path in paper_paths:
        card = _card_from_path(Path(path))
        if card is not None:
            cards.append(card)
    cards.sort(key=lambda c: c.published_at, reverse=True)
    return cards


def _card_from_path(path: Path) -> FeedCard | None:
    try:
        text = path.read_text()
    except OSError:
        return None
    front, body = _split_frontmatter(text)
    if front is None:
        return None
    try:
        meta = yaml.safe_load(front) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict) or any(k not in meta for k in _REQUIRED):
        return None
    novelty = str(meta["novelty_claim"])
    return FeedCard(
        lab_id=str(meta["lab_id"]),
        campaign_id=str(meta["campaign_id"]),
        title=_extract_title(body, novelty),
        summary=novelty,
        novelty_claim=novelty,
        status=str(meta["status"]),
        published_at=str(meta["published_at"]),
    )


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split a `---\\n{yaml}\\n---\\n\\n{body}` document. Returns (yaml, body)."""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    return parts[1], parts[2]


def _extract_title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return fallback[:80]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_feed.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add efferents/journal/ tests/test_feed.py
git commit -m "feat(journal): add feed renderer (paper markdown -> feed cards)"
```

---

## Task 2: Lab reader (`efferents/dashboard/reader.py`)

**Files:**
- Create: `efferents/dashboard/__init__.py`
- Create: `efferents/dashboard/reader.py`
- Test: `tests/test_dashboard_reader.py`

Context: reuse existing helpers — `efferents.agents.state.recent_runs(db, n)`, `efferents.agents.state.campaign_open_list(db, lab_id)`, `efferents.daemon.read_pidfile(path)` / `is_pid_alive(pid)`, and `efferents.lab.get_config()`. The `smoke_lab_config` fixture in `tests/conftest.py` installs a `LabConfig` (lab_id `smoke-fixture`, headline column `synthetic_loss`) automatically per test, so `get_config()` works in tests.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_reader.py`:

```python
import sqlite3
from pathlib import Path

from efferents.dashboard import reader


def _make_runs_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT, "
        "ended_at TEXT, synthetic_loss REAL)"
    )
    conn.executemany(
        "INSERT INTO runs (run_id, started_at, synthetic_loss) VALUES (?, ?, ?)",
        [("r1", "2026-06-01T10:00:00", 0.08),
         ("r2", "2026-06-01T10:01:00", 0.05),
         ("r3", "2026-06-01T10:02:00", 0.03)],
    )
    conn.commit()
    conn.close()


def test_read_state_stopped_when_no_pidfile(tmp_path, smoke_lab_config):
    state = reader.read_state(tmp_path)
    assert state["lab_id"] == "smoke-fixture"
    assert state["status"] == "stopped"
    assert state["budget"]["spent"] == 0.0
    assert "cap" in state["budget"]


def test_read_state_budget_sums_cost(tmp_path, smoke_lab_config):
    (tmp_path / "budget.jsonl").write_text(
        '{"cost_usd": 0.01}\n{"cost_usd": 0.02}\n'
    )
    state = reader.read_state(tmp_path)
    assert abs(state["budget"]["spent"] - 0.03) < 1e-9


def test_read_runs_returns_headline_and_series(tmp_path, smoke_lab_config):
    _make_runs_db(tmp_path / "runs.sqlite")
    out = reader.read_runs(tmp_path)
    assert out["headline"] == {"column": "synthetic_loss", "direction": "min"}
    assert [r["run_id"] for r in out["runs"]] == ["r3", "r2", "r1"]  # newest first
    assert [pt["value"] for pt in out["series"]] == [0.08, 0.05, 0.03]  # oldest->newest


def test_read_runs_empty_when_no_db(tmp_path, smoke_lab_config):
    out = reader.read_runs(tmp_path)
    assert out["runs"] == []
    assert out["series"] == []
    assert out["headline"]["column"] == "synthetic_loss"


def test_read_papers_reads_paper_dir(tmp_path, smoke_lab_config):
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "camp-1.md").write_text(
        "---\nlab_id: smoke-fixture\ncampaign_id: camp-1\n"
        "novelty_claim: A real finding.\npublished_at: 2026-06-09\n"
        "status: preprint\n---\n\n# Title\n\nbody\n"
    )
    papers = reader.read_papers(tmp_path)
    assert len(papers) == 1
    assert papers[0]["campaign_id"] == "camp-1"
    assert papers[0]["title"] == "Title"


def test_read_papers_empty_when_no_dir(tmp_path, smoke_lab_config):
    assert reader.read_papers(tmp_path) == []


def test_read_activity_parses_notebook(tmp_path, smoke_lab_config):
    (tmp_path / "lab_notebook.md").write_text(
        "## 2026-06-01T10:00:00+00:00 — orchestrator start\n\n"
        "efferents daemon\n\n"
        "## 2026-06-01T10:05:00+00:00 — Researcher mode: refine\n\n"
        "proposed 4 configs\n\n"
    )
    acts = reader.read_activity(tmp_path)
    assert acts[0]["title"] == "Researcher mode: refine"  # newest first
    assert acts[1]["title"] == "orchestrator start"


def test_read_activity_empty_when_no_notebook(tmp_path, smoke_lab_config):
    assert reader.read_activity(tmp_path) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dashboard_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'efferents.dashboard'`

- [ ] **Step 3: Write the implementation**

Create `efferents/dashboard/__init__.py` (empty file).

Create `efferents/dashboard/reader.py`:

```python
"""Read a lab directory into plain dicts for the dashboard endpoints.

Read-only. Tolerant of missing files (a stopped or just-initialized lab still
renders). No HTTP knowledge — pure file/db reads, so it is testable without a
socket.
"""

from __future__ import annotations

import json
from pathlib import Path

from efferents import daemon
from efferents import lab as lab_mod
from efferents.agents import state as state_mod
from efferents.journal.feed import render_feed


def read_state(lab_root: Path) -> dict:
    lab_root = Path(lab_root)
    cfg = lab_mod.get_config()
    pid = daemon.read_pidfile(lab_root / "daemon.pid")
    running = pid is not None and daemon.is_pid_alive(pid)
    return {
        "lab_id": cfg.lab_id,
        "domain": cfg.domain,
        "status": "running" if running else "stopped",
        "budget": {
            "spent": _budget_spent(lab_root / "budget.jsonl"),
            "cap": cfg.budget.daily_cap_usd,
        },
        "hypothesis": _current_hypothesis(lab_root, cfg.lab_id),
    }


def read_runs(lab_root: Path, n: int = 30) -> dict:
    lab_root = Path(lab_root)
    cfg = lab_mod.get_config()
    column = cfg.metrics.headline.column
    direction = cfg.metrics.headline.direction
    db = lab_root / "runs.sqlite"
    rows = state_mod.recent_runs(db, n) if db.exists() else []
    runs = [
        {"run_id": r.get("run_id"), "started_at": r.get("started_at"),
         "value": r.get(column)}
        for r in rows
    ]
    series = [
        {"started_at": r["started_at"], "value": r["value"]}
        for r in reversed(runs)
        if r["value"] is not None
    ]
    return {"headline": {"column": column, "direction": direction},
            "runs": runs, "series": series}


def read_papers(lab_root: Path) -> list[dict]:
    lab_root = Path(lab_root)
    paths: list[Path] = []
    for name in ("paper", "papers"):  # writer uses 'paper'; CLI pre-creates 'papers'
        d = lab_root / name
        if d.exists():
            paths.extend(sorted(d.glob("*.md")))
    return [c.model_dump() for c in render_feed(paths)]


def read_activity(lab_root: Path, n: int = 20) -> list[dict]:
    nb = Path(lab_root) / "lab_notebook.md"
    if not nb.exists():
        return []
    text = nb.read_text()
    entries: list[dict] = []
    for block in text.split("\n## "):
        block = block.lstrip("# ").rstrip()
        if not block:
            continue
        head, _, body = block.partition("\n")
        timestamp, _, title = head.partition(" — ")
        entries.append({
            "timestamp": timestamp.strip(),
            "title": title.strip(),
            "body": body.strip()[:300],
        })
    entries.reverse()
    return entries[:n]


def _budget_spent(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = 0.0
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            total += float(json.loads(line).get("cost_usd", 0.0))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return total


def _current_hypothesis(lab_root: Path, lab_id: str) -> dict:
    question = ""
    student = ""
    db = lab_root / "runs.sqlite"
    if db.exists():
        try:
            campaigns = state_mod.campaign_open_list(db, lab_id)
        except Exception:
            campaigns = []
        if campaigns:
            latest = max(campaigns, key=lambda c: c.get("opened_at", ""))
            question = latest.get("question", "") or ""
            student = latest.get("student_id", "") or ""
    hyp_md = lab_root / "hypothesis.md"
    claim = falsifier = ""
    if hyp_md.exists():
        text = hyp_md.read_text()
        claim = _section(text, "Claim")
        falsifier = _section(text, "Falsifier")
    return {"question": question, "claim": claim,
            "falsifier": falsifier, "student": student}


def _section(markdown: str, name: str) -> str:
    """Return the text under a `## {name}` heading, up to the next `##`."""
    lines = markdown.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        if line.strip().startswith("## "):
            if capturing:
                break
            capturing = line.strip()[3:].strip().lower() == name.lower()
            continue
        if capturing:
            out.append(line)
    return "\n".join(out).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dashboard_reader.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add efferents/dashboard/__init__.py efferents/dashboard/reader.py tests/test_dashboard_reader.py
git commit -m "feat(dashboard): add lab reader (state/runs/papers/activity)"
```

---

## Task 3: HTTP server (`efferents/dashboard/server.py`)

**Files:**
- Create: `efferents/dashboard/server.py`
- Test: `tests/test_dashboard_server.py`

Context: stdlib `http.server`. We bind a `BaseHTTPRequestHandler` subclass that carries `lab_root` via `functools.partial`. Static files are read from `efferents/dashboard/static/` (created in Task 4; the server only needs the directory to exist for the `/` route, which Task 3's tests do not exercise — they hit `/api/*`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_server.py`:

```python
import json
import sqlite3
import threading
import urllib.request
from pathlib import Path

import pytest

from efferents.dashboard import server


def _make_runs_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT, "
        "ended_at TEXT, synthetic_loss REAL)"
    )
    conn.execute(
        "INSERT INTO runs (run_id, started_at, synthetic_loss) VALUES (?, ?, ?)",
        ("r1", "2026-06-01T10:00:00", 0.05),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def running_server(tmp_path, smoke_lab_config):
    _make_runs_db(tmp_path / "runs.sqlite")
    httpd = server.make_server(tmp_path, port=0)  # port 0 -> OS picks a free port
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield port
    httpd.shutdown()


def _get(port: int, path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as resp:
        return resp.status, json.loads(resp.read())


def test_api_state(running_server):
    status, body = _get(running_server, "/api/state")
    assert status == 200
    assert body["lab_id"] == "smoke-fixture"
    assert body["status"] == "stopped"


def test_api_runs(running_server):
    status, body = _get(running_server, "/api/runs")
    assert status == 200
    assert body["headline"]["column"] == "synthetic_loss"
    assert body["runs"][0]["run_id"] == "r1"


def test_api_papers_empty(running_server):
    status, body = _get(running_server, "/api/papers")
    assert status == 200
    assert body == []


def test_api_activity_empty(running_server):
    status, body = _get(running_server, "/api/activity")
    assert status == 200
    assert body == []


def test_unknown_path_404(running_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"http://127.0.0.1:{running_server}/nope")
    assert exc.value.code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dashboard_server.py -v`
Expected: FAIL with `ImportError: cannot import name 'make_server'`

- [ ] **Step 3: Write the implementation**

Create `efferents/dashboard/server.py`:

```python
"""Local read-only HTTP server for the lab dashboard.

Stdlib http.server only — no web framework dependency. Serves the static
dashboard page plus JSON endpoints backed by `reader`. Read-only: there are no
POST/PUT routes and nothing here mutates lab state.
"""

from __future__ import annotations

import json
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from efferents.dashboard import reader

STATIC_DIR = Path(__file__).parent / "static"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}


class DashboardHandler(BaseHTTPRequestHandler):
    lab_root: Path

    def __init__(self, *args, lab_root: Path, **kwargs):
        self.lab_root = Path(lab_root)
        super().__init__(*args, **kwargs)

    def do_GET(self):  # noqa: N802 (stdlib naming)
        try:
            if self.path in ("/", "/index.html"):
                return self._send_file(STATIC_DIR / "dashboard.html")
            if self.path == "/api/state":
                return self._send_json(reader.read_state(self.lab_root))
            if self.path == "/api/runs":
                return self._send_json(reader.read_runs(self.lab_root))
            if self.path == "/api/papers":
                return self._send_json(reader.read_papers(self.lab_root))
            if self.path == "/api/activity":
                return self._send_json(reader.read_activity(self.lab_root))
            if self.path.startswith("/static/"):
                target = (STATIC_DIR / self.path[len("/static/"):]).resolve()
                if STATIC_DIR in target.parents and target.is_file():
                    return self._send_file(target)
            self.send_error(404)
        except Exception as exc:  # read-only server: report, don't crash
            self.send_error(500, str(exc))

    def _send_json(self, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",
                         _CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # silence per-request stderr logging
        pass


def make_server(lab_root: Path, port: int = 8800) -> ThreadingHTTPServer:
    handler = partial(DashboardHandler, lab_root=Path(lab_root))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(lab_root: Path, port: int = 8800, open_browser: bool = True) -> None:
    httpd = make_server(lab_root, port)
    url = f"http://localhost:{httpd.server_address[1]}"
    print(f"efferents dashboard: {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dashboard_server.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add efferents/dashboard/server.py tests/test_dashboard_server.py
git commit -m "feat(dashboard): add stdlib http server with /api endpoints"
```

---

## Task 4: Dashboard frontend (`efferents/dashboard/static/`)

**Files:**
- Create: `efferents/dashboard/static/dashboard.html`
- Create: `efferents/dashboard/static/dashboard.css`
- Create: `efferents/dashboard/static/dashboard.js`
- Test: `tests/test_dashboard_server.py` (add one route test)

No build step. Vanilla JS polls the four endpoints every 4s and renders the five panels from §2 of the spec.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_dashboard_server.py`:

```python
def test_root_serves_dashboard_html(running_server):
    with urllib.request.urlopen(
        f"http://127.0.0.1:{running_server}/"
    ) as resp:
        assert resp.status == 200
        assert resp.headers["Content-Type"].startswith("text/html")
        html = resp.read().decode()
    assert "dashboard.js" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dashboard_server.py::test_root_serves_dashboard_html -v`
Expected: FAIL — `FileNotFoundError` / 500, because `static/dashboard.html` does not exist yet.

- [ ] **Step 3: Write the implementation**

Create `efferents/dashboard/static/dashboard.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>efferents — lab dashboard</title>
  <link rel="stylesheet" href="/static/dashboard.css">
</head>
<body>
  <header id="topbar">
    <div><b id="lab-id">…</b> <span id="domain" class="muted"></span></div>
    <div class="topbar-right">
      <span id="status-badge" class="badge">…</span>
      <span id="budget" class="muted"></span>
    </div>
  </header>

  <main>
    <section class="col-main">
      <div class="card">
        <div class="label">Current hypothesis <span id="student" class="muted"></span></div>
        <div id="question"></div>
        <div id="claim" class="muted small"></div>
        <div id="falsifier" class="muted small"></div>
      </div>

      <div class="card">
        <div class="label" id="metric-label">Headline metric</div>
        <svg id="trend" viewBox="0 0 100 40" preserveAspectRatio="none"></svg>
        <div id="trend-caption" class="muted small"></div>
      </div>

      <div class="card">
        <div class="label">Recent runs</div>
        <table id="runs"><tbody></tbody></table>
      </div>
    </section>

    <section class="col-side">
      <div class="card">
        <div class="label accent">Papers</div>
        <div id="papers"></div>
      </div>
      <div class="card">
        <div class="label">Agent activity</div>
        <div id="activity"></div>
      </div>
    </section>
  </main>

  <script src="/static/dashboard.js"></script>
</body>
</html>
```

Create `efferents/dashboard/static/dashboard.css`:

```css
:root { --bg:#0d0f12; --panel:#161a1f; --line:#2a2f37; --fg:#e6e8eb;
        --muted:#8b939c; --accent:#88f; --ok:#4a9; --warn:#c84; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:14px/1.5 -apple-system, system-ui, sans-serif; }
#topbar { display:flex; justify-content:space-between; align-items:center;
          padding:12px 18px; border-bottom:1px solid var(--line); }
.topbar-right { display:flex; gap:16px; align-items:center; }
.badge { padding:2px 8px; border-radius:10px; border:1px solid var(--line); }
.badge.running { color:var(--ok); border-color:var(--ok); }
.badge.stopped { color:var(--muted); }
main { display:flex; gap:14px; padding:16px; flex-wrap:wrap; }
.col-main { flex:2; min-width:320px; display:flex; flex-direction:column; gap:14px; }
.col-side { flex:1; min-width:260px; display:flex; flex-direction:column; gap:14px; }
.card { background:var(--panel); border:1px solid var(--line);
        border-radius:8px; padding:12px 14px; }
.label { text-transform:uppercase; font-size:11px; letter-spacing:.06em;
         color:var(--muted); margin-bottom:6px; }
.label.accent { color:var(--accent); }
.muted { color:var(--muted); }
.small { font-size:12px; }
table#runs { width:100%; border-collapse:collapse; font-size:12px; }
table#runs td { padding:3px 4px; border-bottom:1px solid var(--line); }
#trend { width:100%; height:80px; }
#trend polyline { fill:none; stroke:var(--ok); stroke-width:1; }
.paper { border-left:2px solid var(--accent); padding:4px 8px; margin-bottom:8px; }
.act { font-size:12px; padding:3px 0; border-bottom:1px solid var(--line); }
.act .when { color:var(--muted); }
```

Create `efferents/dashboard/static/dashboard.js`:

```javascript
async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

function text(id, value) { document.getElementById(id).textContent = value || ""; }

function renderState(s) {
  text("lab-id", s.lab_id);
  text("domain", "· " + s.domain);
  const badge = document.getElementById("status-badge");
  badge.textContent = s.status;
  badge.className = "badge " + s.status;
  text("budget", `budget $${(s.budget.spent).toFixed(2)} / $${s.budget.cap}`);
  text("student", s.hypothesis.student ? "· " + s.hypothesis.student : "");
  text("question", s.hypothesis.question || "(no open campaign)");
  text("claim", s.hypothesis.claim);
  text("falsifier", s.hypothesis.falsifier);
}

function renderRuns(d) {
  text("metric-label", `${d.headline.column} (${d.headline.direction})`);
  const tbody = document.querySelector("#runs tbody");
  tbody.innerHTML = "";
  d.runs.forEach(r => {
    const tr = document.createElement("tr");
    const v = r.value == null ? "—" : r.value;
    tr.innerHTML = `<td>${(r.run_id || "").slice(0, 6)}</td>` +
                   `<td class="muted">${r.started_at || ""}</td><td>${v}</td>`;
    tbody.appendChild(tr);
  });
  renderTrend(d.series);
}

function renderTrend(series) {
  const svg = document.getElementById("trend");
  svg.innerHTML = "";
  if (!series.length) return;
  const vals = series.map(p => p.value);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const pts = series.map((p, i) => {
    const x = series.length === 1 ? 0 : (i / (series.length - 1)) * 100;
    const y = 40 - ((p.value - min) / span) * 38 - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  poly.setAttribute("points", pts);
  svg.appendChild(poly);
  const best = Math.min(...vals);
  text("trend-caption", `${series.length} runs · best ${best}`);
}

function renderPapers(papers) {
  const el = document.getElementById("papers");
  if (!papers.length) { el.innerHTML = '<div class="muted small">no papers yet</div>'; return; }
  el.innerHTML = papers.map(p =>
    `<div class="paper"><div><b>${p.title}</b></div>` +
    `<div class="muted small">${p.status} · ${p.published_at}</div></div>`).join("");
}

function renderActivity(acts) {
  const el = document.getElementById("activity");
  el.innerHTML = acts.map(a =>
    `<div class="act"><span class="when">${a.timestamp}</span> — ${a.title}</div>`
  ).join("") || '<div class="muted small">no activity yet</div>';
}

async function tick() {
  try {
    renderState(await getJSON("/api/state"));
    renderRuns(await getJSON("/api/runs"));
    renderPapers(await getJSON("/api/papers"));
    renderActivity(await getJSON("/api/activity"));
  } catch (e) {
    console.error(e);
  }
}

tick();
setInterval(tick, 4000);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dashboard_server.py -v`
Expected: PASS (6 tests total)

- [ ] **Step 5: Commit**

```bash
git add efferents/dashboard/static/ tests/test_dashboard_server.py
git commit -m "feat(dashboard): add vanilla-JS frontend (5 panels, 4s polling)"
```

---

## Task 5: CLI `serve` subcommand (`efferents/cli.py`)

**Files:**
- Modify: `efferents/cli.py` (add `_cmd_serve` and its subparser)
- Test: `tests/test_cli_serve.py`

Context: `cli.py` uses argparse subparsers with `.set_defaults(func=...)`. `LabConfig.from_submission(dir)` reads `hypothesis.md` + `lab.yaml` from `dir`; the CLI copies both into the lab root at init, so a lab root is a valid "submission" for config loading. Mirror the existing `_cmd_start` import style (`from efferents.lab import LabConfig`, `from efferents import lab as lab_mod`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_serve.py`:

```python
import efferents.cli as cli


def test_serve_subcommand_parses():
    parser = cli.build_parser()
    args = parser.parse_args(["serve", "--lab-root", "lab", "--port", "9001", "--no-open"])
    assert args.func is cli._cmd_serve
    assert args.lab_root == "lab"
    assert args.port == 9001
    assert args.no_open is True


def test_serve_defaults():
    parser = cli.build_parser()
    args = parser.parse_args(["serve"])
    assert args.lab_root == "lab"
    assert args.port == 8800
    assert args.no_open is False


def test_cmd_serve_loads_config_and_starts(tmp_path, monkeypatch):
    # Minimal valid submission: hypothesis.md + lab.yaml
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: t\nfalsifiability_gate: passed\nstatus: active\n---\n# H\n"
    )
    (tmp_path / "lab.yaml").write_text(
        "lab_id: t\ndomain: d\n"
        "source:\n  dir: ./src/\n"
        "executor:\n  run_command: 'python -m x --config {config_path}'\n"
        "  config_template: configs/default.yaml\n"
        "metrics:\n  headline:\n    column: loss\n    direction: min\n"
        "  panels:\n    - { column: loss, label: Loss }\n"
        "budget:\n  daily_cap_usd: 1.0\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "default.yaml").touch()

    called = {}

    def fake_serve(lab_root, port, open_browser):
        called["lab_root"] = str(lab_root)
        called["port"] = port
        called["open_browser"] = open_browser

    monkeypatch.setattr("efferents.dashboard.server.serve", fake_serve)

    import argparse
    args = argparse.Namespace(lab_root=str(tmp_path), port=8800, no_open=True)
    rc = cli._cmd_serve(args)
    assert rc == 0
    assert called["port"] == 8800
    assert called["open_browser"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_serve.py -v`
Expected: FAIL — `AttributeError: module 'efferents.cli' has no attribute '_cmd_serve'` (and/or `build_parser`).

- [ ] **Step 3: Write the implementation**

First, check `efferents/cli.py` for how the parser is built. If the subparser setup currently lives inline inside `main()`, extract it into a `build_parser()` function so it is testable, and have `main()` call it. Concretely:

In `efferents/cli.py`, ensure there is a `build_parser()` function returning the configured `ArgumentParser` (move the existing `argparse.ArgumentParser(...)` + `add_subparsers()` + all `add_parser(...)` blocks into it if not already), and that `main()` does `parser = build_parser()`.

Then add the `serve` handler near the other `_cmd_*` functions:

```python
def _cmd_serve(args: argparse.Namespace) -> int:
    from efferents.dashboard import server as dash_server

    lab_root = Path(args.lab_root).resolve()
    try:
        cfg = LabConfig.from_submission(lab_root)
    except SubmissionError as e:
        print(f"could not load lab config from {lab_root}: {e}", file=sys.stderr)
        return 1
    lab_mod.set_config(cfg)
    dash_server.serve(lab_root, port=args.port, open_browser=not args.no_open)
    return 0
```

And register the subparser inside `build_parser()`, alongside the existing ones:

```python
    p_serve = sub.add_parser("serve", help="Start the read-only web dashboard")
    p_serve.add_argument("--lab-root", default="lab")
    p_serve.add_argument("--port", type=int, default=8800)
    p_serve.add_argument("--no-open", action="store_true",
                         help="Do not auto-open the browser")
    p_serve.set_defaults(func=_cmd_serve)
```

(Confirm `LabConfig`, `SubmissionError`, `lab_mod`, `sys`, `Path`, and `argparse` are already imported at the top of `cli.py` — they are used by `_cmd_start`/`_cmd_validate`. Reuse those imports.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_serve.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest tests/test_feed.py tests/test_dashboard_reader.py tests/test_dashboard_server.py tests/test_cli_serve.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add efferents/cli.py tests/test_cli_serve.py
git commit -m "feat(cli): add 'efferents serve' subcommand for the dashboard"
```

---

## Task 6: Landing page (`web/landing/`)

**Files:**
- Create: `web/landing/index.html`
- Create: `web/landing/style.css`
- Test: `tests/test_landing.py`

Static, deployable to GitHub Pages now and efferents.com later. Mirrors §4 of the spec.

- [ ] **Step 1: Write the failing test**

Create `tests/test_landing.py`:

```python
from pathlib import Path

LANDING = Path(__file__).resolve().parents[1] / "web" / "landing" / "index.html"


def test_landing_exists():
    assert LANDING.is_file()


def test_landing_has_agent_instruction():
    html = LANDING.read_text()
    assert "intake.md" in html
    assert "Read https://efferents.com/intake.md and follow it" in html


def test_landing_links_stylesheet():
    assert 'href="style.css"' in LANDING.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_landing.py -v`
Expected: FAIL on `test_landing_exists` (file missing).

- [ ] **Step 3: Write the implementation**

Create `web/landing/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>efferents — autonomous research labs</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <nav>
    <b>efferents</b>
    <div class="nav-links">
      <a href="#how">how it works</a>
      <a href="https://efferents.com/intake.md">intake.md</a>
    </div>
  </nav>

  <header class="hero">
    <h1>Autonomous research labs that publish papers.</h1>
    <p class="lede">
      Spin up a lab on your own machine. It forms falsifiable hypotheses, runs
      experiments, and publishes results to a shared journal — on its own.
    </p>
    <div class="entry">
      <div class="entry-card human">
        <div class="label">For humans</div>
        <a href="#how">Read how it works ↓</a>
      </div>
      <div class="entry-card agent">
        <div class="label">For your agent</div>
        <pre id="agent-cmd">Read https://efferents.com/intake.md and follow it</pre>
        <button onclick="copyCmd()">copy</button>
      </div>
    </div>
  </header>

  <section id="how">
    <div class="label">How it works</div>
    <ol class="steps">
      <li>Your agent reads <code>intake.md</code> and installs efferents.</li>
      <li>A popper-probe dialogue in your terminal sharpens the claim into a
          falsifiable hypothesis.</li>
      <li>The daemon runs locally and publishes papers to the shared journal.</li>
    </ol>
  </section>

  <section id="journal">
    <div class="label accent">From the journal
      <span class="muted">(live once the journal repo is wired — preview for now)</span>
    </div>
    <div class="feed">
      <div class="feed-card">
        <div class="muted small">smoke-coefficient · 2026-06-09</div>
        <b>Baseline synthetic loss achievable…</b>
        <div class="small">coefficient ∈ (0.75, 0.85) ✓</div>
      </div>
      <div class="feed-card placeholder">your lab here →</div>
    </div>
  </section>

  <footer>efferents · markdown is the SDK</footer>

  <script>
    function copyCmd() {
      navigator.clipboard.writeText(
        document.getElementById("agent-cmd").textContent.trim());
    }
  </script>
</body>
</html>
```

Create `web/landing/style.css`:

```css
:root { --bg:#0d0f12; --panel:#161a1f; --line:#2a2f37; --fg:#e6e8eb;
        --muted:#8b939c; --accent:#88f; --ok:#4a9; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:15px/1.6 -apple-system, system-ui, sans-serif; }
nav { display:flex; justify-content:space-between; align-items:center;
      padding:14px 24px; border-bottom:1px solid var(--line); }
.nav-links a { color:var(--muted); margin-left:18px; text-decoration:none; }
.hero { text-align:center; padding:64px 20px; border-bottom:1px solid var(--line); }
.hero h1 { font-size:32px; margin:0 0 12px; }
.lede { color:var(--muted); max-width:560px; margin:0 auto 28px; }
.entry { display:flex; gap:16px; justify-content:center; flex-wrap:wrap; }
.entry-card { border:1px solid var(--line); border-radius:8px; padding:14px 18px;
              text-align:left; min-width:240px; }
.entry-card.human { border-color:var(--ok); }
.entry-card.agent { border-color:var(--accent); }
.entry-card a { color:var(--fg); text-decoration:none; }
.label { text-transform:uppercase; font-size:11px; letter-spacing:.06em;
         color:var(--muted); margin-bottom:8px; }
.label.accent { color:var(--accent); }
pre { background:#000; border-radius:6px; padding:10px; font-size:12px;
      white-space:pre-wrap; margin:0 0 8px; }
button { background:var(--accent); border:0; color:#000; border-radius:5px;
         padding:5px 12px; cursor:pointer; }
section { max-width:760px; margin:0 auto; padding:32px 20px; }
.steps li { margin-bottom:10px; }
.feed { display:flex; gap:14px; flex-wrap:wrap; }
.feed-card { flex:1; min-width:200px; border-left:2px solid var(--accent);
             padding:8px 12px; background:rgba(136,136,255,.06); border-radius:0 6px 6px 0; }
.feed-card.placeholder { border-left-color:var(--line); color:var(--muted);
                         background:none; display:flex; align-items:center; }
.muted { color:var(--muted); } .small { font-size:12px; }
code { background:#000; padding:1px 5px; border-radius:4px; }
footer { text-align:center; color:var(--muted); padding:32px;
         border-top:1px solid var(--line); }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_landing.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add web/landing/ tests/test_landing.py
git commit -m "feat(web): add static landing page (moltbook-shaped)"
```

---

## Task 7: End-to-end verification + README note

**Files:**
- Modify: `README.md` (add a short "Visual surfaces" section)
- No new test; this task is manual verification against the smoke-lab.

- [ ] **Step 1: Run the whole test suite**

Run: `uv run pytest tests/test_feed.py tests/test_dashboard_reader.py tests/test_dashboard_server.py tests/test_cli_serve.py tests/test_landing.py -v`
Expected: all PASS.

- [ ] **Step 2: Manually verify the dashboard against the smoke-lab**

The smoke-lab at `examples/smoke-lab/` already has a populated `lab/` dir (runs.sqlite, state.json, lab_notebook.md, hypothesis.md, lab.yaml).

Run:
```bash
uv run efferents serve --lab-root examples/smoke-lab/lab --no-open
```
Expected stdout: `efferents dashboard: http://localhost:8800  (Ctrl-C to stop)`

Open `http://localhost:8800` in a browser. Verify:
- Top bar shows `smoke-coefficient · synthetic`, a `stopped` badge (daemon isn't running), and a budget figure.
- "Current hypothesis" shows the claim/falsifier from `hypothesis.md`.
- "Recent runs" lists rows and the trend SVG draws a line.
- "Agent activity" lists notebook entries (newest first).
- "Papers" shows "no papers yet" (smoke-lab `paper/` is empty) — this is correct.

Stop with Ctrl-C. Confirm clean exit.

- [ ] **Step 3: Manually verify the landing page**

Run:
```bash
uv run python -m http.server 8localhost 2>/dev/null || (cd web/landing && uv run python -m http.server 8001)
```
(Simplest: `cd web/landing && python3 -m http.server 8001`.)
Open `http://localhost:8001`. Verify the hero, the copy-paste agent command block (click "copy", paste to confirm), the 3-step how-it-works, and the stubbed journal preview all render.

- [ ] **Step 4: Add a README note**

Add this section to `README.md` (under the existing layout/usage content):

```markdown
## Visual surfaces

Two read-only web surfaces sit on top of the terminal/agent flow:

- **Landing page** (`web/landing/`) — a static site explaining efferents and
  handing an agent the `intake.md` instruction. Deployable to GitHub Pages /
  efferents.com. Open `web/landing/index.html` directly, or serve it with
  `python -m http.server` from that directory.
- **Local lab dashboard** — `efferents serve --lab-root <lab dir>` starts a
  local read-only dashboard (default http://localhost:8800) that visualizes the
  running lab: current hypothesis, run/metric trend, published papers, and agent
  activity. It reads the lab's files; it never mutates state. popper-probe and
  launching stay in the terminal.

The journal feed renderer (`efferents/journal/feed.py`) reads paper markdown
into feed cards today from the local `lab/paper/` dir; the same renderer will be
pointed at a shared `efferents-journal` git repo when the hosted journal ships.
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document the landing page and 'efferents serve' dashboard"
```

---

## Self-Review Notes

- **Spec coverage:** §1 architecture → Tasks 1–6 (the three units + CLI + landing). §2 dashboard (5 panels, endpoints, stdlib server, `metrics.panels`-driven headline) → Tasks 2–4. §3 feed renderer (`render_feed(paths) -> [FeedCard]`, pure, skips malformed) → Task 1. §4 landing (nav/hero/dual-entry/how-it-works/stubbed feed) → Task 6. §5 layout/`efferents serve`/testing/zero-deps → Tasks 5, 7, and per-task tests. Error handling (missing dir/empty lab/stopped daemon/malformed frontmatter/port in use) → reader/feed tolerance tests + server 500 guard.
- **Type consistency:** `FeedCard` fields and `reader.*` dict shapes are defined once in the File Structure contracts and reused verbatim in Tasks 1–4 and the JS. `make_server(lab_root, port)` / `serve(lab_root, port, open_browser)` signatures match between Task 3 and Task 5. `build_parser()` / `_cmd_serve` names match between Task 5 impl and test.
- **Known existing inconsistency handled:** writer writes to `lab/paper/` (singular); CLI pre-creates `lab/papers/` (plural). `read_papers` globs both, so it works regardless. Not fixing the upstream inconsistency here (out of scope).
- **Budget caveat:** `_budget_spent` sums all `cost_usd` in `budget.jsonl` (cumulative, not day-scoped). Acceptable for v1 display; note for future refinement.
```
