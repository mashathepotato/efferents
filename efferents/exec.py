"""Subprocess execution + stdout-JSON result contract.

Phase A's `run_command` wrote rows directly to SQLite. The new contract is:
the run command's last action is to emit a single JSON line to stdout
containing run_id, metrics, optional artifacts, optional elapsed_s,
optional git_commit. A lab may additionally emit ``observations`` for paired
arms, evaluation slices, or other subsidiary measurements. The daemon parses
that envelope and writes the primary row while preserving the full observation
set as structured JSON.
This decouples the run from the daemon's filesystem.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
import re
import signal
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
    observations: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    git_commit: str | None = None
    elapsed_s: float | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    return_code: int | None = None


_SAFE_BASE_ENV = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL",
    "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL",
    "VIRTUAL_ENV", "PYTHONPATH", "DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH",
)
_COL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _subprocess_env(env_passthrough: tuple[str, ...]) -> dict[str, str]:
    """Build the environment for lab-owned commands.

    The daemon may hold API keys and notification credentials. Those are not
    experiment inputs, so only a small runtime baseline plus explicitly named
    variables is inherited.
    """
    names = set(_SAFE_BASE_ENV) | set(env_passthrough)
    return {name: os.environ[name] for name in names if name in os.environ}


def _validated_metrics(raw: object) -> tuple[dict[str, float | int] | None, str | None]:
    if not isinstance(raw, dict) or not raw:
        return None, "JSON result must contain a non-empty 'metrics' mapping"
    metrics: dict[str, float | int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _COL_NAME_RE.fullmatch(key):
            return None, f"invalid metric name: {key!r}"
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
        ):
            return None, f"metric {key!r} must be a finite number"
        metrics[key] = value
    return metrics, None


def _validated_observations(raw: object) -> tuple[list[dict] | None, str | None]:
    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return None, "'observations' must be a list"
    observations: list[dict] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return None, f"observations[{i}] must be an object"
        metrics, error = _validated_metrics(item.get("metrics"))
        if error is not None:
            return None, f"observations[{i}]: {error}"
        dimensions = item.get("dimensions") or {}
        if not isinstance(dimensions, dict):
            return None, f"observations[{i}].dimensions must be an object"
        for key, value in dimensions.items():
            if not isinstance(key, str) or not _COL_NAME_RE.fullmatch(key):
                return None, f"observations[{i}] has invalid dimension name {key!r}"
            if value is not None and (
                isinstance(value, (dict, list))
                or not isinstance(value, (str, int, float, bool))
            ):
                return None, (
                    f"observations[{i}].dimensions[{key!r}] must be a scalar"
                )
        observations.append({
            "name": item.get("name"),
            "dimensions": dimensions,
            "metrics": metrics,
            "artifacts": list(item.get("artifacts") or []),
        })
    return observations, None


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
    env = _subprocess_env(env_passthrough)
    try:
        proc = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=cwd, env=env, start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        stdout, stderr = proc.communicate()
        return RunResult(
            ok=False,
            stdout=stdout or (
                (e.stdout or "") if isinstance(e.stdout, str) else ""
            ),
            stderr=stderr or (
                (e.stderr or "") if isinstance(e.stderr, str) else ""
            ),
            error=f"timeout after {timeout_s}s",
            return_code=proc.returncode,
        )

    last_json = _extract_trailing_json(stdout)
    if last_json is None:
        return RunResult(
            ok=False,
            stdout=stdout, stderr=stderr,
            error=(
                "run_command did not emit a JSON result on stdout"
                if proc.returncode == 0
                else f"run_command exited with status {proc.returncode} and emitted no JSON result"
            ),
            return_code=proc.returncode,
        )

    metrics, metric_error = _validated_metrics(last_json.get("metrics"))
    observations, observation_error = _validated_observations(
        last_json.get("observations")
    )
    contract_error = metric_error or observation_error
    ok = proc.returncode == 0 and contract_error is None
    return RunResult(
        ok=ok,
        metrics=metrics,
        observations=observations or [],
        artifacts=list(last_json.get("artifacts") or []),
        git_commit=last_json.get("git_commit"),
        elapsed_s=last_json.get("elapsed_s"),
        stdout=stdout,
        stderr=stderr,
        error=(
            contract_error
            if contract_error is not None
            else (f"run_command exited with status {proc.returncode}" if proc.returncode else None)
        ),
        return_code=proc.returncode,
    )


def _execute_run(config_path: Path, *, smoke: bool = False) -> RunResult:
    """Render the lab's run_command and execute it, parsing stdout JSON."""
    cfg = _lab.get_config()
    template = (
        cfg.executor.smoke_command
        if smoke and cfg.executor.smoke_command
        else cfg.executor.run_command
    )
    cmd = template.format(config_path=str(config_path))
    return _run_and_capture(
        cmd,
        timeout_s=(
            cfg.executor.smoke_timeout_s if smoke else cfg.executor.run_timeout_s
        ),
        cwd=str(cfg.source.dir),
        env_passthrough=cfg.executor.env_passthrough,
    )


