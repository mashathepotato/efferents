"""The repo adapter config (efferents.yaml) loader."""
from pathlib import Path

import pytest

from efferents.repo_adapter import AdapterConfigError, RepoAdapterConfig

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "repo-adapter"


def test_example_efferents_yaml_loads():
    cfg = RepoAdapterConfig.load(EXAMPLE)
    assert cfg.metric == "val_f1"
    assert cfg.maximize is True
    assert cfg.budget.max_gpu_hours == 2
    assert cfg.approval_mode == "plan_then_execute"
    assert "{checkpoint}" in cfg.eval_command
    assert cfg.outputs.runs_file == "runs.jsonl"


def test_missing_required_field_raises():
    with pytest.raises(AdapterConfigError):
        RepoAdapterConfig.from_dict({"goal": "x"})


def test_eval_command_must_have_checkpoint_placeholder():
    with pytest.raises(AdapterConfigError):
        RepoAdapterConfig.from_dict({
            "goal": "g", "train_command": "t", "eval_command": "eval.py",
            "metric": "m",
        })


def test_bad_approval_mode_raises():
    with pytest.raises(AdapterConfigError):
        RepoAdapterConfig.from_dict({
            "goal": "g", "train_command": "t",
            "eval_command": "eval --checkpoint {checkpoint}", "metric": "m",
            "approval": {"mode": "yolo"},
        })
