"""LabConfig construction and defaults."""
from __future__ import annotations
import dataclasses
from pathlib import Path

import pytest

from efferents.lab import (
    Budget, Executor, Headline, LabConfig, Metrics, Panel, Source, SubmissionError,
)


def test_labconfig_construction_with_defaults():
    cfg = LabConfig(
        lab_id="test-lab",
        domain="test-domain",
        pi_handle=None,
        source=Source(dir=Path("/tmp")),
        executor=Executor(
            run_command="python -m test --config {config_path}",
            smoke_command=None,
            config_template=Path("configs/default.yaml"),
        ),
        metrics=Metrics(
            headline=Headline(column="loss", direction="min"),
            panels=(Panel(column="loss", label="Loss"),),
        ),
        budget=Budget(),
    )
    assert cfg.lab_id == "test-lab"
    assert cfg.budget.daily_cap_usd == 10.0
    assert cfg.budget.sonnet_default is True
    assert cfg.metrics.flat_digest_epsilon == 0.005
    assert cfg.executor.run_timeout_s == 7200
    assert cfg.executor.smoke_timeout_s == 300
    assert cfg.executor.env_passthrough == ()
    assert cfg.source.allowed_patterns == ("**/*.py",)
    assert cfg.peer_review_enabled is False
    assert len(cfg.students) == 1
    assert cfg.students[0]["id"] == "primary"


def test_labconfig_frozen():
    cfg = LabConfig(
        lab_id="t", domain="d", pi_handle=None,
        source=Source(dir=Path("/tmp")),
        executor=Executor(run_command="x {config_path}", smoke_command=None, config_template=Path("c.yaml")),
        metrics=Metrics(headline=Headline(column="m", direction="min"), panels=()),
        budget=Budget(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.lab_id = "different"  # type: ignore[misc]


def test_submission_error_is_value_error():
    assert issubclass(SubmissionError, ValueError)
    with pytest.raises(ValueError, match="bad submission"):
        raise SubmissionError("bad submission")


def test_headline_direction_max():
    h = Headline(column="accuracy", direction="max")
    assert h.direction == "max"
    cfg = LabConfig(
        lab_id="t", domain="d", pi_handle=None,
        source=Source(dir=Path("/tmp")),
        executor=Executor(run_command="x {config_path}", smoke_command=None, config_template=Path("c.yaml")),
        metrics=Metrics(headline=h, panels=()),
        budget=Budget(),
    )
    assert cfg.metrics.headline.direction == "max"
