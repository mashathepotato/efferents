"""Rewritten executor.execute routes through exec.py with generic notebook formatting."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

from efferents.agents import executor
from efferents.agents.state import LabPaths, lab_paths
from efferents.lab import (
    Budget, Executor, Headline, LabConfig, Metrics, Panel, Source,
)
from efferents import lab as lab_mod
from efferents.migrations.runner import ensure_runs_table


def _make_run_script(src: Path, metrics: dict, exit_code: int = 0) -> str:
    """Write a shell script that emits a JSON result and exits with exit_code.

    Returns the run_command string referencing the script. Uses a script file
    to avoid Python str.format() mangling the JSON braces.
    """
    payload = json.dumps({"run_id": "ignored", "metrics": metrics, "elapsed_s": 0.01})
    script = src / "run_smoke.sh"
    lines = ["#!/usr/bin/env sh", f"printf '%s\\n' '{payload}'"]
    if exit_code != 0:
        lines.append(f"exit {exit_code}")
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o755)
    return f"sh {script} {{config_path}}"


def _install_smoke(tmp_path: Path, run_cmd: str, headline="synthetic_loss"):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    cfg_template = src / "default.yaml"
    cfg_template.write_text("coefficient: 0.5\n")
    cfg = LabConfig(
        lab_id="x", domain="y", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command=run_cmd,
            smoke_command=None,
            config_template=cfg_template,
            run_timeout_s=30,
        ),
        metrics=Metrics(
            headline=Headline(column=headline, direction="min"),
            panels=(Panel(column=headline, label="Loss"),),
        ),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    return cfg


def _make_paths(tmp_path: Path) -> LabPaths:
    lab_dir = tmp_path / "lab"
    lab_dir.mkdir(exist_ok=True)
    return lab_paths(lab_dir)


def test_execute_happy_path_writes_row_and_notebook(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    run_cmd = _make_run_script(src, {"synthetic_loss": 0.42})
    cfg = _install_smoke(tmp_path, run_cmd)
    paths = _make_paths(tmp_path)
    ensure_runs_table(tmp_path / "lab" / "state.db", cfg)

    outcome = executor.execute(
        paths=paths,
        proposal={"name": "trial-1", "config_overrides": {"coefficient": 0.8},
                  "hypothesis": "lower coefficient helps", "expected": "loss < 0.1"},
    )

    assert outcome["ok"] is True
    assert outcome["name"] == "trial-1"
    assert len(outcome["rows"]) == 1
    assert outcome["rows"][0]["synthetic_loss"] == 0.42
    # Orchestrator-side run_id wins over the run_command payload's run_id
    assert outcome["rows"][0]["run_id"] != "ignored"

    conn = sqlite3.connect(tmp_path / "lab" / "state.db")
    try:
        rows = list(conn.execute("SELECT run_id, synthetic_loss FROM runs"))
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0][1] == 0.42

    nb_text = paths.notebook.read_text()
    assert "trial-1" in nb_text
    assert "synthetic_loss" in nb_text
    # No QML-specific identifiers
    assert "E_w1" not in nb_text
    assert "amp_ratio" not in nb_text


def test_execute_nonzero_exit_returns_failure(tmp_path, monkeypatch):
    # Exercise the real returncode!=0 path: emit valid JSON, then exit non-zero.
    # Without this, the test short-circuits on "no JSON" and never reaches the
    # `ok = proc.returncode == 0` check inside _run_and_capture.
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    run_cmd = _make_run_script(src, {"synthetic_loss": 0.42}, exit_code=1)
    cfg = _install_smoke(tmp_path, run_cmd)
    paths = _make_paths(tmp_path)
    ensure_runs_table(tmp_path / "lab" / "state.db", cfg)

    outcome = executor.execute(
        paths=paths,
        proposal={"name": "fail-1", "config_overrides": {},
                  "hypothesis": "", "expected": ""},
    )
    assert outcome["ok"] is False
    assert outcome["name"] == "fail-1"
    # _persist_run_result still writes the row because metrics were emitted;
    # the orchestrator-side ok=False signals "treat this run as failed
    # downstream" while the metric trace is preserved for analyst inspection.
    conn = sqlite3.connect(tmp_path / "lab" / "state.db")
    try:
        rows = list(conn.execute("SELECT run_id, synthetic_loss FROM runs"))
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0][1] == 0.42


def test_execute_no_json_returns_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd = "echo plain-text-no-json"
    cfg = _install_smoke(tmp_path, cmd)
    paths = _make_paths(tmp_path)
    ensure_runs_table(tmp_path / "lab" / "state.db", cfg)

    outcome = executor.execute(
        paths=paths,
        proposal={"name": "nojson", "config_overrides": {},
                  "hypothesis": "", "expected": ""},
    )
    assert outcome["ok"] is False
    assert "JSON" in (outcome.get("error") or "")


def test_execute_writes_rendered_config_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    run_cmd = _make_run_script(src, {"synthetic_loss": 0.1})
    cfg = _install_smoke(tmp_path, run_cmd)
    paths = _make_paths(tmp_path)
    ensure_runs_table(tmp_path / "lab" / "state.db", cfg)

    outcome = executor.execute(
        paths=paths,
        proposal={"name": "render-test", "config_overrides": {"coefficient": 0.9},
                  "hypothesis": "", "expected": ""},
    )
    assert outcome["ok"] is True
    configs_dir = paths.root / "configs"
    files = list(configs_dir.glob("run_*.yaml"))
    assert len(files) == 1
    rendered = yaml.safe_load(files[0].read_text())
    assert rendered["coefficient"] == 0.9
    assert rendered["run"]["name"] == "render-test"
