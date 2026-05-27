"""Coder's target globs, new-file regex, and smoke command read from LabConfig."""
from __future__ import annotations
import re
from pathlib import Path

from efferents.agents import coder
from efferents.lab import (
    Budget, Executor, Headline, LabConfig, Metrics, Panel, Source,
)
from efferents import lab as lab_mod


def _install(tmp_path: Path, source_subdir: str = "my_research", allowed=("**/*.py",)):
    src = tmp_path / source_subdir
    src.mkdir()
    (src / "default.yaml").touch()
    cfg = LabConfig(
        lab_id="x", domain="y", pi_handle=None,
        source=Source(dir=src, allowed_patterns=allowed),
        executor=Executor(
            run_command=f"python -m {source_subdir}.run --config {{config_path}}",
            smoke_command=f"python -m {source_subdir}.run --config {{config_path}} --smoke",
            config_template=src / "default.yaml",
        ),
        metrics=Metrics(headline=Headline(column="m", direction="min"), panels=()),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    return cfg


def test_target_globs_use_source_dir(tmp_path):
    _install(tmp_path)
    globs = coder._target_globs()
    src_abs = str((tmp_path / "my_research").resolve())
    assert any(src_abs in g for g in globs)
    # config_template is also in target globs
    assert any("default.yaml" in g for g in globs)


def test_new_file_path_re_uses_source_dir(tmp_path):
    _install(tmp_path)
    pattern = coder._new_file_path_re()
    src_abs = str((tmp_path / "my_research").resolve())
    assert pattern.match(f"{src_abs}/foo.py")
    assert not pattern.match(f"{src_abs}/sub/foo.py")  # no nested dirs
    assert not pattern.match("auto_qml/foo.py")  # legacy path no longer matches


def test_smoke_command_renders_config_path(tmp_path):
    _install(tmp_path)
    cmd = coder._smoke_command(Path("/some/config.yaml"))
    assert "{config_path}" not in cmd
    assert "/some/config.yaml" in cmd
    assert "--smoke" in cmd


def test_smoke_command_falls_back_to_run_command(tmp_path):
    src = tmp_path / "r"
    src.mkdir()
    (src / "c.yaml").touch()
    cfg = LabConfig(
        lab_id="x", domain="y", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command="python -m r.run --config {config_path}",
            smoke_command=None,  # no smoke variant
            config_template=src / "c.yaml",
        ),
        metrics=Metrics(headline=Headline(column="m", direction="min"), panels=()),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    cmd = coder._smoke_command(Path("/some/config.yaml"))
    assert "--smoke" not in cmd
    assert "/some/config.yaml" in cmd
