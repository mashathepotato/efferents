# Prompt templating (v0.1.2) design

**Status:** design, ready for plan.
**Date:** 2026-06-02
**Closes:** CLAUDE.md item 4 (templatize prompts); the "remaining gap" in [`2026-05-28-deployment-verification.md`](./2026-05-28-deployment-verification.md) §5.
**Builds on:** [`2026-05-29-research-loop-e2e-design.md`](./2026-05-29-research-loop-e2e-design.md), [`2026-05-26-efferents-deployment-design.md`](./2026-05-26-efferents-deployment-design.md).

## Motivation

After v0.1.1, the smoke-lab daemon boots cleanly through the orchestrator → Researcher → executor pipeline, but it can't *self-drive*: the agent prompts are still calibrated for the auto-qml reference lab. The Researcher reads "amp_ratio ≥ 0.04 is the fidelity gate" and proposes QFM/HEP-shaped experiments (`raw_q`, `aug_depth`, `epochs`) whose metrics (`e_w1`, `radial_l2_log`, `active_frac_w1`) the smoke lab doesn't produce. The `coefficient` knob the smoke lab actually exposes is invisible to it.

v0.1.2 makes the prompts domain-agnostic and templated, so the Researcher reasons in terms of the lab's own `LabConfig` (headline metric, panels, source dir, run command, hypothesis) — and lets a lab override any prompt wholesale. This is the precondition for both a real second example lab and any Phase-B venue work: neither is meaningful while the agents only think in QML terms.

## Scope

- New `efferents/agents/prompts/loader.py`: `load_prompt(name, *, extras=None)` renders a prompt (framework default or lab override) through `str.format()` with a LabConfig-derived variable dict.
- Rewrite the 9 QML-coupled framework prompts to be domain-agnostic + templated. (`reviewer_neutral.md` and `reviewer_enthusiast.md` are already clean — no change.)
- Add `LabConfig.prompts_dir` + per-lab override resolution (`<submission>/prompts/<name>.md`).
- Replace every `PROMPT_PATH.read_text()` callsite in the agents with `load_prompt(...)`.
- Tests: loader unit tests, a coupling-guard test, and the smoke-lab acceptance gate.

Out of scope:
- Auto-qml's own `prompts/` override directory (lives in the auto-qml repo; its next session adds it).
- Prompt *merge* semantics — overrides are wholesale replacement, not section-level merge.
- Per-prompt model selection or any change to which model each agent uses.
- A second full example lab (separate slice).

## Coupling inventory (measured 2026-06-02)

Lines per framework prompt matching the QML token set
(`e_w1|raw_q|aug_depth|active_frac|radial_l2|QFM|jet|amp_ratio|wallpaper|auto_qml|gen_max`):

| prompt | lines | tier |
|---|---|---|
| student.md | 49 | heavy |
| supervisor.md | 25 | heavy |
| researcher.md | 23 | heavy |
| coder.md | 19 | medium |
| writer.md | 15 | medium |
| librarian.md | 4 | light |
| analyst.md | 2 | light |
| reviewer_critical.md | 1 | light |
| rebuttal.md | 1 | light |
| reviewer_neutral.md | 0 | clean |
| reviewer_enthusiast.md | 0 | clean |

---

## 1. Templating mechanism + variables

**Mechanism:** Python `str.format()`. No new dependency. Literal braces in prompt prose must be escaped as `{{` / `}}` — handled during the rewrite, and the "renders without error" test catches misses.

**Variable surface**, rendered from `lab.get_config()` plus optional per-call extras:

```python
def _render_vars(cfg, extras=None) -> dict:
    panels = cfg.metrics.panels
    panel_block = _format_panel_block(panels)  # small markdown table; "(none)" if empty
    base = {
        # Identity
        "lab_id":              cfg.lab_id,
        "domain":              cfg.domain,
        "pi_handle":           cfg.pi_handle or "(anonymous)",
        # Source / executor
        "source_dir":          str(cfg.source.dir),
        "run_command":         cfg.executor.run_command,
        "smoke_command":       cfg.executor.smoke_command or cfg.executor.run_command,
        "config_template":     str(cfg.executor.config_template),
        # Metrics
        "headline_metric":     cfg.metrics.headline.column,
        "headline_direction":  cfg.metrics.headline.direction,   # "min" | "max"
        "panel_metrics":       ", ".join(p.column for p in panels) or "(none)",
        "panel_metrics_block": panel_block,
    }
    if extras:
        base.update(extras)
    return base
```

`extras` carries campaign-specific values only the caller knows — chiefly `hypothesis_body` and `hypothesis_slug` for the Researcher's per-campaign path. A prompt that references `{hypothesis_body}` but is loaded without that extra raises a clear `PromptRenderError` (see §4), not a silent blank.

**Loader:** `efferents/agents/prompts/loader.py`

```python
FRAMEWORK_PROMPTS_DIR = Path(__file__).parent

class PromptRenderError(RuntimeError):
    pass

def load_prompt(name: str, *, extras: dict | None = None) -> str:
    cfg = lab.get_config()
    override = (cfg.prompts_dir / f"{name}.md") if cfg.prompts_dir else None
    raw = (override.read_text() if override and override.is_file()
           else (FRAMEWORK_PROMPTS_DIR / f"{name}.md").read_text())
    try:
        return raw.format(**_render_vars(cfg, extras))
    except KeyError as e:
        raise PromptRenderError(
            f"prompt {name!r} references undefined variable {e.args[0]!r}"
        ) from e
```

