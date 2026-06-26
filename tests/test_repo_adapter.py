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


def test_example_sweep_parsed():
    cfg = RepoAdapterConfig.load(EXAMPLE)
    assert cfg.sweep is not None
    assert cfg.sweep.param == "threshold"
    assert cfg.sweep.values == (0.30, 0.50, 0.65, 0.80, 0.90)
    assert cfg.config_template == "configs/base.yaml"


def test_sweep_requires_config_path_placeholder():
    with pytest.raises(AdapterConfigError):
        RepoAdapterConfig.from_dict({
            "goal": "g", "train_command": "train.py",  # no {config_path}
            "eval_command": "eval --checkpoint {checkpoint}", "metric": "m",
            "sweep": {"param": "lr", "values": [0.1, 0.2]},
        })


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
