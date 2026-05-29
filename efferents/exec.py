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
import subprocess
from dataclasses import dataclass, field


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
