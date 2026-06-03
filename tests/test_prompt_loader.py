"""load_prompt renders framework or lab-override prompts via str.format."""
from __future__ import annotations
from pathlib import Path

import pytest

from efferents.agents.prompts.loader import (
    load_prompt, PromptRenderError, _render_vars, _format_panel_block,
)
from efferents.lab import (
    Budget, Executor, Headline, LabConfig, Metrics, Panel, Source,
)
from efferents import lab as lab_mod


def _install(tmp_path, *, prompts_dir=None, headline="synthetic_loss",
             panels=(("synthetic_loss", "Loss", None),)):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "c.yaml").touch()
    cfg = LabConfig(
        lab_id="smoke", domain="synthetic", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command="python3 -m src.run --config {config_path}",
            smoke_command="python3 -m src.run --config {config_path} --smoke",
            config_template=src / "c.yaml",
        ),
        metrics=Metrics(
            headline=Headline(column=headline, direction="min"),
            panels=tuple(Panel(column=c, label=l, target=t) for c, l, t in panels),
        ),
        budget=Budget(),
        prompts_dir=prompts_dir,
    )
    lab_mod.set_config(cfg)
    return cfg


def test_render_vars_exposes_core_fields(tmp_path):
    cfg = _install(tmp_path)
    v = _render_vars(cfg)
    assert v["lab_id"] == "smoke"
    assert v["domain"] == "synthetic"
    assert v["headline_metric"] == "synthetic_loss"
    assert v["headline_direction"] == "min"
    assert v["source_dir"] == str(cfg.source.dir)
    assert "{config_path}" in v["run_command"]


def test_render_vars_extras_merge(tmp_path):
    cfg = _install(tmp_path)
    v = _render_vars(cfg, {"hypothesis_body": "X causes Y"})
    assert v["hypothesis_body"] == "X causes Y"


def test_panel_block_empty(tmp_path):
    cfg = _install(tmp_path, panels=())
    v = _render_vars(cfg)
    assert v["panel_metrics"] == "(none)"
    assert "(none)" in v["panel_metrics_block"]


def test_load_framework_prompt_substitutes(tmp_path):
    cfg = _install(tmp_path, prompts_dir=tmp_path / "prompts")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "demo.md").write_text(
        "Lab {lab_id} optimizes {headline_metric} ({headline_direction})."
    )
    out = load_prompt("demo")
    assert out == "Lab smoke optimizes synthetic_loss (min)."


def test_override_takes_precedence_over_framework(tmp_path):
    cfg = _install(tmp_path, prompts_dir=tmp_path / "prompts")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "analyst.md").write_text("OVERRIDE {lab_id}")
    out = load_prompt("analyst")
    assert out == "OVERRIDE smoke"


def test_missing_override_falls_back_to_framework(tmp_path):
    cfg = _install(tmp_path, prompts_dir=tmp_path / "prompts")
    (tmp_path / "prompts").mkdir()
    out = load_prompt("analyst")  # framework analyst.md exists, 0 braces today
    assert len(out) > 0
    assert "OVERRIDE" not in out


def test_undefined_variable_raises_prompt_render_error(tmp_path):
    cfg = _install(tmp_path, prompts_dir=tmp_path / "prompts")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "demo.md").write_text("uses {bogus_var}")
    with pytest.raises(PromptRenderError, match="bogus_var"):
        load_prompt("demo")


def test_explicit_override_path_wins(tmp_path):
    cfg = _install(tmp_path)
    explicit = tmp_path / "explicit_student.md"
    explicit.write_text("EXPLICIT {lab_id}")
    out = load_prompt("student", override_path=explicit)
    assert out == "EXPLICIT smoke"
