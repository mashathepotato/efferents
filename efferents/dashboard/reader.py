"""Read a lab directory into plain dicts for the dashboard endpoints.

Read-only. Tolerant of missing files (a stopped or just-initialized lab still
renders). No HTTP knowledge — pure file/db reads, so it is testable without a
socket.
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

_ACTIVITY_BODY_PREVIEW = 300

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
    def _finite(x):
        return x if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None

    db = lab_root / "runs.sqlite"
    rows = state_mod.recent_runs(db, n) if db.exists() else []
    runs = [
        {"run_id": r.get("run_id"), "started_at": r.get("started_at"),
         "value": _finite(r.get(column))}
        for r in rows
    ]
    series = [
        {"started_at": r["started_at"], "value": r["value"]}
        for r in reversed(runs)
        if r["value"] is not None and r["started_at"] is not None
    ]
    return {"headline": {"column": column, "direction": direction},
            "runs": runs, "series": series}


def read_papers(lab_root: Path) -> list[dict]:
    lab_root = Path(lab_root)
    paths: list[Path] = []
    seen: set[str] = set()
    for name in ("paper", "papers"):  # writer uses 'paper'; CLI pre-creates 'papers'
        d = lab_root / name
        if d.exists():
            for p in sorted(d.glob("*.md")):
                if p.name not in seen:
                    seen.add(p.name)
                    paths.append(p)
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
        timestamp, sep, title = head.partition(" — ")
        if not sep:
            continue
        entries.append({
            "timestamp": timestamp.strip(),
            "title": title.strip(),
            "body": body.strip()[:_ACTIVITY_BODY_PREVIEW],
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
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
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
    """Return the text under a `## {name}` heading, up to the next `## ` heading."""
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