def _persist_run_result(
    result: RunResult,
    run_id: str,
    config_path: Path,
    *,
    db_path: Path | None = None,
    proposal: dict | None = None,
    config_yaml: str | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    duration_seconds: float | None = None,
    started_at: str | None = None,
    seed: int | None = None,
) -> None:
    """Insert a row into lab/runs.sqlite from a RunResult.

    Every attempt gets a row. Failed-run metrics are retained in
    ``raw_metrics_json`` for diagnosis but are not copied into scored metric
    columns, so they cannot become a downstream "best run".
    """
    db_path = Path(db_path) if db_path is not None else Path("lab/runs.sqlite")
    proposal = proposal or {}
    cols = [
        "run_id", "started_at", "ended_at", "config_path",
        "campaign_id", "researcher_mode", "student_id", "status",
        "exit_code", "error", "stdout_path", "stderr_path",
        "config_yaml", "config_hash", "artifacts_json", "raw_metrics_json",
        "observations_json",
        "seed",
    ]
    now = datetime.now(timezone.utc).isoformat()
    config_hash = (
        "sha256:" + hashlib.sha256(config_yaml.encode()).hexdigest()
        if config_yaml is not None
        else None
    )
    vals: list = [
        run_id,
        started_at or now,
        now,
        str(config_path),
        proposal.get("campaign_id"),
        proposal.get("mode"),
        proposal.get("student_id") or "primary",
        "succeeded" if result.ok else "failed",
        result.return_code,
        result.error,
        str(stdout_path) if stdout_path else None,
        str(stderr_path) if stderr_path else None,
        config_yaml,
        config_hash,
        json.dumps(result.artifacts),
        json.dumps(result.metrics or {}),
        json.dumps(result.observations),
        seed,
    ]
    if result.ok:
        for key, value in (result.metrics or {}).items():
            if not _COL_NAME_RE.fullmatch(key):
                raise ValueError(f"unsafe metric column name: {key!r}")
            cols.append(key)
            vals.append(value)
    if result.git_commit:
        cols.append("git_commit")
        vals.append(result.git_commit)
    elapsed = duration_seconds if duration_seconds is not None else result.elapsed_s
    if elapsed is not None:
        cols.append("duration_seconds")
        vals.append(elapsed)

    placeholders = ",".join("?" for _ in vals)
    col_list = ",".join(f'"{col}"' for col in cols)
    sql = f"INSERT INTO runs ({col_list}) VALUES ({placeholders})"

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        # WAL lets the dashboard read while a run row is being written; without
        # it a lock collision here silently drops the row after compute is spent.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
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
            metadata_types = {
                "campaign_id": "TEXT", "researcher_mode": "TEXT",
                "student_id": "TEXT", "status": "TEXT",
                "exit_code": "INTEGER", "error": "TEXT",
                "stdout_path": "TEXT", "stderr_path": "TEXT",
                "config_yaml": "TEXT", "config_hash": "TEXT",
                "artifacts_json": "TEXT", "raw_metrics_json": "TEXT",
                "observations_json": "TEXT",
                "seed": "INTEGER", "git_commit": "TEXT",
                "duration_seconds": "REAL",
            }
            for col in cols:
                if col not in existing:
                    try:
                        if not _COL_NAME_RE.fullmatch(col):
                            raise ValueError(f"unsafe column name: {col!r}")
                        sql_type = metadata_types.get(col, "REAL")
                        conn.execute(
                            f'ALTER TABLE runs ADD COLUMN "{col}" {sql_type}'
                        )
                    except sqlite3.OperationalError as alter_err:
                        print(f"warning: could not add column {col}: {alter_err}")
                        return
            try:
                conn.execute(sql, vals)
                conn.commit()
            except sqlite3.OperationalError as retry_err:
                print(f"warning: persist retry failed: {retry_err}")
