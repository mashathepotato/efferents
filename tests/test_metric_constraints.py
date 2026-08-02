from __future__ import annotations

from pathlib import Path

from efferents import lab as lab_mod
from efferents.lab import (
    Budget,
    Constraint,
    Executor,
    Headline,
    LabConfig,
    Metrics,
    Source,
)
from efferents.metrics_view import best_run, constraint_failures, eligible


def _configure(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config = source / "config.yaml"
    config.write_text("{}\n")
    lab_mod.set_config(LabConfig(
        lab_id="constraint-test",
        domain="synthetic",
        pi_handle=None,
        source=Source(dir=source),
        executor=Executor(
            run_command="echo {config_path}",
            smoke_command=None,
            config_template=config,
        ),
        metrics=Metrics(
            headline=Headline(column="loss", direction="min"),
            panels=(),
            constraints=(
                Constraint(column="amplitude", op=">=", value=0.04),
                Constraint(column="spread", op="<=", value=1.8),
            ),
        ),
        budget=Budget(),
    ))


def test_invalid_low_loss_cannot_become_best(tmp_path):
    _configure(tmp_path)
    collapsed = {"loss": 0.01, "amplitude": 0.001, "spread": 1.0}
    valid = {"loss": 0.2, "amplitude": 0.1, "spread": 1.2}

    assert eligible(collapsed) is False
    assert "amplitude" in constraint_failures(collapsed)[0]
    assert best_run([collapsed, valid]) == valid


def test_missing_constraint_metric_is_ineligible(tmp_path):
    _configure(tmp_path)
    failures = constraint_failures({"loss": 0.2, "amplitude": 0.1})
    assert failures == ["spread: missing (requires <= 1.8)"]