**Callsite migration:** every `PROMPT_PATH.read_text()` (analyst, coder, researcher's student/supervisor loads, writer, librarian, reviewers, rebuttal) becomes `load_prompt("<name>")` (with `extras={...}` where a hypothesis body is in scope). The module-level `PROMPT_PATH` constants are removed.

---

## 2. Per-lab override mechanism

A lab may ship `<submission>/prompts/<name>.md`. If present, the loader uses it instead of the framework default; either way the chosen file is `.format()`-rendered, so overrides are templated too.

```
<submission>/
├── hypothesis.md
├── lab.yaml
├── src/
└── prompts/              # OPTIONAL override directory
    ├── student.md        # if present, replaces the framework student.md
    ├── supervisor.md
    └── coder.md
```

(The smoke lab ships no `prompts/` dir — see below.)

**LabConfig:** add `prompts_dir: Path | None = None`. In `from_submission`, set it to `submission_dir / "prompts"` when that directory exists, else `None`.

**Resolution rules:**
- Wholesale replacement, not merge. A lab's `student.md` fully replaces the framework's. No "which paragraph came from where" ambiguity.
- Missing override → framework default. No warning; the framework prompt is the canonical fallback.
- Template variables apply identically to framework and override prompts.

**Smoke lab ships NO overrides.** The framework's rewritten generic defaults must be sufficient to drive it. This is deliberate: it makes the smoke-lab acceptance test (§4) the objective check on rewrite quality. If the generic defaults can't make the Researcher propose "vary `coefficient`, watch `synthetic_loss`," the rewrite is incomplete.

**Auto-qml path:** auto-qml's next session adds its own `prompts/` override dir restoring the QFM/HEP/amp_ratio prose. No framework change needed then.

---

## 3. The prompt rewrite pass

Each prompt's domain-specific reasoning is replaced by a template variable or generic phrasing. The paper structure, dialogue roles, and budget/gate mechanics are already domain-agnostic and stay.

**Heavy — the Researcher trio (student, supervisor, researcher):**
- Replace the "amp_ratio is the FIDELITY GATE, check it first" calibration block with: "the lab's headline metric is `{headline_metric}` (optimize toward {headline_direction}); judge every proposal against it."
- Replace the fixed three-metric QML vector with `{panel_metrics_block}` (the lab's actual panels).
- Replace `raw_q`/`aug_depth`/`epochs` example overrides with generic "config knobs exposed in `{config_template}`."
- Replace "QFM quantum patch encoding for HEP quark/gluon jets" framing with `{domain}` + `{hypothesis_body}`.

**Medium (coder, writer):**
- `coder.md`: `auto_qml/X.py` → `{source_dir}`; `python -m auto_qml.run` → `{smoke_command}`. Drop QML-specific "don't break the diffusion math" cautions; keep generic "preserve the run contract, minimal diffs."
- `writer.md`: QML metric names in the results-section guidance → `{headline_metric}` / `{panel_metrics}`. The 5-section paper structure is already generic.

**Light (librarian, analyst, reviewer_critical, rebuttal):** surgical swaps of stray `jet`/`QFM`/metric tokens to generic equivalents or template vars.

**Acceptance bar:** `grep -iE "e_w1|raw_q|aug_depth|active_frac|radial_l2|qfm|jet|amp_ratio|wallpaper|auto_qml|gen_max" efferents/agents/prompts/*.md` returns zero matches.

**Named risk:** a prompt can be *technically* generic but *operationally* worse — vaguer, less able to drive good proposals. The §4 smoke-lab acceptance test is the objective guard: if the rewritten prompts can't drive one full autonomous cycle, they're not done.

---

## 4. Testing + acceptance

**`tests/test_prompt_loader.py` (new):**
- `load_prompt("student")` under the smoke LabConfig substitutes `{headline_metric}` → `synthetic_loss`; no unrendered placeholders remain.
- Override resolution: `cfg.prompts_dir` pointing at a tmpdir with `student.md` → that file's rendered content is returned.
- Missing override / `prompts_dir=None` → framework default used.
- A prompt referencing `{bogus_var}` raises `PromptRenderError` naming the variable (no raw `KeyError` escapes).
- Parametrized over all 11 framework `.md` files: `load_prompt(name)` renders without error under the smoke LabConfig. This catches an unescaped `{` introduced during the rewrite.

**`tests/test_prompts_domain_agnostic.py` (new):**
- Grep every framework prompt for the QML token set; assert zero matches. Executable form of §3's acceptance bar; fails CI on regression.

**Existing tests:** Researcher/Coder/Analyst/Writer tests driven with `FakeAnthropic` that assert on QML strings in the rendered system prompt get genericized or moved to `tests/lab_reference/`. Expect a handful of touch-ups.

**Acceptance gate (extends `tests/integration/test_smoke_lab_e2e.py`):**
- With templated prompts the Researcher proposes a `coefficient`-varying experiment, the executor runs `stub_run.py`, and a `synthetic_loss` row lands in `runs.sqlite`. The existing "≥1 row with non-null synthetic_loss within 90s" assertion becomes genuinely achievable (it was blocked purely by QML-flavored prompts).
- Stays `@pytest.mark.integration` (needs `ANTHROPIC_API_KEY`), opt-in.

**Manual verification:** run the smoke daemon foreground ~2 min; confirm the notebook shows a Researcher proposal phrased in `coefficient`/`synthetic_loss` terms, ≥1 run row lands, dashboard renders. Document in a short verification note and bump to v0.1.2.

### Out of scope for v0.1.2
- Auto-qml's `prompts/` override dir (its repo).
- Section-level prompt merge.
- Per-prompt model selection.
- A second full example lab.
