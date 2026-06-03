# Prompt Templating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the agent prompts domain-agnostic and templated so the smoke lab self-drives, with a per-lab override directory for domain-specific prompts.

**Architecture:** A `str.format()`-based `load_prompt(name)` loader renders prompts from a LabConfig-derived variable dict; resolution order is explicit-override-path → `<submission>/prompts/<name>.md` → framework default. All 9 QML-coupled framework prompts are rewritten generic; all 11 get literal braces escaped (so `.format()` is safe). Callsites swap `PROMPT_PATH.read_text()` → `load_prompt(...)`.

**Tech Stack:** Python 3.10+, `uv`, pytest. No new dependencies (`str.format` is stdlib).

**Spec:** `docs/superpowers/specs/2026-06-02-prompt-templating-design.md`

---

## Critical sequencing note

`load_prompt` calls `str.format(**vars)`. **Every** prompt contains literal `{`/`}` today (JSON examples, set notation) — 34 in writer.md down to 3 in each reviewer_*.md, only rebuttal.md and analyst.md have none. Unescaped braces crash `.format()`. Therefore:

1. Build the loader first (Task 2), tested against tmp prompts.
2. Rewrite + brace-escape all prompts (Tasks 3–5), each verified to render via the loader.
3. Only then migrate the agent callsites (Task 6).

Migrating a callsite before its prompt is brace-escaped would crash that agent at runtime.

## File map

**Create:**
- `efferents/agents/prompts/loader.py` — `load_prompt`, `_render_vars`, `_format_panel_block`, `PromptRenderError`
- `tests/test_prompt_loader.py`
- `tests/test_prompts_domain_agnostic.py`

**Modify:**
- `efferents/lab.py` — add `prompts_dir` field + `from_submission` wiring
- `efferents/agents/prompts/*.md` — 9 rewritten generic; all 11 brace-escaped
- `efferents/agents/analyst.py`, `coder.py`, `writer.py`, `librarian.py`, `rebuttal.py`, `reviewer.py`, `researcher.py` — callsite migration
- `tests/conftest.py` — (only if a fixture needs `prompts_dir`; default `None` likely suffices)
- `pyproject.toml` — version → `0.1.2`

---

## Task 1: LabConfig.prompts_dir

**Files:**
- Modify: `efferents/lab.py`
- Modify: `tests/test_lab_config.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_lab_config.py`:

```python
def test_prompts_dir_set_when_directory_exists(tmp_path):
    src = Path(__file__).parent / "fixtures" / "sample_submission"
    import shutil
    sub = tmp_path / "sub"
    shutil.copytree(src, sub)
    (sub / "prompts").mkdir()
    cfg = LabConfig.from_submission(sub)
    assert cfg.prompts_dir == sub / "prompts"


def test_prompts_dir_none_when_absent(tmp_path):
    src = Path(__file__).parent / "fixtures" / "sample_submission"
    import shutil
    sub = tmp_path / "sub"
    shutil.copytree(src, sub)
    cfg = LabConfig.from_submission(sub)
    assert cfg.prompts_dir is None


def test_prompts_dir_defaults_none_on_direct_construction():
    cfg = LabConfig(
        lab_id="t", domain="d", pi_handle=None,
        source=Source(dir=Path("/tmp")),
        executor=Executor(run_command="x {config_path}", smoke_command=None, config_template=Path("c.yaml")),
        metrics=Metrics(headline=Headline(column="m", direction="min"), panels=()),
        budget=Budget(),
    )
    assert cfg.prompts_dir is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_lab_config.py -k prompts_dir -v`
Expected: FAIL — `LabConfig` has no `prompts_dir` field.

- [ ] **Step 3: Add the field**

In `efferents/lab.py`, in the `LabConfig` dataclass, add a field after `peer_review_accept_min_threshold` (keep it last so positional construction in existing tests is unaffected):

```python
    prompts_dir: Path | None = None
```

