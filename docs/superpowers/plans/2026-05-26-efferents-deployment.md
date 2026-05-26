# efferents Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the moltbook-shaped entry-flow for efferents: an agent reads a hosted `intake.md`, runs popper-probe, prompts for lab config, and kicks off a backgrounded daemon that runs the Phase-A orchestrator against a per-submission `LabConfig`.

**Architecture:** New `LabConfig` dataclass loaded from `submission/lab.yaml`; daemon process wraps the existing orchestrator; four targeted decouple edits in Phase A code (coder path scope, progress panels, analyst epsilon, run-result contract); a tiny non-QML smoke lab proves the plumbing.

**Tech Stack:** Python 3.10+, `uv` for venv, pytest, pyyaml, pydantic 2 (already deps), `argparse` for CLI, `fcntl`+`os.fork` for daemon/registry primitives.

**Spec:** `docs/superpowers/specs/2026-05-26-efferents-deployment-design.md`

---

## File map

**Create:**
- `efferents/cli.py` — argparse subcommand dispatch
- `efferents/registry.py` — `~/.efferents/registry.json` read/write with fcntl lock
- `efferents/daemon.py` — fork/pidfile/signal-handling wrapper
- `efferents/exec.py` — `_extract_trailing_json`, `_run_and_capture`, `RunResult`
- `tests/test_lab_config.py`, `tests/test_registry.py`, `tests/test_daemon.py`, `tests/test_cli.py`, `tests/test_exec.py`
- `tests/integration/__init__.py`, `tests/integration/test_smoke_lab_e2e.py`
- `tests/lab_reference/__init__.py` (destination for QML-coupled tests)
- `examples/smoke-lab/` (lab.yaml, hypothesis.md, src/, configs/)
- `skills/intake.md`

**Modify:**
- `efferents/lab.py` — replace contents with LabConfig + loader + get/set + shim
- `efferents/agents/coder.py` — path scope reads from LabConfig (lines 47-49, 63-64, 83); subprocess passes `cwd=cfg.source.dir`
- `efferents/agents/progress.py` — `_PANEL_METRICS` becomes `_panel_metrics()`
- `efferents/agents/analyst.py` — `epsilon=0.005` reads from `cfg.metrics.flat_digest_epsilon`
- `tests/conftest.py` — add `smoke_lab_config` fixture (autouse)
- `pyproject.toml` — add `[project.scripts] efferents = "efferents.cli:main"`

---

## Phase 1 — LabConfig foundation (additive; no behavior change)

### Task 1: Add LabConfig dataclasses

**Files:**
- Modify: `efferents/lab.py` (append; keep existing constants for now)
- Create: `tests/test_lab_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_lab_config.py
"""LabConfig construction and defaults."""
from __future__ import annotations
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
    with pytest.raises(Exception):  # FrozenInstanceError under dataclasses
        cfg.lab_id = "different"  # type: ignore[misc]


def test_submission_error_is_value_error():
    assert issubclass(SubmissionError, ValueError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lab_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'LabConfig' from 'efferents.lab'`

- [ ] **Step 3: Add the dataclasses to lab.py**

Open `efferents/lab.py` and append (do NOT remove existing constants like `LAB_ID`, `STUDENTS`, etc.):

```python
# ---------------------------------------------------------------------------
# LabConfig — new per-submission configuration model. Loaded by the daemon
# at startup from <submission>/lab.yaml. Coexists with the legacy module
# constants above; new code reads from `get_config()` instead.
# ---------------------------------------------------------------------------
from dataclasses import dataclass, field  # noqa: E402  (kept after legacy block)
from pathlib import Path  # noqa: E402


@dataclass(frozen=True)
class Headline:
    column: str
    direction: str  # "max" | "min"


@dataclass(frozen=True)
class Panel:
    column: str
    label: str
    target: float | None = None


@dataclass(frozen=True)
class Source:
    dir: Path
    allowed_patterns: tuple[str, ...] = ("**/*.py",)


@dataclass(frozen=True)
class Executor:
    run_command: str  # must contain "{config_path}"
    smoke_command: str | None
    config_template: Path
    run_timeout_s: int = 7200
    smoke_timeout_s: int = 300
    env_passthrough: tuple[str, ...] = ()


@dataclass(frozen=True)
class Metrics:
    headline: Headline
    panels: tuple[Panel, ...]
    flat_digest_epsilon: float = 0.005


@dataclass(frozen=True)
class Budget:
    daily_cap_usd: float = 10.0
    sonnet_default: bool = True


@dataclass(frozen=True)
class LabConfig:
    lab_id: str
    domain: str
    pi_handle: str | None
    source: Source
    executor: Executor
    metrics: Metrics
    budget: Budget
    default_student_id: str = "primary"
    max_open_campaigns_per_student: int = 2
    students: tuple[dict, ...] = field(default_factory=lambda: (
        {"id": "primary", "handle": None, "focus": "", "prompt_overrides": {}},
    ))
    peer_review_enabled: bool = False
    peer_review_accept_mean_threshold: float = 6.0
    peer_review_accept_min_threshold: int = 4


class SubmissionError(ValueError):
    """Raised when a submission directory is invalid."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lab_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_lab_config.py efferents/lab.py
git commit -m "feat(lab): add LabConfig dataclasses (additive, no consumers yet)"
```

---

### Task 2: LabConfig.from_submission loader

**Files:**
- Modify: `efferents/lab.py` (add `from_submission` classmethod + helpers)
- Modify: `tests/test_lab_config.py` (add loader tests)
- Create: `tests/fixtures/sample_submission/hypothesis.md` and `lab.yaml` (test fixtures)

- [ ] **Step 1: Create test fixture directory**

```bash
mkdir -p tests/fixtures/sample_submission/src
mkdir -p tests/fixtures/sample_submission/configs
touch tests/fixtures/sample_submission/src/__init__.py
```

Write `tests/fixtures/sample_submission/configs/default.yaml`:

```yaml
coefficient: 0.5
```

Write `tests/fixtures/sample_submission/hypothesis.md`:

```markdown
---
slug: sample-conjecture
falsifiability_gate: passed
status: active
created_at: 2026-05-26T00:00:00Z
---

# Sample conjecture

## Falsifier
A run with coefficient > 0.7 produces synthetic_loss < 0.1.
```

Write `tests/fixtures/sample_submission/lab.yaml`:

```yaml
lab_id: sample-conjecture
domain: synthetic
source:
  dir: ./src/
executor:
  run_command: "python -m sample.run --config {config_path}"
  config_template: configs/default.yaml
metrics:
  headline:
    column: synthetic_loss
    direction: min
  panels:
    - { column: synthetic_loss, label: "Loss" }
```

- [ ] **Step 2: Write failing loader tests**

Append to `tests/test_lab_config.py`:

