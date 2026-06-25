"""Executor agent: render a proposal's config, run it, persist + log.

The execute() signature and return shape are preserved for the
orchestrator's downstream consumers. Internals route through
efferents.exec._execute_run + _persist_run_result, and the notebook
formatter renders dynamic columns from RunResult.metrics — no domain-
specific references survive.
"""
from __future__ import annotations

import copy
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from efferents import lab as _lab
from efferents.agents.state import LabPaths, notebook_append, now_iso
from efferents.exec import _execute_run, _persist_run_result, RunResult


def load_default_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open() as f:
        return yaml.safe_load(f)


def apply_overrides(cfg: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Apply dotted-path overrides ('training.batch_size' -> 64) to a nested dict."""
    out = copy.deepcopy(cfg)
    for path, value in overrides.items():
        keys = path.split(".")
        cursor = out
        for k in keys[:-1]:
            if k not in cursor or not isinstance(cursor[k], dict):
                cursor[k] = {}
            cursor = cursor[k]
        cursor[keys[-1]] = value
    return out


def execute(
    *,
    paths: LabPaths,
    proposal: dict[str, Any],
    base_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one proposal end-to-end. Returns {ok, name, rows | error}."""
    cfg = _lab.get_config()
    name = proposal.get("name", "unnamed")
    overrides = dict(proposal.get("config_overrides", {}) or {})
    if proposal.get("campaign_id"):
        overrides["run.campaign_id"] = proposal["campaign_id"]
    if proposal.get("mode"):
        overrides["run.researcher_mode"] = proposal["mode"]
    if proposal.get("student_id"):
        overrides["run.student_id"] = proposal["student_id"]

    base = base_config or load_default_config(cfg.executor.config_template)
    rendered = apply_overrides(base, overrides)
    rendered.setdefault("run", {})["name"] = name

    run_id = uuid.uuid4().hex
    config_dir = paths.root / "configs"
    config_dir.mkdir(exist_ok=True)
    # Resolve to an absolute path: the run command executes with cwd =
    # source.dir, which is generally NOT the daemon's cwd, so a relative
    # config path would not resolve for the subprocess.
    config_path = (config_dir / f"run_{run_id}.yaml").resolve()
    with config_path.open("w") as f:
        yaml.safe_dump(rendered, f)

    started = now_iso()
    t0 = time.monotonic()
    result = _execute_run(config_path)
    duration = time.monotonic() - t0

    _persist_run_result(result, run_id, config_path)

    notebook_append(
        paths.notebook,
        _format_outcome(
            name=name,
            hypothesis=proposal.get("hypothesis", ""),
            expected=proposal.get("expected", ""),
            overrides=overrides,
            result=result,
            duration=duration,
            started=started,
        ),
    )

    if result.ok:
        row: dict[str, Any] = {"run_id": run_id, "name": name}
        if result.metrics:
            row.update(result.metrics)
        if result.git_commit:
            row["git_commit"] = result.git_commit
        return {"ok": True, "name": name, "rows": [row], "duration_seconds": duration}

    err_tail = (result.stderr or "")[-200:]
    return {
        "ok": False,
        "name": name,
        "error": result.error or err_tail or "run failed",
        "traceback": "",
        "duration_seconds": duration,
    }


def _format_outcome(
    *,
    name: str,
    hypothesis: str,
    expected: str,
    overrides: dict[str, Any],
    result: RunResult,
    duration: float,
    started: str,
) -> str:
    lines = [
        f"## {started} — {name}",
        "",
        f"**Hypothesis**: {hypothesis}",
        "",
        f"**Expected**: {expected}",
        "",
        f"**Overrides**: `{overrides}`",
        "",
        f"**Duration**: {duration:.1f}s",
        "",
    ]
    if result.metrics:
        cols = list(result.metrics.keys())
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join("---" for _ in cols) + "|")

        def _fmt(v: Any) -> str:
            if isinstance(v, float):
                return f"{v:.4g}"
            if isinstance(v, int):
                return str(v)
            return str(v)

        lines.append("| " + " | ".join(_fmt(result.metrics[c]) for c in cols) + " |")
    else:
        lines.append(f"**Error**: {result.error or 'no metrics emitted'}")
        if result.stderr:
            tail = result.stderr[-1024:]
            lines.append("")
            lines.append("```")
            lines.append(tail)
            lines.append("```")
    return "\n".join(lines)