In `_build_labconfig`, just before the `return LabConfig(...)`, compute it:

```python
    prompts_dir = submission_dir / "prompts"
    prompts_dir = prompts_dir if prompts_dir.is_dir() else None
```

And pass it in the `LabConfig(...)` constructor call:

```python
        prompts_dir=prompts_dir,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_lab_config.py -v`
Expected: all pass (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add efferents/lab.py tests/test_lab_config.py
git commit -m "feat(lab): add LabConfig.prompts_dir (per-lab prompt override directory)"
```

---

## Task 2: Prompt loader

**Files:**
- Create: `efferents/agents/prompts/loader.py`
- Create: `tests/test_prompt_loader.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_prompt_loader.py`:

```python
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
    assert "{config_path}" in v["run_command"]  # run_command is opaque, not re-rendered


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
    # Write a fake framework prompt by pointing the loader at a real file:
    # use a known framework prompt name but assert substitution on a tmp override
    # to avoid coupling to framework prompt contents.
    cfg = _install(tmp_path, prompts_dir=tmp_path / "prompts")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "demo.md").write_text(
        "Lab {lab_id} optimizes {headline_metric} ({headline_direction})."
    )
    out = load_prompt("demo")
    assert out == "Lab smoke optimizes synthetic_loss (min)."


def test_override_takes_precedence_over_framework(tmp_path):
    # 'analyst' is a real framework prompt; an override must win.
    cfg = _install(tmp_path, prompts_dir=tmp_path / "prompts")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "analyst.md").write_text("OVERRIDE {lab_id}")
    out = load_prompt("analyst")
    assert out == "OVERRIDE smoke"


