"""Executor agent: pops a proposal, builds a config, runs auto_qml.run, logs.

No Anthropic call. Pure mechanical step. Resilient to crashes — if auto_qml.run
raises, we capture the traceback, mark the proposal as failed in the notebook,
and move on. The Researcher will see the failure in its next call and adjust.
"""
from __future__ import annotations

import copy
import time
import traceback
from pathlib import Path
from typing import Any

import yaml

from efferents.agents.state import LabPaths, notebook_append, now_iso

# TODO(framework): this import couples the executor to one specific lab's
# CLI. The framework's executor should subprocess out a lab-configured
# command (lab.EXECUTOR_COMMAND or similar) and parse its result, not
# import a lab module directly. See CLAUDE.md "Coder path scope" /
# "executor refactor" for the decoupling plan. Runtime invocation will
# fail until the framework either (a) imports the lab-provided
# `run_from_config(config: dict) -> list[dict]` via a config-loaded
# module, or (b) refactors the executor to subprocess instead.
from auto_qml.run import run_from_config  # type: ignore[import-not-found]


DEFAULT_CONFIG_PATH = Path("config/default.yaml")


def load_default_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    with Path(path).open() as f:
        return yaml.safe_load(f)


def apply_overrides(cfg: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Apply dotted-path overrides ('augmentation.aug_depth' -> 4) to a nested dict."""
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
    name = proposal.get("name", "unnamed")
    overrides = dict(proposal.get("config_overrides", {}) or {})
    if proposal.get("campaign_id"):
        overrides["run.campaign_id"] = proposal["campaign_id"]
    if proposal.get("mode"):
        overrides["run.researcher_mode"] = proposal["mode"]
    if proposal.get("student_id"):
        overrides["run.student_id"] = proposal["student_id"]
    base = base_config or load_default_config()
    cfg = apply_overrides(base, overrides)

    # Stamp the run name + notes for traceability.
    cfg.setdefault("run", {})["name"] = name
    cfg.setdefault("logging", {})["notes"] = (
        (cfg["logging"].get("notes") or "") + f" | hypothesis: {proposal.get('hypothesis', '')}"
    ).strip(" |")

    lit_context = proposal.get("lit_context") or []
    if not isinstance(lit_context, list):
        lit_context = []

    started = now_iso()
    t0 = time.monotonic()
    try:
        rows = run_from_config(
            cfg,
            config_path=f"<proposal:{name}>",
            lit_context=lit_context,
        )
        duration = time.monotonic() - t0
        notebook_append(
            paths.notebook,
            _format_outcome(
                name=name,
                hypothesis=proposal.get("hypothesis", ""),
                expected=proposal.get("expected", ""),
                overrides=overrides,
                rows=rows,
                duration=duration,
                started=started,
            ),
        )
        return {"ok": True, "name": name, "rows": rows, "duration_seconds": duration}
    except Exception as e:
        tb = traceback.format_exc(limit=8)
        duration = time.monotonic() - t0
        notebook_append(
            paths.notebook,
            f"## {started} — RUN FAILED: {name}\n\n"
            f"**Hypothesis**: {proposal.get('hypothesis', '')}\n\n"
            f"**Overrides**: `{overrides}`\n\n"
            f"**Error**: `{type(e).__name__}: {e}`\n\n"
            f"```\n{tb}\n```\n",
        )
        return {"ok": False, "name": name, "error": str(e), "traceback": tb, "duration_seconds": duration}


def _format_outcome(
    *,
    name: str,
    hypothesis: str,
    expected: str,
    overrides: dict[str, Any],
    rows: list[dict[str, Any]],
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
        "| model | eval_kind | val_x0_mse | E_w1 | radial_l2_log | active_frac_w1 | amp_ratio |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        amp = r.get("gen_max_to_real_max")
        # Re-calibrated 2026-05-25 after May-10 recipe validation:
        # true wallpaper sits at amp ≈ 0.001–0.005; healthy sparse-but-dim
        # output (e.g. May-10 QFM at raw_q=64) sits at amp ≈ 0.05–0.25.
        # < 0.02 → wallpaper, 0.02–0.04 → DIM (probably bad), >= 0.04 → healthy.
        amp_str = "N/A" if amp is None else (
            f"**{amp:.3g}⚠WALLPAPER**" if amp < 0.02 else
            f"**{amp:.3g} DIM**" if amp < 0.04 else f"{amp:.3g}"
        )
        lines.append(
            "| {model} | {eval_kind} | {v:.4g} | {e:.4g} | {l:.4g} | {a:.4g} | {amp} |".format(
                model=r["model"],
                eval_kind=r["eval_kind"],
                v=r["val_x0_mse"] if r["val_x0_mse"] is not None else float("nan"),
                e=r["E_w1"],
                l=r["radial_l2_log"],
                a=r["active_frac_w1"],
                amp=amp_str,
            )
        )
    return "\n".join(lines)
