"""Loader for the buyer-facing repo adapter config (`efferents.yaml`).

This is the "point efferents at your existing ML repo" front door: a single
`efferents.yaml` at a repo root describing how to train, how to evaluate, which
metric to move, and the budget/approval guardrails. It is intentionally simpler
than the lower-level `lab.yaml` (see `efferents/lab.py`) and maps onto it.

Minimal on purpose — enough to load, validate, and drive a bounded loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class AdapterConfigError(ValueError):
    """Raised when an efferents.yaml repo adapter config is invalid."""


@dataclass(frozen=True)
class Budget:
    max_gpu_hours: float | None = None
    max_llm_cost_usd: float | None = None


@dataclass(frozen=True)
class Outputs:
    journal_dir: str = "journal"
    runs_file: str = "runs.jsonl"
    claims_file: str = "claims.jsonl"


@dataclass(frozen=True)
class Sweep:
    param: str
    values: tuple[float | int | str, ...]


@dataclass(frozen=True)
class ChartSpec:
    """One lab-declared dashboard panel, rendered by the shared chart runtime
    (`efferents/dashboard/static/charts.js`). `metric` may be any numeric
    field a run record logs; `type` is any registered chart type."""

    metric: str
    x: str | None = None
    x_label: str | None = None
    type: str = "line"
    label: str | None = None
    target: float | None = None
    target_label: str | None = None
    maximize: bool | None = None


@dataclass(frozen=True)
class RepoAdapterConfig:
    goal: str
    train_command: str
    eval_command: str
    metric: str
    maximize: bool
    budget: Budget
    approval_mode: str
    outputs: Outputs
    config_template: str | None = None
    sweep: Sweep | None = None
    charts: tuple[ChartSpec, ...] = ()

    @classmethod
    def load(cls, path: Path | str) -> "RepoAdapterConfig":
        path = Path(path)
        if path.is_dir():
            path = path / "efferents.yaml"
        if not path.is_file():
            raise AdapterConfigError(f"efferents.yaml not found at {path}")
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as e:
            raise AdapterConfigError(f"efferents.yaml is not valid YAML: {e}") from e
        if not isinstance(raw, dict):
            raise AdapterConfigError("efferents.yaml must be a mapping at top level")
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "RepoAdapterConfig":
        for key in ("goal", "train_command", "eval_command", "metric"):
            if not raw.get(key):
                raise AdapterConfigError(f"efferents.yaml: '{key}' is required")
        if "{checkpoint}" not in raw["eval_command"]:
            raise AdapterConfigError(
                "eval_command must contain the {checkpoint} placeholder"
            )

        sweep_raw = raw.get("sweep")
        sweep = None
        if sweep_raw is not None:
            if not isinstance(sweep_raw, dict) or not sweep_raw.get("param"):
                raise AdapterConfigError("sweep must have a 'param' field")
            values = sweep_raw.get("values")
            if not isinstance(values, list) or not values:
                raise AdapterConfigError("sweep.values must be a non-empty list")
            sweep = Sweep(param=sweep_raw["param"], values=tuple(values))

        config_template = raw.get("config_template")
        if sweep is not None and "{config_path}" not in raw["train_command"]:
            raise AdapterConfigError(
                "train_command must contain {config_path} when a sweep is configured"
            )

        charts_raw = raw.get("charts") or []
        if not isinstance(charts_raw, list):
            raise AdapterConfigError("charts must be a list of chart mappings")
        charts = []
        for entry in charts_raw:
            if not isinstance(entry, dict) or not entry.get("metric"):
                raise AdapterConfigError("each charts entry needs a 'metric'")
            charts.append(ChartSpec(
                metric=entry["metric"],
                x=entry.get("x"),
                x_label=entry.get("x_label"),
                type=entry.get("type", "line"),
                label=entry.get("label"),
                target=_opt_float(entry.get("target")),
                target_label=entry.get("target_label"),
                maximize=(None if entry.get("maximize") is None
                          else bool(entry["maximize"])),
            ))

        budget_raw = raw.get("budget") or {}
        approval_raw = raw.get("approval") or {}
        mode = approval_raw.get("mode", "plan_then_execute")
        if mode not in ("plan_then_execute", "dry_run", "autonomous"):
            raise AdapterConfigError(
                f"approval.mode must be plan_then_execute | dry_run | autonomous; got {mode!r}"
            )
        out_raw = raw.get("outputs") or {}
        return cls(
            goal=raw["goal"],
            train_command=raw["train_command"],
            eval_command=raw["eval_command"],
            metric=raw["metric"],
            maximize=bool(raw.get("maximize", True)),
            budget=Budget(
                max_gpu_hours=_opt_float(budget_raw.get("max_gpu_hours")),
                max_llm_cost_usd=_opt_float(budget_raw.get("max_llm_cost_usd")),
            ),
            approval_mode=mode,
            outputs=Outputs(
                journal_dir=out_raw.get("journal_dir", "journal"),
                runs_file=out_raw.get("runs_file", "runs.jsonl"),
                claims_file=out_raw.get("claims_file", "claims.jsonl"),
            ),
            config_template=config_template,
            sweep=sweep,
            charts=tuple(charts),
        )


def _opt_float(v) -> float | None:
    return None if v is None else float(v)