def test_missing_override_falls_back_to_framework(tmp_path):
    # prompts_dir set but no matching file → framework default used (no error).
    cfg = _install(tmp_path, prompts_dir=tmp_path / "prompts")
    (tmp_path / "prompts").mkdir()
    out = load_prompt("analyst")  # framework analyst.md exists
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_loader.py -v`
Expected: ImportError — `efferents.agents.prompts.loader` doesn't exist.

- [ ] **Step 3: Create the loader**

Create `efferents/agents/prompts/loader.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_loader.py -v`
Expected: 8 passed.

Note: `test_missing_override_falls_back_to_framework` and `test_override_takes_precedence_over_framework` load the real framework `analyst.md`. `analyst.md` has 0 literal braces today (per the brace audit), so it renders fine even before the rewrite. If a future reordering breaks this, escape `analyst.md` first.

- [ ] **Step 5: Commit**

```bash
git add efferents/agents/prompts/loader.py tests/test_prompt_loader.py
git commit -m "feat(prompts): add load_prompt loader with LabConfig-derived rendering + override resolution"
```

---

## Task 3: Rewrite the Researcher trio (student, supervisor, researcher)

These carry the heaviest QML coupling. Rewrite each to be domain-agnostic + templated, escaping all literal braces.

**Files:**
- Modify: `efferents/agents/prompts/student.md`
- Modify: `efferents/agents/prompts/supervisor.md`
- Modify: `efferents/agents/prompts/researcher.md`
- Modify: `tests/test_prompt_loader.py` (add per-prompt render assertions)

- [ ] **Step 1: Add failing render tests**

Append to `tests/test_prompt_loader.py`:

```python
@pytest.mark.parametrize("name", ["student", "supervisor", "researcher"])
def test_researcher_trio_renders_clean(tmp_path, name):
    _install(tmp_path)
    extras = {"hypothesis_body": "Increasing coefficient lowers loss.",
              "hypothesis_slug": "coeff"}
    out = load_prompt(name, extras=extras)
    # No unrendered single-brace placeholders survive
    assert "{" not in out.replace("{{", "").replace("}}", "")
    # Headline metric is woven in
    assert "synthetic_loss" in out
    # No QML residue
    for tok in ("e_w1", "raw_q", "amp_ratio", "QFM", "auto_qml"):
        assert tok not in out
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_prompt_loader.py -k researcher_trio -v`
Expected: FAIL — current prompts contain QML tokens, unescaped braces, and no `{headline_metric}`.

- [ ] **Step 3: Rewrite `student.md`**

Read the current file. Apply these transformations (the file is ~460 lines; preserve its structure — role definition, proposal format, JSON schema — and change only the domain content):

1. **Opening framing** (lines ~10–20): replace the "QFM quantum patch encoding for HEP quark/gluon jets" / `raw_q` setup with:
   > You are the PhD student in an autonomous research lab studying `{domain}`. The lab's current hypothesis:
   >
   > {hypothesis_body}
   >
   > Your job is to propose experiments — config changes to the lab's runnable code — that test and advance this hypothesis.

2. **Fidelity-gate block** (the "`amp_ratio` is the FIDELITY GATE, check it first" calibration, lines ~31–45): replace wholesale with:
   > The lab's headline metric is **`{headline_metric}`**, which you want to drive toward **{headline_direction}**. Judge every proposal against it first. Secondary metrics:
   >
   > {panel_metrics_block}

3. **Metric definitions** (the `e_w1`/`radial_l2_log`/`active_frac_w1` glossary, lines ~48–62): delete the QML glossary; the panel block above replaces it.

4. **Example overrides**: replace any `raw_q`/`aug_depth`/`epochs`/`cond_drop_p` example config knobs with generic phrasing: "config knobs are whatever keys appear in the lab's config template (`{config_template}`); propose overrides as dotted paths into that YAML."

5. **JSON schema block**: this is the proposal output format. Escape every literal `{` → `{{` and `}` → `}}` so `.format()` leaves it intact. Do NOT change the schema's shape.

6. Sweep the rest for `jet`, `QFM`, `wallpaper`, `gen_max` — replace with neutral wording.

- [ ] **Step 4: Rewrite `supervisor.md`**

Same approach. The supervisor reviews the student's proposals and allocates budget. Replace:
- The QML domain framing → `{domain}` + `{hypothesis_body}`.
- The "reject proposals that ignore amp_ratio" rule → "reject proposals that don't state their expected effect on `{headline_metric}`."
- The metric vocabulary → `{headline_metric}` / `{panel_metrics}`.
- Escape literal braces in any JSON/example blocks.

- [ ] **Step 5: Rewrite `researcher.md`**

This is the shared/overview prompt. Replace QML metric references with `{headline_metric}` / `{panel_metrics_block}`, the domain framing with `{domain}`, and escape braces.

- [ ] **Step 6: Verify render tests pass**

Run: `uv run pytest tests/test_prompt_loader.py -k researcher_trio -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add efferents/agents/prompts/student.md efferents/agents/prompts/supervisor.md efferents/agents/prompts/researcher.md tests/test_prompt_loader.py
git commit -m "refactor(prompts): rewrite Researcher trio domain-agnostic + templated"
```

---

## Task 4: Rewrite medium prompts (coder, writer)

**Files:**
- Modify: `efferents/agents/prompts/coder.md`
- Modify: `efferents/agents/prompts/writer.md`
- Modify: `tests/test_prompt_loader.py`

- [ ] **Step 1: Add failing render tests**

Append to `tests/test_prompt_loader.py`:

```python
@pytest.mark.parametrize("name", ["coder", "writer"])
def test_medium_prompts_render_clean(tmp_path, name):
    _install(tmp_path)
    out = load_prompt(name)
    assert "{" not in out.replace("{{", "").replace("}}", "")
    for tok in ("e_w1", "raw_q", "amp_ratio", "QFM", "auto_qml", "gen_max"):
        assert tok not in out
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_prompt_loader.py -k medium_prompts -v`
Expected: FAIL.

- [ ] **Step 3: Rewrite `coder.md`**

1. Replace `auto_qml/X.py` path references with `{source_dir}` (e.g., "edit files under `{source_dir}`").
2. Replace `python -m auto_qml.run --config config/smoke.yaml` with `{smoke_command}`.
3. Delete QML-specific cautions ("don't break the diffusion math", "preserve the QFM encoding"); keep the generic contract: "make minimal diffs; the smoke command must still emit a JSON metrics object on stdout after your change."
4. Escape literal braces in the edit-plan JSON example.

- [ ] **Step 4: Rewrite `writer.md`**

1. Replace QML metric names in the Results-section guidance with `{headline_metric}` / `{panel_metrics}`.
2. The 5-section paper structure (Motivation/Methods/Results/Conclusion/Next) stays.
3. Escape braces in any frontmatter/JSON example.

- [ ] **Step 5: Verify**

Run: `uv run pytest tests/test_prompt_loader.py -k medium_prompts -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add efferents/agents/prompts/coder.md efferents/agents/prompts/writer.md tests/test_prompt_loader.py
git commit -m "refactor(prompts): rewrite coder + writer domain-agnostic + templated"
```

---

## Task 5: Rewrite light prompts + escape the two clean ones

The light prompts (librarian, analyst, reviewer_critical, rebuttal) need surgical QML-token swaps. The two already-clean reviewer prompts (reviewer_neutral, reviewer_enthusiast) have **no QML coupling but do have literal braces** — they need brace-escaping only so `load_prompt` doesn't crash.

**Files:**
- Modify: `efferents/agents/prompts/librarian.md`, `analyst.md`, `reviewer_critical.md`, `rebuttal.md`
- Modify: `efferents/agents/prompts/reviewer_neutral.md`, `reviewer_enthusiast.md` (brace-escape only)
- Modify: `tests/test_prompt_loader.py`

- [ ] **Step 1: Add the all-prompts render guard test**

Append to `tests/test_prompt_loader.py`:

```python
ALL_PROMPTS = [
    "student", "supervisor", "researcher", "coder", "writer",
    "librarian", "analyst", "reviewer_critical", "reviewer_neutral",
    "reviewer_enthusiast", "rebuttal",
]


