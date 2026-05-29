"""_persist_run_result and _execute_run live in efferents.exec."""
from __future__ import annotations
import sqlite3
from pathlib import Path

from efferents.exec import RunResult, _execute_run, _persist_run_result


def test_persist_run_result_inserts_metrics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lab").mkdir()
    db = tmp_path / "lab" / "runs.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT, "
        "config_path TEXT, synthetic_loss REAL, duration_seconds REAL, git_commit TEXT)"
    )
    conn.commit()
    conn.close()

    result = RunResult(
        ok=True,
        metrics={"synthetic_loss": 0.42},
        elapsed_s=12.3,
        git_commit="abc123",
    )
    _persist_run_result(result, "test-1", Path("configs/default.yaml"))

    conn = sqlite3.connect(db)
    rows = list(conn.execute("SELECT run_id, synthetic_loss, duration_seconds, git_commit FROM runs"))
    conn.close()
    assert rows == [("test-1", 0.42, 12.3, "abc123")]


def test_persist_run_result_skips_when_no_metrics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lab").mkdir()
    db = tmp_path / "lab" / "runs.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT, "
        "config_path TEXT)"
    )
    conn.commit()
    conn.close()

    result = RunResult(ok=False, metrics=None, error="run failed")
    _persist_run_result(result, "test-2", Path("configs/x.yaml"))

    conn = sqlite3.connect(db)
    rows = list(conn.execute("SELECT run_id FROM runs"))
    conn.close()
    assert rows == []  # no insert when metrics is None


def test_persist_run_result_adds_missing_column_and_retries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lab").mkdir()
    db = tmp_path / "lab" / "runs.sqlite"
    conn = sqlite3.connect(db)
    # Pre-create table WITHOUT the synthetic_loss column — _persist_run_result
    # must ALTER + retry.
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT, "
        "config_path TEXT)"
    )
    conn.commit()
    conn.close()

    result = RunResult(
        ok=True,
        metrics={"synthetic_loss": 0.42},
        elapsed_s=1.2,
        git_commit=None,
    )
    _persist_run_result(result, "run-x", Path("configs/x.yaml"))

    conn = sqlite3.connect(db)
    rows = list(conn.execute("SELECT run_id, synthetic_loss FROM runs"))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
    conn.close()
    assert rows == [("run-x", 0.42)]
    assert "synthetic_loss" in cols
