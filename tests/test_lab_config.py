"""LabConfig construction and defaults."""
from __future__ import annotations
import dataclasses
from pathlib import Path

import pytest

from efferents.lab import (
    Budget, Executor, Headline, LabConfig, Metrics, Panel, Source, SubmissionError,
)


def test_from_submission_happy_path(tmp_path):
    src = Path(__file__).parent / "fixtures" / "sample_submission"
    import shutil
    sub = tmp_path / "sub"
    shutil.copytree(src, sub)
    cfg = LabConfig.from_submission(sub)
    assert cfg.lab_id == "sample-conjecture"
    assert cfg.domain == "synthetic"
    assert cfg.source.dir.is_absolute()
    assert cfg.source.dir.name == "src"
    assert cfg.executor.run_command == "python -m sample.run --config {config_path}"
    assert cfg.metrics.headline.column == "synthetic_loss"
    assert cfg.metrics.headline.direction == "min"
    assert cfg.budget.daily_cap_usd == 10.0


def test_from_submission_missing_hypothesis(tmp_path):
    (tmp_path / "lab.yaml").write_text("lab_id: x\ndomain: y\n")
    with pytest.raises(SubmissionError, match="hypothesis.md"):
        LabConfig.from_submission(tmp_path)


def test_from_submission_falsifiability_failed(tmp_path):
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: x\nfalsifiability_gate: failed\nstatus: unfalsifiable\n---\n\nbody"
    )
    (tmp_path / "lab.yaml").write_text("lab_id: x\ndomain: y\n")
    with pytest.raises(SubmissionError, match="falsifiability_gate"):
        LabConfig.from_submission(tmp_path)


def test_from_submission_missing_lab_yaml(tmp_path):
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: x\nfalsifiability_gate: passed\nstatus: active\n---\n\nbody"
    )
    with pytest.raises(SubmissionError, match="lab.yaml"):
        LabConfig.from_submission(tmp_path)


def test_from_submission_source_dir_missing(tmp_path):
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: x\nfalsifiability_gate: passed\nstatus: active\n---\n\nbody"
    )
    (tmp_path / "lab.yaml").write_text(
        "lab_id: x\ndomain: y\n"
        "source:\n  dir: ./nonexistent/\n"
        "executor:\n  run_command: 'echo {config_path}'\n  config_template: c.yaml\n"
        "metrics:\n  headline:\n    column: m\n    direction: min\n"
    )
    with pytest.raises(SubmissionError, match="source.dir"):
        LabConfig.from_submission(tmp_path)


def test_from_submission_run_command_missing_placeholder(tmp_path):
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: x\nfalsifiability_gate: passed\nstatus: active\n---\n\nbody"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "c.yaml").touch()
    (tmp_path / "lab.yaml").write_text(
        "lab_id: x\ndomain: y\n"
        "source:\n  dir: ./src/\n"
        "executor:\n  run_command: 'echo no-placeholder'\n  config_template: c.yaml\n"
        "metrics:\n  headline:\n    column: m\n    direction: min\n"
    )
    with pytest.raises(SubmissionError, match=r"\{config_path\}"):
        LabConfig.from_submission(tmp_path)


def test_from_submission_bad_direction(tmp_path):
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: x\nfalsifiability_gate: passed\nstatus: active\n---\n\nbody"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "c.yaml").touch()
    (tmp_path / "lab.yaml").write_text(
        "lab_id: x\ndomain: y\n"
        "source:\n  dir: ./src/\n"
        "executor:\n  run_command: 'echo {config_path}'\n  config_template: c.yaml\n"
        "metrics:\n  headline:\n    column: m\n    direction: maximum\n"
    )
    with pytest.raises(SubmissionError, match="direction"):
        LabConfig.from_submission(tmp_path)


def test_from_submission_lab_id_defaults_to_hypothesis_slug(tmp_path):
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: defaulted-id\nfalsifiability_gate: passed\nstatus: active\n---\n\nbody"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "c.yaml").touch()
    (tmp_path / "lab.yaml").write_text(
        # no lab_id
        "domain: y\n"
        "source:\n  dir: ./src/\n"
        "executor:\n  run_command: 'echo {config_path}'\n  config_template: c.yaml\n"
        "metrics:\n  headline:\n    column: m\n    direction: min\n"
    )
    cfg = LabConfig.from_submission(tmp_path)
    assert cfg.lab_id == "defaulted-id"


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