@pytest.mark.parametrize("name", ALL_PROMPTS)
def test_every_framework_prompt_renders(tmp_path, name):
    _install(tmp_path)
    extras = {"hypothesis_body": "h", "hypothesis_slug": "s"}
    out = load_prompt(name, extras=extras)
    assert "{" not in out.replace("{{", "").replace("}}", "")
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_prompt_loader.py -k every_framework_prompt -v`
Expected: FAIL on the prompts not yet escaped (librarian, analyst, reviewer_*, rebuttal — and any earlier prompt with a stray unescaped brace).

- [ ] **Step 3: Rewrite the light four**

- `librarian.md`: replace the 4 QML lines (lit-review example topics like "QFM diffusion", "jet") with generic `{domain}` phrasing. Escape its 19 braces.
- `analyst.md`: replace the 2 QML metric mentions with `{headline_metric}`. (0 literal braces — no escaping needed.)
- `reviewer_critical.md`: replace the 1 QML token with neutral wording; escape its 3 braces.
- `rebuttal.md`: replace the 1 QML token; (0 braces).

- [ ] **Step 4: Brace-escape the two clean reviewers**

`reviewer_neutral.md` and `reviewer_enthusiast.md`: no content change, just `{` → `{{` and `}` → `}}` on the 3 literal braces each. (If any of those braces are actually intended as template vars, leave them single — but per the audit they're set/JSON notation, so escape.)

- [ ] **Step 5: Verify the full render guard passes**

Run: `uv run pytest tests/test_prompt_loader.py -k every_framework_prompt -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add efferents/agents/prompts/librarian.md efferents/agents/prompts/analyst.md efferents/agents/prompts/reviewer_critical.md efferents/agents/prompts/rebuttal.md efferents/agents/prompts/reviewer_neutral.md efferents/agents/prompts/reviewer_enthusiast.md tests/test_prompt_loader.py
git commit -m "refactor(prompts): genericize light prompts + brace-escape clean reviewers"
```

---

## Task 6: Migrate agent callsites to load_prompt

Now that every prompt is brace-safe and templated, swap the raw `read_text()` loads. Preserve the Researcher's per-student override + focus-injection behavior.

**Files:**
- Modify: `efferents/agents/analyst.py`, `coder.py`, `writer.py`, `librarian.py`, `rebuttal.py`, `reviewer.py`, `researcher.py`

- [ ] **Step 1: Migrate the simple six**

For each of `analyst.py`, `coder.py`, `writer.py`, `librarian.py`, `rebuttal.py`:
- Add `from efferents.agents.prompts.loader import load_prompt` to the imports.
- Replace the `PROMPT_PATH = Path(__file__).parent / "prompts" / "<name>.md"` constant's usage: change `PROMPT_PATH.read_text()` → `load_prompt("<name>")`. Remove the now-unused `PROMPT_PATH` constant.

For `reviewer.py`: change `(PROMPTS_DIR / f"reviewer_{persona}.md").read_text()` → `load_prompt(f"reviewer_{persona}")`. Keep the `persona in PERSONAS` validation.

- [ ] **Step 2: Migrate `researcher.py` (preserve per-student override + focus)**

In `researcher.py`, the student-prompt load (around line 569–595) currently:
1. picks `prompt_path` = `STUDENT_PROMPT_PATH` or a per-student override path,
2. `read_text()`s it,
3. prepends a `## Your focus` block if the student has a `focus`.

