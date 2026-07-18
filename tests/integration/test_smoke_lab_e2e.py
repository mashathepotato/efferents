"""Clean end-to-end smoke: real CLI, real subprocess, no API or stale state."""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


SMOKE_LAB = Path(__file__).parent.parent.parent / "examples" / "smoke-lab"


@pytest.mark.integration
def test_smoke_lab_runs_end_to_end_from_clean_submission(tmp_path):
    sub = tmp_path / "smoke-lab"
    shutil.copytree(
        SMOKE_LAB,
        sub,
        ignore=shutil.ignore_patterns(
            "lab",
            "popper-corpus",
            ".env",
            "__pycache__",
            "*.pyc",
        ),
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"ANTHROPIC_API_KEY", "NTFY_TOKEN"}
    }
    env["EFFERENTS_HOME"] = str(tmp_path / "home")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "efferents.cli",
            "start",
            "--submission",
            str(sub),
            "--dry-run",
            "--max-iterations",
            "1",
        ],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 0, (
        f"CLI failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    lab = sub / "lab"
    db = lab / "runs.sqlite"
    assert db.is_file()
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        runs = [dict(row) for row in conn.execute("SELECT * FROM runs")]
        campaigns = [
            dict(row) for row in conn.execute("SELECT * FROM campaigns")
        ]

    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "succeeded"
    assert run["synthetic_loss"] is not None
    assert run["campaign_id"]
    assert run["campaign_id"] == campaigns[0]["id"]
    assert run["student_id"] == "primary"
    assert run["seed"] == 42  # actual seed from the rendered lab config
    assert run["config_yaml"]
    assert run["config_hash"] == "sha256:" + hashlib.sha256(
        run["config_yaml"].encode()
    ).hexdigest()
    assert Path(run["stdout_path"]).is_file()
    assert Path(run["stderr_path"]).is_file()
    assert len(campaigns) == 1
    campaign = campaigns[0]
    assert campaign["lab_id"] == "smoke-coefficient"
    assert campaign["headline_metric"] == "synthetic_loss"
    assert campaign["headline_direction"] == "min"
    progress = lab / "progress.html"
    assert progress.is_file()
    assert "smoke-coefficient" in progress.read_text()
    assert not (lab / "inflight.json").exists()
