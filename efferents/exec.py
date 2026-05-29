"""Subprocess execution + stdout-JSON result contract.

Phase A's `run_command` wrote rows directly to SQLite. The new contract is:
the run command's last action is to emit a single JSON line to stdout
containing run_id, metrics, optional artifacts, optional elapsed_s,
optional git_commit. The daemon parses that line and writes the row.
This decouples the run from the daemon's filesystem.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from efferents import lab as _lab


@dataclass
class RunResult:
    ok: bool
    metrics: dict | None = None
    artifacts: list[dict] = field(default_factory=list)
    git_commit: str | None = None
    elapsed_s: float | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


def _extract_trailing_json(text: str) -> dict | None:
    """Return the LAST top-level JSON object found in `text`, or None.

    Scans from the end of the string, finding balanced { ... } regions.
    Tolerates inner braces (nested objects). Returns None if no valid
    JSON object is found.
    """
    if not text:
        return None
    depth = 0
    end = -1
    candidates: list[tuple[int, int]] = []  # (start, end+1)
    for i in range(len(text) - 1, -1, -1):
        c = text[i]
        if c == "}":
            if depth == 0:
                end = i
            depth += 1
        elif c == "{":
            depth -= 1
            if depth == 0 and end != -1:
                candidates.append((i, end + 1))
                end = -1
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[1], reverse=True)
    for start, stop in candidates:
        chunk = text[start:stop]
        try:
            obj = json.loads(chunk)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _run_and_capture(
    cmd: str,
    *,
    timeout_s: int,
    cwd: str,
    env_passthrough: tuple[str, ...],
) -> RunResult:
    """Execute `cmd` in `cwd` with selected env vars passed through.
    Capture stdout, parse the last JSON object, return RunResult."""
    env = dict(os.environ)
    for k in env_passthrough:
        if k in os.environ:
            env[k] = os.environ[k]
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout_s, cwd=cwd, env=env,
        )
    except subprocess.TimeoutExpired as e:
        return RunResult(
            ok=False,
            stdout=(e.stdout or "") if isinstance(e.stdout, str) else "",
            stderr=(e.stderr or "") if isinstance(e.stderr, str) else "",
            error=f"timeout after {timeout_s}s",
        )

    last_json = _extract_trailing_json(proc.stdout)
    if last_json is None:
        return RunResult(
            ok=False,
            stdout=proc.stdout, stderr=proc.stderr,
            error="run_command did not emit a JSON result on stdout",
        )

    return RunResult(
        ok=proc.returncode == 0,
        metrics=last_json.get("metrics"),
        artifacts=list(last_json.get("artifacts") or []),
        git_commit=last_json.get("git_commit"),
        elapsed_s=last_json.get("elapsed_s"),
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _execute_run(config_path: Path) -> RunResult:
    """Render the lab's run_command and execute it, parsing stdout JSON."""
    cfg = _lab.get_config()
    cmd = cfg.executor.run_command.format(config_path=str(config_path))
    return _run_and_capture(
        cmd,
        timeout_s=cfg.executor.run_timeout_s,
        cwd=str(cfg.source.dir),
        env_passthrough=cfg.executor.env_passthrough,
    )


def _persist_run_result(result: RunResult, run_id: str, config_path: Path) -> None:
    """Insert a row into lab/runs.sqlite from a RunResult.

    Skips when result.metrics is None (failed run with no parseable metrics).
    If a metric column doesn't exist, ALTER TABLE to add it and retry once.
    """
    if not result.metrics:
        return
    db_path = Path("lab/runs.sqlite")
    cols = ["run_id", "started_at", "ended_at", "config_path"]
    now = datetime.now(timezone.utc).isoformat()
    vals: list = [run_id, now, now, str(config_path)]
    for k, v in result.metrics.items():
        cols.append(k)
        vals.append(v)
    if result.git_commit:
        cols.append("git_commit")
        vals.append(result.git_commit)
    if result.elapsed_s is not None:
        cols.append("duration_seconds")
        vals.append(result.elapsed_s)

    placeholders = ",".join("?" for _ in vals)
    col_list = ",".join(cols)
    sql = f"INSERT INTO runs ({col_list}) VALUES ({placeholders})"

    with sqlite3.connect(db_path) as conn:
        try:
            conn.execute(sql, vals)
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            msg = str(e)
            if "no such column" not in msg.lower() and "has no column named" not in msg.lower():
                print(f"warning: could not persist metric row: {e}")
                return
            existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
            for col in cols:
                if col not in existing:
                    try:
                        conn.execute(f"ALTER TABLE runs ADD COLUMN {col} REAL")
                    except sqlite3.OperationalError as alter_err:
                        print(f"warning: could not add column {col}: {alter_err}")
                        return
            try:
                conn.execute(sql, vals)
                conn.commit()
            except sqlite3.OperationalError as retry_err:
                print(f"warning: persist retry failed: {retry_err}")