Rewrite to route through the loader while keeping (1) and (3):

```python
    # Per-student prompt override → explicit override_path; else lab/framework default.
    override_path = None
    try:
        student = _lab.get_student(student_id)
    except KeyError:
        student = None
    if student:
        ov = (student.get("prompt_overrides") or {}).get("student")
        if ov:
            cand = Path(ov) if Path(ov).is_absolute() else Path(__file__).parent.parent / ov
            if cand.exists():
                override_path = cand
    system_text = load_prompt("student", override_path=override_path)
    if student and student.get("focus") and override_path is None:
        system_text = (
            f"## Your focus (student: {student_id})\n\n{student['focus']}\n\n"
            "Stay within this focus when picking proposals; tell the Supervisor "
            "explicitly when a finding from outside the focus should change the "
            "direction.\n\n---\n\n"
        ) + system_text
```

For the two `SUPERVISOR_PROMPT_PATH.read_text()` sites (around lines 413, 672), replace each with `load_prompt("supervisor")`. Remove the `STUDENT_PROMPT_PATH` / `SUPERVISOR_PROMPT_PATH` constants (keep `PROMPTS_DIR` if other code uses it — grep first).

Add `from efferents.agents.prompts.loader import load_prompt` to researcher imports.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration 2>&1 | tail -8`
Expected: failures only in tests that assert on QML strings in rendered prompts (handled in Task 7). Note which fail.

- [ ] **Step 4: Commit**

```bash
git add efferents/agents/analyst.py efferents/agents/coder.py efferents/agents/writer.py efferents/agents/librarian.py efferents/agents/rebuttal.py efferents/agents/reviewer.py efferents/agents/researcher.py
git commit -m "refactor(agents): load prompts through load_prompt (templated + override-aware)"
```

---

## Task 7: Coupling guard + fix QML-asserting tests

**Files:**
- Create: `tests/test_prompts_domain_agnostic.py`
- Modify: any test asserting QML strings in rendered prompts (triage from Task 6)

- [ ] **Step 1: Write the coupling guard**

Create `tests/test_prompts_domain_agnostic.py`:

```python
"""Framework prompts must carry no QML-specific vocabulary."""
from __future__ import annotations
import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "efferents" / "agents" / "prompts"
QML_TOKENS = re.compile(
    r"e_w1|raw_q|aug_depth|active_frac|radial_l2|qfm|jet|amp_ratio|wallpaper|auto_qml|gen_max",
    re.IGNORECASE,
)


