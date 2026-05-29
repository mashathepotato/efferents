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

    out, _ = proc.communicate()
    assert runs >= 1, (
        f"no synthetic_loss rows after 90s.\nstdout/stderr:\n{out}"
    )
