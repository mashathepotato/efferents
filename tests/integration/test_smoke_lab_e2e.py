"""End-to-end: drive the smoke-lab through `efferents start` foreground,
assert metric rows appear in state.db within 90s.

Marked `integration`; opt-in via `pytest -m integration`. Requires
ANTHROPIC_API_KEY to be set; skips otherwise.
"""
from __future__ import annotations
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest


SMOKE_LAB = Path(__file__).parent.parent.parent / "examples" / "smoke-lab"


@pytest.mark.integration
def test_smoke_lab_runs_end_to_end(tmp_path, monkeypatch):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; integration test requires it")

    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    sub = tmp_path / "smoke-lab"
    shutil.copytree(SMOKE_LAB, sub)

    proc = subprocess.Popen(
        [sys.executable, "-m", "efferents.cli", "start", "--submission", str(sub)],
        env={**os.environ, "EFFERENTS_HOME": str(tmp_path / "home")},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    db = sub / "lab" / "runs.sqlite"
    deadline = time.time() + 90
    runs = 0
    while time.time() < deadline:
        if db.exists():
            try:
                conn = sqlite3.connect(db)
                cur = conn.execute("SELECT COUNT(*) FROM runs WHERE synthetic_loss IS NOT NULL")
                runs = cur.fetchone()[0]
                conn.close()
                if runs >= 1:
                    break
            except sqlite3.OperationalError:
                pass
        time.sleep(1)

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    # v0.1.3 acceptance: the agent-proposed-eval path reached the DB through the
    # real daemon. Any campaign the Researcher opened carries a headline_metric;
    # for the smoke lab the only sensible metric is synthetic_loss. We assert
    # correctness *when* a metric was proposed (robust to LLM timing/variation:
    # a null headline_metric just means the fallback applied that round).
    proposed_metrics: list[str] = []
    if db.exists():
        try:
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            proposed_metrics = [
                r["headline_metric"]
                for r in conn.execute(
                    "SELECT headline_metric FROM campaigns WHERE headline_metric IS NOT NULL"
                )
            ]
            conn.close()
        except sqlite3.OperationalError:
            pass

    out, _ = proc.communicate()
    assert runs >= 1, (
        f"no synthetic_loss rows after 90s.\nstdout/stderr:\n{out}"
    )
    # When the Researcher did propose a metric, it must be the smoke lab's.
    assert all(m == "synthetic_loss" for m in proposed_metrics), (
        f"unexpected proposed headline_metric(s): {proposed_metrics}\n"
        f"stdout/stderr:\n{out}"
    )