def test_no_qml_tokens_in_framework_prompts():
    offenders = {}
    for md in sorted(PROMPTS_DIR.glob("*.md")):
        hits = QML_TOKENS.findall(md.read_text())
        if hits:
            offenders[md.name] = sorted(set(h.lower() for h in hits))
    assert not offenders, f"QML tokens found in framework prompts: {offenders}"
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_prompts_domain_agnostic.py -v`
Expected: PASS (Tasks 3–5 removed all QML tokens). If it fails, the named offender prompt still has residue — fix that prompt, re-run.

- [ ] **Step 3: Triage and fix QML-asserting tests**

For each test that failed in Task 6 Step 3 because it asserted a QML string appears in a rendered prompt: either genericize the assertion (assert on the new generic phrasing) or, if the test is fundamentally QML-specific, `git mv` it to `tests/lab_reference/` and add `pytestmark = pytest.mark.skip(reason="QML-specific; lives with auto-qml")`.

Run the full suite to confirm green:

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration 2>&1 | tail -5`
Expected: all pass, pre-existing skips unchanged.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add prompt coupling guard + genericize QML-asserting prompt tests"
```

---

## Task 8: Acceptance — smoke lab self-drives + tag v0.1.2

**Files:**
- Modify: `pyproject.toml`
- Create: `docs/superpowers/specs/<today>-prompt-templating-verification.md`

- [ ] **Step 1: Full unit suite green**

Run: `uv run pytest tests/ --ignore=tests/lab_reference 2>&1 | tail -3`
Expected: all pass (integration auto-skips without API key).

- [ ] **Step 2: Run the smoke daemon foreground**

Pre-clean and launch (needs `ANTHROPIC_API_KEY`):

```bash
rm -rf examples/smoke-lab/lab examples/smoke-lab/context
.venv/bin/efferents start --submission examples/smoke-lab/ > /tmp/smoke-v012.log 2>&1 &
```

Let it run ~2 minutes, then inspect:

```bash
sqlite3 examples/smoke-lab/lab/runs.sqlite "SELECT COUNT(*), MIN(synthetic_loss), MAX(synthetic_loss) FROM runs"
tail -40 examples/smoke-lab/lab/lab_notebook.md
```

Then stop the daemon:

```bash
pkill -f "efferents.cli start"
```

**Success criteria:**
- The notebook shows a Researcher proposal phrased in terms of `coefficient` / `synthetic_loss` (NOT `raw_q` / `e_w1`).
- ≥1 row with non-null `synthetic_loss` landed in `runs.sqlite`.
- No `orchestrator step FAILED: OperationalError: no such column: seed` (the v0.1.1 blocker).

If the Researcher still proposes QML-shaped experiments, a prompt rewrite was incomplete — return to Task 3/4 for the offending prompt. If `synthetic_loss` rows land, the slice is done.

- [ ] **Step 3: Write the verification note**

Create `docs/superpowers/specs/<today>-prompt-templating-verification.md` (replace `<today>` with the ISO date) recording: unit test counts, the Researcher proposal text observed, the run-row count + loss range, and any prompt that needed a second pass.

- [ ] **Step 4: Bump version + tag**

Edit `pyproject.toml`: `version = "0.1.2"`.

```bash
git add pyproject.toml docs/superpowers/specs/
git commit -m "chore: bump to 0.1.2 — prompts templated; smoke lab self-drives"
git tag -a v0.1.2 -m "v0.1.2 — domain-agnostic templated prompts + per-lab override dir"
```

The smoke lab now runs an autonomous research cycle with zero QML hardcoding. Auto-qml restores its domain prose via its own `prompts/` override dir in its next session.