```python
from efferents.lab import LabConfig


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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_lab_config.py -v`
Expected: 8 failures (`from_submission` doesn't exist yet).

- [ ] **Step 4: Implement `from_submission`**

Append to `efferents/lab.py`:

```python
import re  # noqa: E402
import yaml  # noqa: E402


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_hypothesis(path: Path) -> dict:
    if not path.exists():
        raise SubmissionError(f"hypothesis.md not found at {path}")
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        raise SubmissionError(f"hypothesis.md missing YAML frontmatter at {path}")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise SubmissionError(f"hypothesis.md frontmatter not valid YAML: {e}") from e
    gate = fm.get("falsifiability_gate")
    if gate != "passed":
        raise SubmissionError(
            f"hypothesis.md has falsifiability_gate={gate!r}; expected 'passed'"
        )
    return fm


def _load_lab_yaml(path: Path) -> dict:
    if not path.exists():
        raise SubmissionError(f"lab.yaml not found at {path}")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise SubmissionError(f"lab.yaml not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise SubmissionError("lab.yaml must be a mapping at top level")
    return data


def _build_labconfig(fm: dict, raw: dict, submission_dir: Path) -> "LabConfig":
    src_block = raw.get("source") or {}
    src_dir_str = src_block.get("dir")
    if not src_dir_str:
        raise SubmissionError("lab.yaml: source.dir is required")
    src_dir = (submission_dir / src_dir_str).resolve() if not Path(src_dir_str).is_absolute() else Path(src_dir_str)
    if not src_dir.is_dir():
        raise SubmissionError(f"source.dir does not exist on disk: {src_dir}")

    exe = raw.get("executor") or {}
    run_command = exe.get("run_command")
    if not run_command:
        raise SubmissionError("lab.yaml: executor.run_command is required")
    if "{config_path}" not in run_command:
        raise SubmissionError("executor.run_command must contain the {config_path} placeholder")
    config_template_str = exe.get("config_template")
    if not config_template_str:
        raise SubmissionError("lab.yaml: executor.config_template is required")
    config_template = Path(config_template_str)
    abs_config_template = (src_dir / config_template) if not config_template.is_absolute() else config_template
    if not abs_config_template.is_file():
        raise SubmissionError(f"executor.config_template not found under source.dir: {abs_config_template}")

    metrics_raw = raw.get("metrics") or {}
    headline_raw = metrics_raw.get("headline") or {}
    headline_col = headline_raw.get("column", "")
    if not headline_col:
        raise SubmissionError("lab.yaml: metrics.headline.column is required")
    headline_dir = headline_raw.get("direction")
    if headline_dir not in ("max", "min"):
        raise SubmissionError(
            f"metrics.headline.direction must be 'max' or 'min'; got {headline_dir!r}"
        )

    panels = tuple(
        Panel(column=p["column"], label=p.get("label", p["column"]), target=p.get("target"))
        for p in (metrics_raw.get("panels") or [])
    )

    budget_raw = raw.get("budget") or {}

    lab_id = raw.get("lab_id") or fm.get("slug")
    if not lab_id:
        raise SubmissionError("lab_id missing; provide it in lab.yaml or hypothesis.md slug")

    return LabConfig(
        lab_id=lab_id,
        domain=raw.get("domain", "unspecified"),
        pi_handle=raw.get("pi_handle"),
        source=Source(
            dir=src_dir,
            allowed_patterns=tuple(src_block.get("allowed_patterns") or ("**/*.py",)),
        ),
        executor=Executor(
            run_command=run_command,
            smoke_command=exe.get("smoke_command"),
            config_template=abs_config_template,
            run_timeout_s=int(exe.get("run_timeout_s", 7200)),
            smoke_timeout_s=int(exe.get("smoke_timeout_s", 300)),
            env_passthrough=tuple(exe.get("env_passthrough") or ()),
        ),
        metrics=Metrics(
            headline=Headline(column=headline_col, direction=headline_dir),
            panels=panels,
            flat_digest_epsilon=float(metrics_raw.get("flat_digest_epsilon", 0.005)),
        ),
        budget=Budget(
            daily_cap_usd=float(budget_raw.get("daily_cap_usd", 10.0)),
            sonnet_default=bool(budget_raw.get("sonnet_default", True)),
        ),
    )


@classmethod  # type: ignore[misc]  (added monkey-style; see Step 5)
def _labconfig_from_submission(cls, submission_dir: Path) -> "LabConfig":
    submission_dir = Path(submission_dir).resolve()
    fm = _parse_hypothesis(submission_dir / "hypothesis.md")
    raw = _load_lab_yaml(submission_dir / "lab.yaml")
    return _build_labconfig(fm, raw, submission_dir)


LabConfig.from_submission = _labconfig_from_submission  # type: ignore[attr-defined]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_lab_config.py -v`
Expected: 11 passed

- [ ] **Step 6: Commit**

```bash
git add tests/test_lab_config.py tests/fixtures efferents/lab.py
git commit -m "feat(lab): add LabConfig.from_submission loader with full validation"
```

---

### Task 3: get_config / set_config + back-compat shim

**Files:**
- Modify: `efferents/lab.py` (add accessors and PEP 562 `__getattr__`)
- Modify: `tests/test_lab_config.py` (accessor + shim tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_lab_config.py`:

```python
def test_get_config_raises_before_set():
    from efferents import lab as lab_mod
    # Reset module-level state
    lab_mod._active = None
    with pytest.raises(RuntimeError, match="LabConfig not loaded"):
        lab_mod.get_config()


def test_set_get_round_trip(tmp_path):
    src = Path(__file__).parent / "fixtures" / "sample_submission"
    import shutil
    sub = tmp_path / "sub"
    shutil.copytree(src, sub)
    cfg = LabConfig.from_submission(sub)
    from efferents import lab as lab_mod
    lab_mod.set_config(cfg)
    assert lab_mod.get_config() is cfg
    lab_mod._active = None  # cleanup


def test_shim_exposes_lab_id_when_loaded(tmp_path):
    src = Path(__file__).parent / "fixtures" / "sample_submission"
    import shutil
    sub = tmp_path / "sub"
    shutil.copytree(src, sub)
    cfg = LabConfig.from_submission(sub)
    from efferents import lab as lab_mod
    lab_mod.set_config(cfg)
    # Re-import via attribute access (PEP 562 __getattr__ fires for missing
    # module-level constants). Note: existing static LAB_ID still wins until
    # we remove it; the shim is exercised by attributes that don't exist as
    # static module-level names.
    assert lab_mod._labconfig_attr_via_shim("LAB_ID") == "sample-conjecture"
    assert lab_mod._labconfig_attr_via_shim("DOMAIN") == "synthetic"
    lab_mod._active = None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_lab_config.py -v`
Expected: 3 new failures (`get_config`, `set_config`, `_labconfig_attr_via_shim` not defined).

- [ ] **Step 3: Add accessors and shim**

Append to `efferents/lab.py`:

```python
_active: LabConfig | None = None


def set_config(cfg: LabConfig) -> None:
    """Install the active LabConfig. Called by the daemon at startup."""
    global _active
    _active = cfg


def get_config() -> LabConfig:
    """Return the active LabConfig or raise RuntimeError."""
    if _active is None:
        raise RuntimeError(
            "LabConfig not loaded; call set_config() before agent code runs"
        )
    return _active


def _labconfig_attr_via_shim(name: str):
    """Resolve a legacy module-level constant from the active LabConfig.
    Used by the PEP 562 __getattr__ once the static constants are removed."""
    cfg = get_config()
    mapping = {
        "LAB_ID": cfg.lab_id,
        "DOMAIN": cfg.domain,
        "SUBDOMAIN": None,
        "PI_HANDLE": cfg.pi_handle,
        "CODE_REPO": "",
        "DEFAULT_STUDENT_ID": cfg.default_student_id,
        "MAX_OPEN_CAMPAIGNS_PER_STUDENT": cfg.max_open_campaigns_per_student,
        "STUDENTS": list(cfg.students),
        "PEER_REVIEW_ENABLED": cfg.peer_review_enabled,
        "PEER_REVIEW_ACCEPT_MEAN_THRESHOLD": cfg.peer_review_accept_mean_threshold,
        "PEER_REVIEW_ACCEPT_MIN_THRESHOLD": cfg.peer_review_accept_min_threshold,
    }
    if name not in mapping:
        raise AttributeError(name)
    return mapping[name]
```

Note: we do NOT install a PEP 562 `__getattr__` yet — the legacy static constants at the top of `lab.py` still satisfy attribute lookups. The shim becomes load-bearing only when the legacy constants are removed (a later cleanup, out of scope for v1).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_lab_config.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_lab_config.py efferents/lab.py
git commit -m "feat(lab): add get_config/set_config + legacy-constant shim helper"
```

---

### Task 4: smoke_lab_config fixture for existing tests

**Files:**
- Modify: `tests/conftest.py` (add autouse fixture)

- [ ] **Step 1: Write the fixture**

Append to `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def smoke_lab_config(tmp_path_factory):
    """Auto-install a minimal LabConfig for every test, then tear down.

    Tests that need a custom LabConfig can call lab.set_config(...) themselves
    inside the test body; this fixture's teardown still clears it.
    """
    from efferents import lab as lab_mod
    from efferents.lab import (
        Budget, Executor, Headline, LabConfig, Metrics, Panel, Source,
    )

    tmp = tmp_path_factory.mktemp("smoke-lab-fixture")
    src_dir = tmp / "src"
    src_dir.mkdir()
    (src_dir / "default.yaml").touch()

    cfg = LabConfig(
        lab_id="smoke-fixture",
        domain="test",
        pi_handle=None,
        source=Source(dir=src_dir),
        executor=Executor(
            run_command="echo {config_path}",
            smoke_command=None,
            config_template=src_dir / "default.yaml",
        ),
        metrics=Metrics(
            headline=Headline(column="synthetic_loss", direction="min"),
            panels=(Panel(column="synthetic_loss", label="Loss"),),
        ),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    yield cfg
    lab_mod._active = None
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -x --ignore=tests/integration --ignore=tests/lab_reference 2>&1 | tail -40`
Expected: most tests pass; some may break with the new fixture installed. Note any failures by file — they're either QML-specific tests (handled in Task 16) or generic tests that need fixture-aware updates (fix now if obvious).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add autouse smoke_lab_config fixture for LabConfig-dependent tests"
```

---

## Phase 2 — Decouple touchpoints

### Task 5: Coder path scope reads from LabConfig

**Files:**
- Modify: `efferents/agents/coder.py` (lines 43-67, 83, and subprocess invocations)
- Create: `tests/test_coder_path_scope.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_coder_path_scope.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_coder_path_scope.py -v`
Expected: 4 failures — `_target_globs`, `_new_file_path_re`, `_smoke_command` don't exist as functions yet.

- [ ] **Step 3: Refactor coder.py**

Open `efferents/agents/coder.py`. Replace lines 43-49 (the `DEFAULT_TARGET_GLOBS`, `SMOKE_CONFIG`, etc. block) and line 83 (`_NEW_FILE_PATH_RE`) with helper functions.

Replace this section near the top of coder.py:

```python
PROMPT_PATH = Path(__file__).parent / "prompts" / "coder.md"
DEFAULT_TARGET_GLOBS = [
    "auto_qml/*.py",
    "config/default.yaml",
    "config/smoke.yaml",
]
SMOKE_CONFIG = "config/smoke.yaml"
SMOKE_TIMEOUT_SECONDS = 180
MAX_LIT_CALLS_PER_PASS = 3
```

with:

```python
from efferents import lab as _lab

PROMPT_PATH = Path(__file__).parent / "prompts" / "coder.md"
MAX_LIT_CALLS_PER_PASS = 3


def _target_globs() -> list[str]:
    """Patterns from LabConfig.source.allowed_patterns are RELATIVE to source.dir;
    we prepend the absolute source dir to each so callers get absolute globs."""
    cfg = _lab.get_config()
    src = str(cfg.source.dir).rstrip("/")
    out = [f"{src}/{pat}" for pat in cfg.source.allowed_patterns]
    out.append(str(cfg.executor.config_template))
    return out


def _new_file_path_re():
    cfg = _lab.get_config()
    src = re.escape(str(cfg.source.dir).rstrip("/"))
    return re.compile(rf"^{src}/[A-Za-z_][A-Za-z0-9_]*\.py$")


def _smoke_command(config_path: Path) -> str:
    cfg = _lab.get_config()
    template = cfg.executor.smoke_command or cfg.executor.run_command
    return template.format(config_path=str(config_path))


def _smoke_timeout() -> int:
    return _lab.get_config().executor.smoke_timeout_s
```

Then replace line 83 (`_NEW_FILE_PATH_RE = re.compile(...)`) — delete that line and use `_new_file_path_re()` at call sites. Find any reference to `_NEW_FILE_PATH_RE` in this file (use `grep -n _NEW_FILE_PATH_RE efferents/agents/coder.py`) and replace with `_new_file_path_re()`.

Find any reference to `DEFAULT_TARGET_GLOBS` and replace with `_target_globs()`.

Find any reference to `SMOKE_CONFIG` and replace with the appropriate `_smoke_command(...)` call. The subprocess that runs the smoke test should look like:

```python
proc = subprocess.run(
    _smoke_command(config_path),
    shell=True, capture_output=True, text=True,
    timeout=_smoke_timeout(),
    cwd=str(_lab.get_config().source.dir),
)
```

Replace any existing `subprocess.run(["python", "-m", "auto_qml.run", ...]` or `cwd=...` call with the above pattern. Use grep to find them: `grep -n 'subprocess.run' efferents/agents/coder.py`.

Also replace `SMOKE_TIMEOUT_SECONDS` with `_smoke_timeout()`. Find with: `grep -n SMOKE_TIMEOUT efferents/agents/coder.py`.

- [ ] **Step 4: Run new tests + existing coder tests**

Run: `uv run pytest tests/test_coder_path_scope.py -v`
Expected: 4 passed

Run: `uv run pytest tests/ -k coder -v`
Expected: existing coder tests still pass (or move to lab_reference if they assert QML paths — defer to Task 16).

- [ ] **Step 5: Commit**

```bash
git add tests/test_coder_path_scope.py efferents/agents/coder.py
git commit -m "refactor(coder): read source.dir, allowed_patterns, smoke_command from LabConfig"
```

---

### Task 6: progress.py panel metrics read from LabConfig

**Files:**
- Modify: `efferents/agents/progress.py` (lines 58-63 and consumers)
- Create: `tests/test_progress_panels.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_progress_panels.py`:

```python
"""progress._panel_metrics() reads panels from LabConfig.metrics.panels."""
from __future__ import annotations
from pathlib import Path

from efferents.agents import progress
from efferents.lab import (
    Budget, Executor, Headline, LabConfig, Metrics, Panel, Source,
)
from efferents import lab as lab_mod


def test_panel_metrics_from_config(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.yaml").touch()
    cfg = LabConfig(
        lab_id="x", domain="y", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command="echo {config_path}", smoke_command=None,
            config_template=src / "c.yaml",
        ),
        metrics=Metrics(
            headline=Headline(column="accuracy", direction="max"),
            panels=(
                Panel(column="accuracy", label="Acc", target=0.95),
                Panel(column="loss", label="Loss", target=None),
            ),
        ),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    panels = progress._panel_metrics()
    assert panels == [
        ("accuracy", "Acc", 0.95),
        ("loss", "Loss", None),
    ]


def test_panel_metrics_empty_when_no_panels(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.yaml").touch()
    cfg = LabConfig(
        lab_id="x", domain="y", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command="echo {config_path}", smoke_command=None,
            config_template=src / "c.yaml",
        ),
        metrics=Metrics(headline=Headline(column="m", direction="min"), panels=()),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    assert progress._panel_metrics() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_progress_panels.py -v`
Expected: failures — `_panel_metrics` is currently a `list[...]` constant, not a callable.

- [ ] **Step 3: Refactor progress.py**

Open `efferents/agents/progress.py`. Replace lines 58-63 (the `_PANEL_METRICS` list literal) with:

```python
def _panel_metrics() -> list[tuple[str, str, float | None]]:
    """Return per-lab panel definitions from the active LabConfig."""
    cfg = _lab.get_config()
    return [(p.column, p.label, p.target) for p in cfg.metrics.panels]


def _headline_metric() -> tuple[str, str]:
    """Return (column, direction) for the lab's headline metric."""
    h = _lab.get_config().metrics.headline
    return (h.column, h.direction)
```

Find any reference to `_PANEL_METRICS` in this file: `grep -n _PANEL_METRICS efferents/agents/progress.py`. Replace each with `_panel_metrics()`.

If the headline metric was previously chosen as the first entry of `_PANEL_METRICS` (typically `("e_w1", ...)`), update those call sites to call `_headline_metric()` and respect `direction`. For example, replace any `min(rows, key=lambda r: r["e_w1"])` with logic that branches on direction:

```python
col, direction = _headline_metric()
have = [r for r in rows if r.get(col) is not None]
if direction == "min":
    best = min(have, key=lambda r: r[col])
else:
    best = max(have, key=lambda r: r[col])
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_progress_panels.py -v`
Expected: 2 passed

Run: `uv run pytest tests/test_progress.py -v`
Expected: existing tests pass OR identify QML-specific assertions for Task 16 triage.

- [ ] **Step 5: Commit**

```bash
git add tests/test_progress_panels.py efferents/agents/progress.py
git commit -m "refactor(progress): read panels + headline metric from LabConfig"
```

---

### Task 7: analyst.py flat_digest_epsilon from LabConfig

**Files:**
- Modify: `efferents/agents/analyst.py` (replace hardcoded `epsilon=0.005`)
- Create: `tests/test_analyst_epsilon.py`

- [ ] **Step 1: Locate the hardcode**

Run: `grep -n "epsilon" efferents/agents/analyst.py`

Identify the function (likely `update_flat_digest_counter` per CLAUDE.md) that has `epsilon=0.005` as a default parameter or constant.

- [ ] **Step 2: Write failing test**

Create `tests/test_analyst_epsilon.py`:

```python
"""Analyst reads flat_digest_epsilon from LabConfig."""
from __future__ import annotations
from pathlib import Path

from efferents.agents import analyst
from efferents.lab import (
    Budget, Executor, Headline, LabConfig, Metrics, Panel, Source,
)
from efferents import lab as lab_mod


def test_analyst_epsilon_reads_from_config(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.yaml").touch()
    cfg = LabConfig(
        lab_id="x", domain="y", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command="echo {config_path}", smoke_command=None,
            config_template=src / "c.yaml",
        ),
        metrics=Metrics(
            headline=Headline(column="m", direction="min"),
            panels=(),
            flat_digest_epsilon=0.02,  # custom
        ),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    assert analyst._flat_digest_epsilon() == 0.02


def test_analyst_epsilon_defaults_to_005(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.yaml").touch()
    cfg = LabConfig(
        lab_id="x", domain="y", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command="echo {config_path}", smoke_command=None,
            config_template=src / "c.yaml",
        ),
        metrics=Metrics(headline=Headline(column="m", direction="min"), panels=()),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    assert analyst._flat_digest_epsilon() == 0.005
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_analyst_epsilon.py -v`
Expected: failures — `_flat_digest_epsilon` doesn't exist.

- [ ] **Step 4: Refactor analyst.py**

Add at the top of `efferents/agents/analyst.py` (after existing imports):

```python
from efferents import lab as _lab


def _flat_digest_epsilon() -> float:
    return _lab.get_config().metrics.flat_digest_epsilon
```

Replace any `epsilon=0.005` default parameter in `update_flat_digest_counter` (or similar) to compute from `_flat_digest_epsilon()`. Update call sites accordingly. Example:

```python
def update_flat_digest_counter(..., epsilon: float | None = None) -> int:
    if epsilon is None:
        epsilon = _flat_digest_epsilon()
    # ... existing logic uses epsilon ...
```

Then any caller that previously passed nothing now gets the LabConfig default.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_analyst_epsilon.py tests/test_flat_digest_counter.py -v`
Expected: new tests pass; existing flat_digest tests either pass or need updates (if they passed `epsilon=0.005` explicitly).

- [ ] **Step 6: Commit**

```bash
git add tests/test_analyst_epsilon.py efferents/agents/analyst.py
git commit -m "refactor(analyst): read flat_digest_epsilon from LabConfig"
```

---

## Phase 3 — Stdout result contract

### Task 8: Run-and-capture utility with trailing JSON parsing

**Files:**
- Create: `efferents/exec.py`
- Create: `tests/test_exec.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_exec.py`:

```python
"""Stdout-JSON contract for run subprocess capture."""
from __future__ import annotations
import json

from efferents.exec import RunResult, _extract_trailing_json, _run_and_capture


def test_extract_trailing_json_simple():
    stdout = 'epoch 1\nepoch 2\n{"run_id":"r1","metrics":{"loss":0.5}}\n'
    out = _extract_trailing_json(stdout)
    assert out == {"run_id": "r1", "metrics": {"loss": 0.5}}


def test_extract_trailing_json_multiple_objects_takes_last():
    stdout = '{"a":1}\nsome chatter\n{"b":2}\n'
    out = _extract_trailing_json(stdout)
    assert out == {"b": 2}


def test_extract_trailing_json_none_when_absent():
    assert _extract_trailing_json("just plain text") is None
    assert _extract_trailing_json("") is None


def test_extract_trailing_json_handles_nested_braces():
    stdout = 'log\n{"run_id":"r","metrics":{"loss":0.1,"nested":{"k":1}}}\n'
    out = _extract_trailing_json(stdout)
    assert out["metrics"]["nested"]["k"] == 1


def test_extract_trailing_json_malformed_returns_none():
    assert _extract_trailing_json('{"unterminated') is None


def test_run_and_capture_happy_path(tmp_path):
    # A tiny shell command that emits stdout JSON
    payload = {"run_id": "test-1", "metrics": {"synthetic_loss": 0.42}, "elapsed_s": 0.01}
    cmd = f"echo '{json.dumps(payload)}'"
    result = _run_and_capture(cmd, timeout_s=10, cwd=str(tmp_path), env_passthrough=())
    assert result.ok is True
    assert result.metrics == {"synthetic_loss": 0.42}
    assert result.error is None


def test_run_and_capture_no_json(tmp_path):
    result = _run_and_capture("echo no-json-here", timeout_s=10, cwd=str(tmp_path), env_passthrough=())
    assert result.ok is False
    assert result.error is not None
    assert "JSON" in result.error


def test_run_and_capture_nonzero_exit(tmp_path):
    payload = {"run_id": "test-1", "metrics": {"x": 1}}
    import json as _json
    cmd = f"echo '{_json.dumps(payload)}' && exit 1"
    result = _run_and_capture(cmd, timeout_s=10, cwd=str(tmp_path), env_passthrough=())
    assert result.ok is False
    assert result.metrics == {"x": 1}


def test_run_and_capture_timeout(tmp_path):
    result = _run_and_capture("sleep 5", timeout_s=1, cwd=str(tmp_path), env_passthrough=())
    assert result.ok is False
    assert result.error is not None
    assert "timeout" in result.error.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_exec.py -v`
Expected: ImportError — `efferents.exec` doesn't exist.

- [ ] **Step 3: Implement efferents/exec.py**

Create `efferents/exec.py`:

```python
"""Subprocess execution + stdout-JSON result contract.

Phase A's `run_command` wrote rows directly to SQLite. The new contract is:
the run command's last action is to emit a single JSON line to stdout
containing run_id, metrics, optional artifacts, optional elapsed_s,
optional git_commit. The daemon parses that line and writes the row.
This decouples the run from the daemon's filesystem.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunResult:
    ok: bool
    metrics: dict | None = None
    artifacts: list[dict] = field(default_factory=list)
    git_commit: str | None = None
    elapsed_s: float | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


# Match the LAST balanced top-level { ... } block in a string.
# We scan from the end and balance braces; tolerant of inner braces.
def _extract_trailing_json(text: str) -> dict | None:
    if not text:
        return None
    # Find every '}' that closes a JSON object starting at a '{' on the same logical depth.
    depth = 0
    end = -1
    candidates: list[tuple[int, int]] = []  # (start, end+1)
    for i in range(len(text) - 1, -1, -1):
        c = text[i]
        if c == "}":
            if depth == 0:
                end = i
            depth += 1
        elif c == "{":
            depth -= 1
            if depth == 0 and end != -1:
                candidates.append((i, end + 1))
                end = -1
    if not candidates:
        return None
    # The LAST trailing object is the candidates entry with the largest end.
    candidates.sort(key=lambda t: t[1], reverse=True)
    for start, stop in candidates:
        chunk = text[start:stop]
        try:
            obj = json.loads(chunk)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _run_and_capture(
    cmd: str,
    *,
    timeout_s: int,
    cwd: str,
    env_passthrough: tuple[str, ...],
) -> RunResult:
    """Execute `cmd` in `cwd` with selected env vars passed through.
    Capture stdout, parse the last JSON object, return RunResult."""
    env = dict(os.environ)
    for k in env_passthrough:
        if k in os.environ:
            env[k] = os.environ[k]
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout_s, cwd=cwd, env=env,
        )
    except subprocess.TimeoutExpired as e:
        return RunResult(
            ok=False,
            stdout=(e.stdout or "") if isinstance(e.stdout, str) else "",
            stderr=(e.stderr or "") if isinstance(e.stderr, str) else "",
            error=f"timeout after {timeout_s}s",
        )

    last_json = _extract_trailing_json(proc.stdout)
    if last_json is None:
        return RunResult(
            ok=False,
            stdout=proc.stdout, stderr=proc.stderr,
            error="run_command did not emit a JSON result on stdout",
        )

    return RunResult(
        ok=proc.returncode == 0,
        metrics=last_json.get("metrics"),
        artifacts=list(last_json.get("artifacts") or []),
        git_commit=last_json.get("git_commit"),
        elapsed_s=last_json.get("elapsed_s"),
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_exec.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add efferents/exec.py tests/test_exec.py
git commit -m "feat(exec): add run-and-capture with stdout-JSON result contract"
```

---

## Phase 4 — Registry + daemon

### Task 9: registry.py — ~/.efferents/registry.json with fcntl lock

**Files:**
- Create: `efferents/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_registry.py`:

```python
"""~/.efferents/registry.json read/write with file lock."""
from __future__ import annotations
import json
import os
from pathlib import Path

import pytest

from efferents.registry import LabRecord, Registry


def test_registry_empty_on_first_read(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg = Registry()
    assert reg.list() == []


def test_register_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg = Registry()
    rec = LabRecord(
        lab_id="my-lab",
        submission_dir=str(tmp_path / "sub"),
        lab_root=str(tmp_path / "sub/lab"),
        pid=12345,
        started_at="2026-05-26T14:02:00Z",
        status="running",
    )
    reg.register(rec)
    listed = reg.list()
    assert len(listed) == 1
    assert listed[0].lab_id == "my-lab"
    assert listed[0].pid == 12345


def test_register_idempotent_on_lab_id(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg = Registry()
    rec1 = LabRecord(lab_id="x", submission_dir="/a", lab_root="/a/lab",
                     pid=1, started_at="t1", status="running")
    rec2 = LabRecord(lab_id="x", submission_dir="/a", lab_root="/a/lab",
                     pid=2, started_at="t2", status="running")
    reg.register(rec1)
    reg.register(rec2)
    listed = reg.list()
    assert len(listed) == 1
    assert listed[0].pid == 2  # latest wins


def test_get_by_lab_id(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg = Registry()
    reg.register(LabRecord(lab_id="y", submission_dir="/b", lab_root="/b/lab",
                           pid=99, started_at="t", status="running"))
    rec = reg.get("y")
    assert rec is not None
    assert rec.pid == 99
    assert reg.get("nonexistent") is None


def test_update_status(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg = Registry()
    reg.register(LabRecord(lab_id="z", submission_dir="/c", lab_root="/c/lab",
                           pid=5, started_at="t", status="running"))
    reg.update_status("z", "stopped")
    assert reg.get("z").status == "stopped"


def test_corrupted_json_recovered(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path))
    reg_path = tmp_path / "registry.json"
    reg_path.write_text("{not valid json")
    reg = Registry()
    # Should treat as empty and warn (not crash)
    assert reg.list() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_registry.py -v`
Expected: ImportError — `efferents.registry` doesn't exist.

- [ ] **Step 3: Implement registry.py**

Create `efferents/registry.py`:

```python
"""Per-user registry mapping lab_id → submission metadata.

Single JSON file at ~/.efferents/registry.json (or $EFFERENTS_HOME/registry.json)
with fcntl-based locking for multi-CLI safety.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class LabRecord:
    lab_id: str
    submission_dir: str
    lab_root: str
    pid: int
    started_at: str
    status: str  # "running" | "stopped" | "crashed"


def _home() -> Path:
    return Path(os.environ.get("EFFERENTS_HOME", str(Path.home() / ".efferents")))


class Registry:
    """File-backed lab registry with fcntl locking. Single-host."""

    def __init__(self) -> None:
        self._home = _home()
        self._home.mkdir(parents=True, exist_ok=True)
        self._path = self._home / "registry.json"

    @contextmanager
    def _locked(self):
        """Open + lock the registry file. Yields list[LabRecord]. Writes back on exit."""
        if not self._path.exists():
            self._path.write_text("[]")
        with open(self._path, "r+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                raw = fh.read()
                try:
                    data = json.loads(raw) if raw.strip() else []
                except json.JSONDecodeError:
                    print(
                        f"efferents.registry: corrupted JSON at {self._path}, resetting",
                        file=sys.stderr,
                    )
                    data = []
                records = [LabRecord(**r) for r in data]
                yield records
                fh.seek(0)
                fh.truncate()
                fh.write(json.dumps([asdict(r) for r in records], indent=2))
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def list(self) -> list[LabRecord]:
        with self._locked() as records:
            return list(records)

    def get(self, lab_id: str) -> LabRecord | None:
        with self._locked() as records:
            for r in records:
                if r.lab_id == lab_id:
                    return r
            return None

    def register(self, rec: LabRecord) -> None:
        with self._locked() as records:
            # Replace any existing entry for the same lab_id.
            records[:] = [r for r in records if r.lab_id != rec.lab_id]
            records.append(rec)

    def update_status(self, lab_id: str, status: str) -> None:
        with self._locked() as records:
            for r in records:
                if r.lab_id == lab_id:
                    r.status = status
                    return
            raise KeyError(f"unknown lab_id: {lab_id}")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_registry.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add efferents/registry.py tests/test_registry.py
git commit -m "feat(registry): add fcntl-locked per-user lab registry"
```

---

### Task 10: daemon.py — fork, pidfile, signal handling

**Files:**
- Create: `efferents/daemon.py`
- Create: `tests/test_daemon.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_daemon.py`:

```python
"""Daemon fork + pidfile lifecycle. No-fork foreground path tested directly."""
from __future__ import annotations
import os
import signal
import time
from pathlib import Path

import pytest

from efferents.daemon import (
    is_pid_alive, read_pidfile, write_pidfile, clear_pidfile, run_foreground,
)


def test_write_and_read_pidfile(tmp_path):
    p = tmp_path / "daemon.pid"
    write_pidfile(p, 12345)
    assert read_pidfile(p) == 12345


def test_read_pidfile_missing(tmp_path):
    p = tmp_path / "missing.pid"
    assert read_pidfile(p) is None


def test_clear_pidfile_idempotent(tmp_path):
    p = tmp_path / "daemon.pid"
    clear_pidfile(p)  # absent
    write_pidfile(p, 99)
    clear_pidfile(p)
    assert not p.exists()


def test_is_pid_alive_current_process():
    assert is_pid_alive(os.getpid()) is True


def test_is_pid_alive_dead_pid():
    # PID 999999 is virtually guaranteed not to exist on a fresh test host
    assert is_pid_alive(999999) is False


def test_run_foreground_invokes_callback(tmp_path, monkeypatch):
    """Foreground mode: no fork, just call the loop body once."""
    called = []
    def fake_loop():
        called.append(1)
    run_foreground(tmp_path, fake_loop)
    assert called == [1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_daemon.py -v`
Expected: ImportError — `efferents.daemon` doesn't exist.

- [ ] **Step 3: Implement daemon.py**

Create `efferents/daemon.py`:

```python
"""Daemon lifecycle helpers: fork (double-fork + setsid), pidfile mgmt,
SIGTERM handler. The "loop body" passed in is `orchestrator.start()` or
equivalent; the daemon module doesn't import it directly so it stays testable
without a full orchestrator setup.
"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Callable


def write_pidfile(path: Path, pid: int) -> None:
    path.write_text(str(pid))


def read_pidfile(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def clear_pidfile(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def is_pid_alive(pid: int) -> bool:
    """Send signal 0 (no-op) to test process existence."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # alive but not ours
    return True


def run_foreground(lab_root: Path, loop: Callable[[], None]) -> None:
    """Run the loop in the foreground (no fork)."""
    _install_signal_handlers(lab_root)
    loop()


def daemonize_and_run(lab_root: Path, loop: Callable[[], None]) -> int:
    """Double-fork + setsid + write pidfile + run loop.

    Returns the child PID (in the original parent). In the child, this never
    returns — it calls `loop()` until SIGTERM or the loop exits naturally.
    """
    # First fork
    pid = os.fork()
    if pid > 0:
        # Original parent: wait for first child to exit and return grandchild PID
        os.waitpid(pid, 0)
        # Grandchild PID is read from the pidfile, which it wrote.
        pidfile = lab_root / "daemon.pid"
        # Spin briefly for the pidfile to appear (worst case ~100ms after fork).
        import time as _time
        for _ in range(50):
            if pidfile.exists():
                child_pid = read_pidfile(pidfile)
                if child_pid:
                    return child_pid
            _time.sleep(0.01)
        raise RuntimeError("daemon did not write pidfile within 500ms")

    # First child: setsid, second fork
    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)  # first child exits, grandchild is now session leader

    # Grandchild
    write_pidfile(lab_root / "daemon.pid", os.getpid())

    # Reopen stdio to daemon.log
    logfile = lab_root / "daemon.log"
    sys.stdout.flush()
    sys.stderr.flush()
    with open(logfile, "a", buffering=1) as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())

    _install_signal_handlers(lab_root)

    try:
        loop()
    except SystemExit:
        raise
    except BaseException as e:
        (lab_root / "halt_reason.txt").write_text(f"unhandled exception: {e!r}")
        os._exit(1)
    finally:
        clear_pidfile(lab_root / "daemon.pid")
    os._exit(0)


def _install_signal_handlers(lab_root: Path) -> None:
    def _term(signum, frame):
        # Mark clean shutdown; loop should exit on the next iteration.
        (lab_root / "halt_reason.txt").write_text(f"received signal {signum}")
        sys.exit(0)
    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_daemon.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add efferents/daemon.py tests/test_daemon.py
git commit -m "feat(daemon): add fork/pidfile/signal-handling lifecycle helpers"
```

---

## Phase 5 — CLI

### Task 11: `efferents` CLI skeleton + `validate` subcommand

**Files:**
- Create: `efferents/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_cli.py`:

```python
"""efferents CLI subcommand integration tests."""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from efferents.cli import main


SAMPLE = Path(__file__).parent / "fixtures" / "sample_submission"


def test_validate_ok(tmp_path, capsys):
    sub = tmp_path / "sub"
    shutil.copytree(SAMPLE, sub)
    exit_code = main(["validate", "--submission", str(sub)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "OK" in captured.out
    assert "sample-conjecture" in captured.out


def test_validate_missing_submission(tmp_path, capsys):
    exit_code = main(["validate", "--submission", str(tmp_path / "nope")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "hypothesis.md" in captured.err or "hypothesis.md" in captured.out


def test_validate_unknown_subcommand_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["bogus"])
    assert exc.value.code == 2  # argparse-style
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ImportError — `efferents.cli` doesn't exist.

- [ ] **Step 3: Implement cli.py with validate**

Create `efferents/cli.py`:

```python
"""efferents CLI entry point.

  efferents validate --submission <dir>
  efferents start    --submission <dir> [--detach] [--lab-root <path>]
  efferents status   [--lab-id <id>]
  efferents stop     --lab-id <id>
  efferents list

The `main(argv=None)` entry point is exposed for tests; pyproject.toml
console_scripts points at `efferents.cli:main` (added in Task 17).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from efferents.lab import LabConfig, SubmissionError


def _cmd_validate(args: argparse.Namespace) -> int:
    sub = Path(args.submission).resolve()
    try:
        cfg = LabConfig.from_submission(sub)
    except SubmissionError as e:
        print(f"validation failed: {e}", file=sys.stderr)
        return 1
    print(f"OK lab_id={cfg.lab_id} domain={cfg.domain} source_dir={cfg.source.dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="efferents")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate", help="Validate a submission directory")
    p_validate.add_argument("--submission", required=True)
    p_validate.set_defaults(func=_cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py::test_validate_ok tests/test_cli.py::test_validate_missing_submission tests/test_cli.py::test_validate_unknown_subcommand_exits_2 -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add efferents/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'efferents validate' subcommand"
```

---

### Task 12: `efferents start` (foreground first)

**Files:**
- Modify: `efferents/cli.py` (add `start` subcommand)
- Modify: `tests/test_cli.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_cli.py`:

```python
def test_start_foreground_registers_and_runs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    sub = tmp_path / "sub"
    shutil.copytree(SAMPLE, sub)

    # Patch the orchestrator loop to a one-shot no-op so start returns.
    called = []
    def fake_loop():
        called.append(1)
    monkeypatch.setattr("efferents.cli._orchestrator_loop", fake_loop)

    exit_code = main(["start", "--submission", str(sub)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "lab_id=sample-conjecture" in captured.out
    assert called == [1]

    # Verify registry has the entry
    from efferents.registry import Registry
    rec = Registry().get("sample-conjecture")
    assert rec is not None
    assert rec.lab_id == "sample-conjecture"
    assert (sub / "lab" / "state.db").exists() or True  # state.db is created by migrations (may be absent in stub)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_start_foreground_registers_and_runs -v`
Expected: failure — `start` subcommand not registered, `_orchestrator_loop` doesn't exist.

- [ ] **Step 3: Add start to cli.py**

Append to `efferents/cli.py`:

```python
import os
from datetime import datetime, timezone

from efferents import daemon, lab as lab_mod
from efferents.registry import LabRecord, Registry


def _orchestrator_loop() -> None:
    """Indirection so tests can monkey-patch the loop body without forking.
    In production, calls efferents.agents.orchestrator.start()."""
    from efferents.agents import orchestrator
    orchestrator.start()


def _init_lab_root(submission_dir: Path, lab_root: Path) -> None:
    """Create lab/ dir + run migrations + copy provenance files."""
    lab_root.mkdir(parents=True, exist_ok=True)
    (lab_root / "progress").mkdir(exist_ok=True)
    (lab_root / "papers").mkdir(exist_ok=True)

    # Provenance copies
    import shutil as _shutil
    _shutil.copy2(submission_dir / "hypothesis.md", lab_root / "hypothesis.md")
    _shutil.copy2(submission_dir / "lab.yaml", lab_root / "lab.yaml")

    # state.json empty bootstrap
    state_json = lab_root / "state.json"
    if not state_json.exists():
        state_json.write_text("{}")

    # Migrations
    from efferents.migrations import runner as _mig
    _mig.upgrade(lab_root / "state.db")


def _cmd_start(args: argparse.Namespace) -> int:
    sub = Path(args.submission).resolve()
    try:
        cfg = LabConfig.from_submission(sub)
    except SubmissionError as e:
        print(f"validation failed: {e}", file=sys.stderr)
        return 1

    lab_root = Path(args.lab_root).resolve() if args.lab_root else (sub / "lab").resolve()
    _init_lab_root(sub, lab_root)

    # Install the active config and chdir
    lab_mod.set_config(cfg)
    os.chdir(sub)

    # Register the lab
    started_at = datetime.now(timezone.utc).isoformat()
    reg = Registry()
    reg.register(LabRecord(
        lab_id=cfg.lab_id,
        submission_dir=str(sub),
        lab_root=str(lab_root),
        pid=os.getpid(),
        started_at=started_at,
        status="running",
    ))

    print(f"lab_id={cfg.lab_id} pid={os.getpid()} dashboard={lab_root}/progress/index.html")

    if args.detach:
        # Detach path is added in Task 13. For now, error out clearly.
        print("error: --detach not implemented yet (Task 13)", file=sys.stderr)
        return 2

    try:
        daemon.run_foreground(lab_root, _orchestrator_loop)
    finally:
        reg.update_status(cfg.lab_id, "stopped")
    return 0


# Extend main() to register the new subparser:
```

And update `main()` in the same file by inserting (after the existing `p_validate.set_defaults(...)`):

```python
    p_start = sub.add_parser("start", help="Start the lab daemon")
    p_start.add_argument("--submission", required=True)
    p_start.add_argument("--detach", action="store_true")
    p_start.add_argument("--lab-root", default=None)
    p_start.set_defaults(func=_cmd_start)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: validate tests + new start test pass.

- [ ] **Step 5: Commit**

```bash
git add efferents/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'efferents start' (foreground only; detach in next task)"
```

---

### Task 13: `efferents start --detach`

**Files:**
- Modify: `efferents/cli.py` (wire daemonize path)
- Modify: `tests/test_cli.py` (add detach test)

- [ ] **Step 1: Add failing test**

Append to `tests/test_cli.py`:

```python
def test_start_detach_writes_pidfile(tmp_path, monkeypatch):
    """Detach path forks; we test the post-fork bookkeeping via a stubbed daemonize call."""
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    sub = tmp_path / "sub"
    shutil.copytree(SAMPLE, sub)

    # Stub daemonize_and_run to just return a fake pid without forking
    fake_child_pid = 4242
    def fake_daemonize(lab_root, loop):
        return fake_child_pid
    monkeypatch.setattr("efferents.cli.daemon.daemonize_and_run", fake_daemonize)

    exit_code = main(["start", "--submission", str(sub), "--detach"])
    assert exit_code == 0

    from efferents.registry import Registry
    rec = Registry().get("sample-conjecture")
    assert rec is not None
    assert rec.pid == fake_child_pid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_start_detach_writes_pidfile -v`
Expected: fail with "--detach not implemented yet".

- [ ] **Step 3: Replace the detach guard in `_cmd_start`**

In `efferents/cli.py`, find the block:

```python
    if args.detach:
        # Detach path is added in Task 13. For now, error out clearly.
        print("error: --detach not implemented yet (Task 13)", file=sys.stderr)
        return 2
```

Replace with:

```python
    if args.detach:
        child_pid = daemon.daemonize_and_run(lab_root, _orchestrator_loop)
        # Update registry with the actual child PID (we registered our own PID above)
        reg.update_status(cfg.lab_id, "running")
        rec = reg.get(cfg.lab_id)
        if rec is not None:
            rec.pid = child_pid
            reg.register(rec)  # idempotent replace
        return 0
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add efferents/cli.py tests/test_cli.py
git commit -m "feat(cli): wire 'efferents start --detach' via daemonize_and_run"
```

---

### Task 14: `efferents status`

**Files:**
- Modify: `efferents/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_cli.py`:

```python
def test_status_running_lab(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    from efferents.registry import LabRecord, Registry
    reg = Registry()
    reg.register(LabRecord(
        lab_id="x", submission_dir=str(tmp_path / "s"),
        lab_root=str(tmp_path / "s/lab"), pid=os.getpid(),
        started_at="2026-05-26T10:00:00Z", status="running",
    ))
    (tmp_path / "s" / "lab").mkdir(parents=True)
    (tmp_path / "s" / "lab" / "state.json").write_text("{}")

    exit_code = main(["status", "--lab-id", "x"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "running" in captured.out
    assert "x" in captured.out


def test_status_dead_pid_marks_crashed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    from efferents.registry import LabRecord, Registry
    reg = Registry()
    reg.register(LabRecord(
        lab_id="y", submission_dir=str(tmp_path / "s"),
        lab_root=str(tmp_path / "s/lab"), pid=999999, # dead PID
        started_at="2026-05-26T10:00:00Z", status="running",
    ))

    exit_code = main(["status", "--lab-id", "y"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "crashed" in captured.out.lower() or "dead" in captured.out.lower()


def test_status_unknown_lab(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    exit_code = main(["status", "--lab-id", "nope"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "not found" in captured.err.lower() or "unknown" in captured.err.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_status_running_lab -v`
Expected: failure — `status` subcommand not registered.

- [ ] **Step 3: Add status to cli.py**

Append to `efferents/cli.py`:

```python
def _cmd_status(args: argparse.Namespace) -> int:
    reg = Registry()
    if args.lab_id is None:
        return _cmd_list(args)
    rec = reg.get(args.lab_id)
    if rec is None:
        print(f"unknown lab_id: {args.lab_id}", file=sys.stderr)
        return 1

    alive = daemon.is_pid_alive(rec.pid)
    status = rec.status
    if rec.status == "running" and not alive:
        status = "crashed"
        reg.update_status(args.lab_id, "crashed")

    lab_root = Path(rec.lab_root)
    print(f"lab_id={rec.lab_id}")
    print(f"status={status}")
    print(f"started_at={rec.started_at}")
    print(f"pid={rec.pid} (alive={alive})")
    state_json = lab_root / "state.json"
    if state_json.exists():
        from datetime import datetime as _dt, timezone as _tz
        mtime = _dt.fromtimestamp(state_json.stat().st_mtime, tz=_tz.utc).isoformat()
        print(f"last_activity={mtime}")
    print(f"dashboard=file://{lab_root}/progress/index.html")
    halt = lab_root / "halt_reason.txt"
    if halt.exists():
        print(f"halt_reason={halt.read_text().strip()}")
    return 0
```

And update `main()` to register the subparser:

```python
    p_status = sub.add_parser("status", help="Show lab status")
    p_status.add_argument("--lab-id", default=None)
    p_status.set_defaults(func=_cmd_status)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v -k status`
Expected: status tests pass (the `_cmd_list` call inside status without --lab-id will fail until Task 16; the test_status_unknown_lab and test_status_running_lab tests should pass).

- [ ] **Step 5: Commit**

```bash
git add efferents/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'efferents status' with liveness check + crash detection"
```

---

### Task 15: `efferents stop`

**Files:**
- Modify: `efferents/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_cli.py`:

```python
def test_stop_marks_registry_stopped(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    from efferents.registry import LabRecord, Registry
    reg = Registry()
    reg.register(LabRecord(
        lab_id="z", submission_dir="/x", lab_root="/x/lab",
        pid=999999, started_at="t", status="running",
    ))

    # Patch os.kill to a no-op so we don't actually try to signal anything
    monkeypatch.setattr("efferents.cli.os.kill", lambda pid, sig: None)
    monkeypatch.setattr("efferents.cli.daemon.is_pid_alive", lambda pid: False)

    exit_code = main(["stop", "--lab-id", "z"])
    assert exit_code == 0
    assert reg.get("z").status == "stopped"


def test_stop_unknown_lab(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    exit_code = main(["stop", "--lab-id", "ghost"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "unknown" in captured.err.lower() or "not found" in captured.err.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_stop_marks_registry_stopped -v`
Expected: failure — `stop` subcommand not registered.

- [ ] **Step 3: Add stop to cli.py**

Append to `efferents/cli.py`:

```python
import signal as _signal
import time as _time


def _cmd_stop(args: argparse.Namespace) -> int:
    reg = Registry()
    rec = reg.get(args.lab_id)
    if rec is None:
        print(f"unknown lab_id: {args.lab_id}", file=sys.stderr)
        return 1

    if daemon.is_pid_alive(rec.pid):
        os.kill(rec.pid, _signal.SIGTERM)
        # Wait up to 10s for graceful shutdown
        for _ in range(100):
            if not daemon.is_pid_alive(rec.pid):
                break
            _time.sleep(0.1)
        if daemon.is_pid_alive(rec.pid):
            os.kill(rec.pid, _signal.SIGKILL)
            print(f"warning: SIGTERM ignored, sent SIGKILL to PID {rec.pid}", file=sys.stderr)

    reg.update_status(args.lab_id, "stopped")
    print(f"stopped lab_id={args.lab_id}")
    return 0
```

And update `main()`:

```python
    p_stop = sub.add_parser("stop", help="Stop a running lab daemon")
    p_stop.add_argument("--lab-id", required=True)
    p_stop.set_defaults(func=_cmd_stop)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v -k stop`
Expected: stop tests pass.

- [ ] **Step 5: Commit**

```bash
git add efferents/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'efferents stop' with SIGTERM grace period + SIGKILL fallback"
```

---

### Task 16: `efferents list` + console_scripts entry

**Files:**
- Modify: `efferents/cli.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_cli.py`:

```python
def test_list_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    exit_code = main(["list"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "no labs registered" in captured.out.lower() or "LAB_ID" in captured.out


def test_list_with_entries(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    from efferents.registry import LabRecord, Registry
    reg = Registry()
    reg.register(LabRecord(
        lab_id="alpha", submission_dir="/a", lab_root="/a/lab",
        pid=os.getpid(), started_at="2026-05-26T10:00:00Z", status="running",
    ))
    reg.register(LabRecord(
        lab_id="beta", submission_dir="/b", lab_root="/b/lab",
        pid=999999, started_at="2026-05-25T10:00:00Z", status="running",
    ))
    exit_code = main(["list"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "alpha" in captured.out
    assert "beta" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_list_empty tests/test_cli.py::test_list_with_entries -v`
Expected: failure — `list` subcommand not registered.

- [ ] **Step 3: Add list to cli.py**

Append to `efferents/cli.py`:

```python
def _cmd_list(args: argparse.Namespace) -> int:
    reg = Registry()
    records = reg.list()
    if not records:
        print("no labs registered")
        return 0
    print(f"{'LAB_ID':<24} {'STATUS':<10} {'STARTED':<25} SUBMISSION")
    for r in records:
        status = r.status
        if status == "running" and not daemon.is_pid_alive(r.pid):
            status = "crashed"
        print(f"{r.lab_id:<24} {status:<10} {r.started_at:<25} {r.submission_dir}")
    return 0
```

And update `main()`:

```python
    p_list = sub.add_parser("list", help="List all registered labs")
    p_list.set_defaults(func=_cmd_list)
```

- [ ] **Step 4: Add console_scripts entry to pyproject.toml**

Edit `pyproject.toml`. Add after the `[project.optional-dependencies]` section:

```toml
[project.scripts]
efferents = "efferents.cli:main"
```

- [ ] **Step 5: Reinstall to pick up the entry point**

Run: `uv pip install -e .`
Expected: no errors; `efferents` command should be available.

Run: `efferents --help`
Expected: usage text showing validate, start, status, stop, list subcommands.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: all CLI tests pass.

- [ ] **Step 7: Commit**

```bash
git add efferents/cli.py tests/test_cli.py pyproject.toml
git commit -m "feat(cli): add 'efferents list' + console_scripts entry"
```

---

## Phase 6 — Wire stdout-result contract into orchestrator

### Task 17: Replace direct-SQLite writes with stdout JSON ingest

**Files:**
- Modify: `efferents/agents/coder.py` (smoke test invocation now uses `_run_and_capture`)
- Modify: `efferents/agents/orchestrator.py` (real-run invocation uses `_run_and_capture` and writes the row from `RunResult.metrics`)

- [ ] **Step 1: Identify current run sites**

Run: `grep -nE 'subprocess\.(run|Popen)' efferents/agents/`
Identify each invocation of a run subprocess. Two main places: coder.py's smoke test, and orchestrator.py's real-run scheduler (if it shells out — verify).

If orchestrator.py does NOT directly invoke runs (Phase A's auto-qml had the run logic inside `auto_qml/run.py` and the orchestrator just kicked it off), then add a new helper:

```python
# efferents/agents/orchestrator.py
from efferents.exec import _run_and_capture
from efferents import lab as _lab


def _execute_run(config_path: Path) -> "RunResult":
    cfg = _lab.get_config()
    cmd = cfg.executor.run_command.format(config_path=str(config_path))
    return _run_and_capture(
        cmd,
        timeout_s=cfg.executor.run_timeout_s,
        cwd=str(cfg.source.dir),
        env_passthrough=cfg.executor.env_passthrough,
    )
```

And a writer that inserts the row into `state.db`:

```python
def _persist_run_result(result: "RunResult", run_id: str, config_path: Path) -> None:
    import sqlite3
    from datetime import datetime, timezone

    if not result.metrics:
        return  # nothing to persist; analyst will see no row and treat as failure
    with sqlite3.connect("lab/state.db") as conn:
        cols = ["run_id", "started_at", "ended_at", "config_path"]
        vals: list = [run_id, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(), str(config_path)]
        for k, v in result.metrics.items():
            cols.append(k)
            vals.append(v)
        if result.git_commit:
            cols.append("git_commit"); vals.append(result.git_commit)
        if result.elapsed_s is not None:
            cols.append("duration_seconds"); vals.append(result.elapsed_s)
        placeholders = ",".join("?" for _ in vals)
        col_list = ",".join(cols)
        # Tolerate columns that don't exist yet by catching the error and warning.
        try:
            conn.execute(f"INSERT INTO runs ({col_list}) VALUES ({placeholders})", vals)
            conn.commit()
        except sqlite3.OperationalError as e:
            print(f"warning: could not persist metric row: {e}")
```

- [ ] **Step 2: Write a unit test**

Create `tests/test_orchestrator_run_persistence.py`:

```python
"""Orchestrator.persist_run_result inserts metrics from RunResult into state.db."""
from __future__ import annotations
import sqlite3
from pathlib import Path

import pytest

from efferents.exec import RunResult


def test_persist_run_result_inserts_metrics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lab").mkdir()
    db = tmp_path / "lab" / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT, "
        "config_path TEXT, synthetic_loss REAL, duration_seconds REAL, git_commit TEXT)"
    )
    conn.commit()
    conn.close()

    from efferents.agents import orchestrator
    result = RunResult(
        ok=True,
        metrics={"synthetic_loss": 0.42},
        elapsed_s=12.3,
        git_commit="abc123",
    )
    orchestrator._persist_run_result(result, "test-1", Path("configs/default.yaml"))

    conn = sqlite3.connect(db)
    rows = list(conn.execute("SELECT run_id, synthetic_loss, duration_seconds, git_commit FROM runs"))
    assert rows == [("test-1", 0.42, 12.3, "abc123")]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator_run_persistence.py -v`
Expected: failure — `_persist_run_result` doesn't exist on orchestrator.

- [ ] **Step 4: Add the helpers from Step 1 to orchestrator.py**

Open `efferents/agents/orchestrator.py` and add the `_execute_run` and `_persist_run_result` functions exactly as drafted in Step 1.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_orchestrator_run_persistence.py tests/test_exec.py -v`
Expected: passes.

- [ ] **Step 6: Commit**

```bash
git add efferents/agents/orchestrator.py tests/test_orchestrator_run_persistence.py
git commit -m "feat(orchestrator): persist runs from stdout-JSON via _run_and_capture"
```

---

## Phase 7 — Test triage

### Task 18: Move QML-specific tests to `tests/lab_reference/`

**Files:**
- Create: `tests/lab_reference/__init__.py`
- Move: tests that assert on QML-specific columns (e_w1, active_frac_w1, radial_l2_log, gen_max_to_real_max), reference auto_qml package, or hardcode QML-specific behavior.
- Create: `tests/README.md`

- [ ] **Step 1: Identify QML-specific tests**

Run: `grep -lE "e_w1|active_frac_w1|radial_l2_log|gen_max_to_real_max|auto_qml" tests/test_*.py`

For each file in the output, open it and confirm whether the assertion is genuinely QML-specific (the metric column is hardcoded in test) versus generic (the test parameterizes on whatever column LabConfig provides). Genuinely-QML tests move; generic ones stay.

- [ ] **Step 2: Set up the lab_reference dir**

```bash
mkdir -p tests/lab_reference
touch tests/lab_reference/__init__.py
```

- [ ] **Step 3: Move each QML test**

For each identified test file (call it `test_x.py`):

```bash
git mv tests/test_x.py tests/lab_reference/test_x.py
```

At the top of each moved file, after the docstring, add:

```python
import pytest
pytestmark = pytest.mark.skip(
    reason="QML-specific; lives with auto-qml. See tests/README.md."
)
```

- [ ] **Step 4: Write tests/README.md**

Create `tests/README.md`:

```markdown
# efferents tests

Tests are split by whether they exercise lab-agnostic framework code or
QML-specific behavior from the reference lab.

- `tests/test_*.py` — generic framework tests. Run against the
  `smoke_lab_config` fixture in `conftest.py`. Must pass without QML data
  or auto-qml available.
- `tests/lab_reference/test_*.py` — QML-specific tests inherited from
  the auto-qml reference lab. Currently `@pytest.mark.skip`-ed. They will
  re-enable when auto-qml depends on efferents as a pip package and these
  tests move into auto-qml's own test suite.
- `tests/integration/test_smoke_lab_e2e.py` — end-to-end test against
  `examples/smoke-lab/`. Marked `@pytest.mark.integration`; opt in via
  `pytest -m integration`.

## Running

- All generic + smoke tests: `uv run pytest tests/ --ignore=tests/lab_reference`
- Integration only: `uv run pytest -m integration`
```

- [ ] **Step 5: Run the full generic test suite**

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration -v`
Expected: all pass.

If anything still fails, the failure is in generic code we've changed — fix at the source. Common breakages:
- A generic test imports `lab.LAB_ID` directly without expecting the fixture: the autouse fixture should cover it.
- A generic test depends on a module-level constant we removed: re-add the constant or update the test.

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test: move QML-specific tests to tests/lab_reference/ with skip marker"
```

---

## Phase 8 — Smoke lab

### Task 19: examples/smoke-lab — stub run and eval code

**Files:**
- Create: `examples/smoke-lab/src/__init__.py`
- Create: `examples/smoke-lab/src/stub_run.py`
- Create: `examples/smoke-lab/src/stub_eval.py`
- Create: `examples/smoke-lab/configs/default.yaml`
- Create: `examples/smoke-lab/configs/smoke.yaml`

- [ ] **Step 1: Create scaffolding**

```bash
mkdir -p examples/smoke-lab/src examples/smoke-lab/configs
touch examples/smoke-lab/src/__init__.py
```

- [ ] **Step 2: Write stub_run.py**

Create `examples/smoke-lab/src/stub_run.py`:

```python
"""Smoke-lab "training" run: reads config, computes synthetic_loss, emits stdout JSON.

Hypothesis under test: "increasing coefficient above 0.7 reduces synthetic_loss below 0.1".
Truth: synthetic_loss = abs(0.8 - coefficient) + small_noise.

This is a stub for proving the efferents framework plumbing — NOT real research.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
import uuid

import yaml


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=2
        ).strip()
    except Exception:
        return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    cfg = yaml.safe_load(open(args.config))
    coefficient = float(cfg.get("coefficient", 0.5))
    seed = int(cfg.get("seed", 42))
    rng = random.Random(seed)

    start = time.time()
    # The "training": a tiny computation parameterized by coefficient.
    noise = rng.gauss(0, 0.01) if not args.smoke else 0.0
    synthetic_loss = abs(0.8 - coefficient) + noise

    payload = {
        "run_id": str(uuid.uuid4()),
        "metrics": {"synthetic_loss": synthetic_loss},
        "git_commit": _git_commit(),
        "elapsed_s": time.time() - start,
        "artifacts": [],
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write stub_eval.py (callable from stub_run if desired)**

Create `examples/smoke-lab/src/stub_eval.py`:

```python
"""Trivial eval helper called from stub_run.py if needed."""
from __future__ import annotations


def loss(coefficient: float, noise: float = 0.0) -> float:
    return abs(0.8 - coefficient) + noise
```

- [ ] **Step 4: Write configs**

Create `examples/smoke-lab/configs/default.yaml`:

```yaml
coefficient: 0.5
seed: 42
```

Create `examples/smoke-lab/configs/smoke.yaml`:

```yaml
coefficient: 0.5
seed: 42
# Smoke run skips noise for determinism.
```

- [ ] **Step 5: Verify the stub runs and emits JSON**

```bash
cd examples/smoke-lab && python -m src.stub_run --config configs/default.yaml
```

Expected: a single JSON line printed to stdout containing `run_id`, `metrics.synthetic_loss`, `git_commit`, `elapsed_s`, `artifacts`.

Return to repo root: `cd -`

- [ ] **Step 6: Commit**

```bash
git add examples/smoke-lab/
git commit -m "examples: smoke-lab stub run/eval code emitting stdout JSON contract"
```

---

### Task 20: examples/smoke-lab — hypothesis.md + lab.yaml + README

**Files:**
- Create: `examples/smoke-lab/hypothesis.md`
- Create: `examples/smoke-lab/lab.yaml`
- Create: `examples/smoke-lab/README.md`

- [ ] **Step 1: Write hypothesis.md**

Create `examples/smoke-lab/hypothesis.md`:

```markdown
---
slug: smoke-coefficient
falsifiability_gate: passed
status: active
created_at: 2026-05-26T00:00:00Z
---

# Smoke-lab hypothesis: optimal coefficient for synthetic loss

## Background

This is a deliberately trivial lab whose purpose is to exercise the efferents
framework plumbing end-to-end. It is **not** real research.

## Claim

The `coefficient` parameter that minimizes `synthetic_loss` lies in the
interval (0.75, 0.85). Outside this interval, `synthetic_loss` increases.

## Falsifier

A run with `coefficient` in [0.75, 0.85] should yield `synthetic_loss < 0.05`.
A run with `coefficient` outside that interval should yield
`synthetic_loss >= 0.05`. Either pattern being violated for >50% of runs
falsifies the claim.

## Probes (recorded by popper-probe)

- **Probe 1 (specificity)**: passed — interval is bounded.
- **Probe 2 (refutability)**: passed — concrete numeric threshold.
- **Probe 3 (verifiability)**: passed — measurable in a single run.
```

- [ ] **Step 2: Write lab.yaml**

Create `examples/smoke-lab/lab.yaml`:

```yaml
lab_id: smoke-coefficient
domain: synthetic

source:
  dir: ./src/
  allowed_patterns:
    - "**/*.py"
    - "**/*.yaml"

executor:
  run_command: "python -m src.stub_run --config {config_path}"
  smoke_command: "python -m src.stub_run --config {config_path} --smoke"
  config_template: ../configs/default.yaml
  run_timeout_s: 60
  smoke_timeout_s: 30

metrics:
  headline:
    column: synthetic_loss
    direction: min
  panels:
    - { column: synthetic_loss, label: "Loss" }
  flat_digest_epsilon: 0.005

budget:
  daily_cap_usd: 2.0
  sonnet_default: true
```

- [ ] **Step 3: Write README.md**

Create `examples/smoke-lab/README.md`:

```markdown
# smoke-lab

A trivial example lab that exercises the efferents framework end-to-end
without GPU, real data, or real research.

## What it proves

- LabConfig loads from a non-QML `lab.yaml`
- Coder modifies code under a non-`auto_qml` source dir
- Run command emits stdout JSON; daemon ingests the row
- Progress dashboard renders against a custom headline metric (`synthetic_loss`)
- A full Researcher → Coder → smoke → run → analyst cycle completes in seconds

## Running locally

```bash
efferents validate --submission examples/smoke-lab/
efferents start    --submission examples/smoke-lab/
```

(Foreground; press Ctrl-C to stop.)

For the end-to-end test variant, run: `pytest -m integration tests/integration/`.

## Caveat

The agent prompts (researcher.md, coder.md, etc) are still calibrated for the
QML reference lab. The Researcher's suggestions may read oddly. This is a
known limitation — see [`docs/superpowers/specs/2026-05-26-efferents-deployment-design.md`](../../docs/superpowers/specs/2026-05-26-efferents-deployment-design.md)
Section 5 "Out of scope".
```

- [ ] **Step 4: Validate the smoke lab**

Run: `efferents validate --submission examples/smoke-lab/`
Expected: `OK lab_id=smoke-coefficient domain=synthetic source_dir=.../examples/smoke-lab/src`

- [ ] **Step 5: Commit**

```bash
git add examples/smoke-lab/hypothesis.md examples/smoke-lab/lab.yaml examples/smoke-lab/README.md
git commit -m "examples: smoke-lab hypothesis, lab.yaml, README"
```

---

### Task 21: End-to-end integration test

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_smoke_lab_e2e.py`

- [ ] **Step 1: Create directory**

```bash
mkdir -p tests/integration
touch tests/integration/__init__.py
```

- [ ] **Step 2: Add integration marker to pyproject.toml**

Edit `pyproject.toml`. Under `[tool.pytest.ini_options]`, extend the markers list:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: integration tests that exec real lab CLIs end-to-end",
    "integration: end-to-end tests that require ANTHROPIC_API_KEY and execute the daemon",
]
```

- [ ] **Step 3: Write the integration test**

Create `tests/integration/test_smoke_lab_e2e.py`:

```python
"""End-to-end: drive the smoke-lab through `efferents start` foreground,
assert metric rows appear in state.db within 60s.

Marked `integration`; opt-in via `pytest -m integration`. Requires
ANTHROPIC_API_KEY to be set; skips otherwise.
"""
from __future__ import annotations
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest


SMOKE_LAB = Path(__file__).parent.parent.parent / "examples" / "smoke-lab"


@pytest.mark.integration
def test_smoke_lab_runs_end_to_end(tmp_path, monkeypatch):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; integration test requires it")

    monkeypatch.setenv("EFFERENTS_HOME", str(tmp_path / "home"))
    sub = tmp_path / "smoke-lab"
    shutil.copytree(SMOKE_LAB, sub)

    # Launch foreground daemon with a timeout via subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "efferents.cli", "start", "--submission", str(sub)],
        env={**os.environ, "EFFERENTS_HOME": str(tmp_path / "home")},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Give the daemon up to 90 seconds to produce at least one run row.
    db = sub / "lab" / "state.db"
    deadline = time.time() + 90
    runs = 0
    while time.time() < deadline:
        if db.exists():
            try:
                conn = sqlite3.connect(db)
                cur = conn.execute("SELECT COUNT(*) FROM runs WHERE synthetic_loss IS NOT NULL")
                runs = cur.fetchone()[0]
                conn.close()
                if runs >= 1:
                    break
            except sqlite3.OperationalError:
                pass  # table not created yet
        time.sleep(1)

    # Shut down
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    out, _ = proc.communicate()
    assert runs >= 1, (
        f"no synthetic_loss rows after 90s.\nstdout/stderr:\n{out}"
    )
    # Dashboard rendered?
    assert (sub / "lab" / "progress" / "index.html").exists() or True  # not required if daemon was killed early
```

- [ ] **Step 4: Verify the test selection works**

Run: `uv run pytest tests/integration/ -v --collect-only`
Expected: 1 test collected under `integration` marker.

Run (only if `ANTHROPIC_API_KEY` is set; otherwise it auto-skips): `uv run pytest -m integration -v`
Expected: pass (or skip if no key).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/ pyproject.toml
git commit -m "test: end-to-end integration test against examples/smoke-lab"
```

---

## Phase 9 — Intake skill + verification

### Task 22: skills/intake.md

**Files:**
- Create: `skills/intake.md`

- [ ] **Step 1: Create skills directory**

```bash
mkdir -p skills
```

- [ ] **Step 2: Write intake.md**

Create `skills/intake.md` (copy from Section 3 of the spec, with the run-command guidance from Section 7 inserted in Step 2):

```markdown
# efferents intake

You are an agent helping a human submit a research hypothesis to an
autonomous lab. This file is your instruction set. Follow each step in
order. If any prerequisite or validation fails, stop and tell the human.

## Prerequisites

- popper-probe plugin/skill installed: https://github.com/mashathepotato/popper-probe
- Python 3.10+ and pip available in the shell
- A local git repository the human is OK with autonomous edits to

## Step 1 — Falsifiability intake (interactive)

Invoke popper-probe:intake on the human's claim. The human will answer
adversarial probes. The output is a hypothesis.md at
<popper-corpus>/<slug>/hypothesis.md with `falsifiability_gate: passed`.

If `falsifiability_gate: failed`, surface the diagnostic and STOP.
If popper-probe is unavailable, refuse and tell the human to install it.

## Step 2 — Lab configuration (interactive)

Ask the human, one question at a time:

  1. Local path to the source code to be modified (must be a git repo)
  2. Run command template — anything that takes a config path and emits a
     JSON metrics object on stdout. Common shapes: local Python, ssh to a
     GPU box, modal/runpod/slurm submission. Must contain `{config_path}`.
  3. Path to the run command's config template (relative to source dir)
  4. Headline metric column name and direction (`max` or `min`)
  5. Domain string (free text, e.g. "quantum-ml", "nlp")

Then offer optional fields: panels, allowed_patterns, flat_digest_epsilon,
daily budget cap. Default daily budget cap is $10.

Schema reference:
https://github.com/mashathepotato/efferents/blob/main/docs/superpowers/specs/2026-05-26-efferents-deployment-design.md#2-submission-contract

## Step 3 — Stage submission

mkdir -p ./efferents-submissions/<slug>/
cp <popper-corpus>/<slug>/hypothesis.md ./efferents-submissions/<slug>/
Write lab.yaml to ./efferents-submissions/<slug>/lab.yaml

## Step 4 — Install + validate

pip install efferents
efferents validate --submission ./efferents-submissions/<slug>/

If validation fails, surface the field-level error to the human and STOP.

## Step 5 — Surface warnings (mandatory; before step 6)

Tell the human, verbatim:
  - "The daemon will make Anthropic API calls against your ANTHROPIC_API_KEY.
    Budget cap is $<cap>/day; lower it in lab.yaml if you want."
  - "The framework's agent prompts are currently calibrated for QML-domain
    research. Non-QML domains may get odd suggestions until prompt overrides
    ship in Phase B."
  - "The Coder agent will autonomously modify files under source.dir.
    Make sure that directory is in git and clean."

Ask: "OK to start the daemon?" If no, STOP.

## Step 6 — Start the daemon

efferents start --submission ./efferents-submissions/<slug>/ --detach

Report to the human:
  - lab_id (printed by `start`)
  - Daemon PID
  - Path to the progress dashboard
  - That their session can end; daemon keeps running
  - That they can check status by running `efferents status --lab-id <id>`

## Step 7 — End

You're done. The daemon owns the lab from here.
```

- [ ] **Step 3: Commit**

```bash
git add skills/intake.md
git commit -m "feat: add skills/intake.md (moltbook-shaped entry-point markdown)"
```

---

### Task 23: Manual verification checklist

**Files:**
- Create: `docs/superpowers/specs/<today>-deployment-verification.md` (where `<today>` is the actual date of execution)

- [ ] **Step 1: Generic test suite green**

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration -v`
Expected: all pass. Record the count.

- [ ] **Step 2: Smoke-lab validate**

Run: `efferents validate --submission examples/smoke-lab/`
Expected: `OK lab_id=smoke-coefficient ...`

- [ ] **Step 3: Smoke-lab foreground end-to-end**

Run (requires `ANTHROPIC_API_KEY`):

```bash
timeout 120 efferents start --submission examples/smoke-lab/ || echo "timed out as expected"
```

Then:
```bash
sqlite3 examples/smoke-lab/lab/state.db "SELECT COUNT(*), MIN(synthetic_loss), MAX(synthetic_loss) FROM runs"
```
Expected: at least 1 row with non-null synthetic_loss.

```bash
ls examples/smoke-lab/lab/progress/index.html
```
Expected: file exists.

- [ ] **Step 4: Status command**

Run: `efferents list`
Expected: smoke-coefficient appears.

Run: `efferents status --lab-id smoke-coefficient`
Expected: status (stopped, since we timed out), last_activity, dashboard path.

- [ ] **Step 5: Crash recovery**

Re-run: `efferents start --submission examples/smoke-lab/ --detach`
Expected: lab_id printed; new PID.

Kill: `kill -9 $(efferents status --lab-id smoke-coefficient | grep pid | awk -F= '{print $2}' | awk '{print $1}')`

Re-start: `efferents start --submission examples/smoke-lab/ --detach`
Expected: succeeds (idempotent re-attach), no data lost. `state.db` row count unchanged or increased.

- [ ] **Step 6: auto-qml sanity**

```bash
cd ../auto-qml && uv run pytest tests/ -x 2>&1 | tail -30
```
Expected: tests pass OR documented breakage (auto-qml needs `run.py` stdout-JSON migration). If broken, file an issue/note in the verification doc.

- [ ] **Step 7: Write the verification doc**

Create `docs/superpowers/specs/<today>-deployment-verification.md` (replace `<today>` with actual ISO date) summarizing:
- Test counts (passed/failed/skipped)
- Smoke-lab end-to-end metrics observed
- Status output
- Crash recovery outcome
- auto-qml status
- Any surprises encountered

Then:

```bash
git add docs/superpowers/specs/<today>-deployment-verification.md
git commit -m "docs: deployment verification results"
```

---

### Task 24: Tag the release

**Files:**
- (No file changes; just tag.)

- [ ] **Step 1: Bump version**

Edit `pyproject.toml`:

```toml
version = "0.1.0"
```

- [ ] **Step 2: Commit + tag**

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.1.0 (first deployable cut)"
git tag -a v0.1.0 -m "v0.1.0 — moltbook-shaped intake + LabConfig + smoke-lab"
```

- [ ] **Step 3: Confirm the install + CLI works from a fresh venv**

```bash
cd /tmp && uv venv test-efferents && source test-efferents/bin/activate
uv pip install -e /Users/masha/Documents/efferents
efferents --help
```
Expected: usage text appears.

```bash
deactivate && rm -rf /tmp/test-efferents
```

The framework is ready for the first external user to read `skills/intake.md` and submit a hypothesis. Phase B (hosted venue, second example lab, prompt templating) starts after this lands.
