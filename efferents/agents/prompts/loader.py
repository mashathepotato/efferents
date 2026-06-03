"""Prompt loader: renders a framework or lab-override prompt via str.format.

Resolution order for `load_prompt(name)`:
  1. explicit `override_path` argument (used by the Researcher's per-student
     prompt override), if it exists
  2. `<submission>/prompts/<name>.md` from LabConfig.prompts_dir, if present
  3. the framework default at efferents/agents/prompts/<name>.md

The chosen file is rendered with a LabConfig-derived variable dict plus any
per-call `extras`. Literal braces in prompt prose must be escaped `{{`/`}}`.
"""
from __future__ import annotations

from pathlib import Path

from efferents import lab as _lab

FRAMEWORK_PROMPTS_DIR = Path(__file__).parent


class PromptRenderError(RuntimeError):
    """A prompt referenced a variable not in the render context, or failed to format."""


def _format_panel_block(panels) -> str:
    """A small markdown table of the lab's panel metrics, or '(none)'."""
    if not panels:
        return "(none)"
    lines = ["| metric | label | target |", "|---|---|---|"]
    for p in panels:
        target = "—" if p.target is None else str(p.target)
        lines.append(f"| {p.column} | {p.label} | {target} |")
    return "\n".join(lines)


def _render_vars(cfg, extras: dict | None = None) -> dict:
    panels = cfg.metrics.panels
    base = {
        "lab_id": cfg.lab_id,
        "domain": cfg.domain,
        "pi_handle": cfg.pi_handle or "(anonymous)",
        "source_dir": str(cfg.source.dir),
        "run_command": cfg.executor.run_command,
        "smoke_command": cfg.executor.smoke_command or cfg.executor.run_command,
        "config_template": str(cfg.executor.config_template),
        "headline_metric": cfg.metrics.headline.column,
        "headline_direction": cfg.metrics.headline.direction,
        "panel_metrics": ", ".join(p.column for p in panels) or "(none)",
        "panel_metrics_block": _format_panel_block(panels),
    }
    if extras:
        base.update(extras)
    return base


def load_prompt(name: str, *, extras: dict | None = None,
                override_path: Path | None = None) -> str:
    cfg = _lab.get_config()
    if override_path is not None and Path(override_path).is_file():
        raw = Path(override_path).read_text()
    else:
        lab_override = (cfg.prompts_dir / f"{name}.md") if cfg.prompts_dir else None
        if lab_override and lab_override.is_file():
            raw = lab_override.read_text()
        else:
            raw = (FRAMEWORK_PROMPTS_DIR / f"{name}.md").read_text()
    try:
        return raw.format(**_render_vars(cfg, extras))
    except KeyError as e:
        raise PromptRenderError(
            f"prompt {name!r} references undefined variable {e.args[0]!r}"
        ) from e
    except (IndexError, ValueError) as e:
        raise PromptRenderError(
            f"prompt {name!r} failed to render (likely an unescaped '{{' or '}}'): {e}"
        ) from e
