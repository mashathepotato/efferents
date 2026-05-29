# Research-Loop E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three v0.1 follow-ups so the smoke lab runs a full research cycle end-to-end via the deployed CLI.

**Architecture:** Move the stdout-JSON persistence helpers from `orchestrator.py` into `efferents/exec.py` (their natural home) and add ALTER-on-OperationalError retry. Add `ensure_runs_table(db, cfg)` to provision a domain-agnostic runs schema from LabConfig metrics. Rewrite `executor.py` so its public signature is preserved but internals route through the new exec helpers, with generic notebook formatting that has zero QML-specific references.

**Tech Stack:** Python 3.10+, `uv`, pytest, sqlite3, pyyaml. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-29-research-loop-e2e-design.md`

---

## File map

**Create:**
- `tests/test_ensure_runs_table.py`
- `tests/test_executor_rewrite.py`

**Rename:**
- `tests/test_orchestrator_run_persistence.py` → `tests/test_exec_persist.py`

**Modify:**
- `efferents/lab.py` — add metric column-name sanitizer in `_build_labconfig`
- `efferents/migrations/runner.py` — add `ensure_runs_table`
- `efferents/exec.py` — receive `_execute_run`, `_persist_run_result` (moved in from orchestrator) with new ALTER-on-OperationalError retry
- `efferents/agents/orchestrator.py` — delete the now-moved helpers + their imports
- `efferents/cli.py` — `_init_lab_root` calls `ensure_runs_table` + scaffolds `context/research_log.md`
- `efferents/agents/executor.py` — full rewrite (signature preserved, internals new)
- `tests/conftest.py` — `smoke_lab_config` provisions `lab/state.db` via `ensure_runs_table`
- `tests/test_lab_config.py` — new sanitizer tests
- `pyproject.toml` — version bump to `0.1.1`

---

## Task 1: LabConfig metric column-name sanitizer

Validates that every metric column name (headline.column + each panel.column) matches `^[A-Za-z_][A-Za-z0-9_]*$` at load time, preventing SQL injection via `lab.yaml` when `ensure_runs_table` ALTERs the schema.

**Files:**
- Modify: `efferents/lab.py` (inside `_build_labconfig`)
- Modify: `tests/test_lab_config.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_lab_config.py`:

```python
def test_from_submission_bad_headline_column_name(tmp_path):
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: x\nfalsifiability_gate: passed\nstatus: active\n---\n\nbody"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "c.yaml").touch()
    (tmp_path / "lab.yaml").write_text(
        "lab_id: x\ndomain: y\n"
        "source:\n  dir: ./src/\n"
        "executor:\n  run_command: 'echo {config_path}'\n  config_template: c.yaml\n"
        "metrics:\n  headline:\n    column: 'bad name; drop table runs;--'\n    direction: min\n"
    )
    with pytest.raises(SubmissionError, match="column"):
        LabConfig.from_submission(tmp_path)


def test_from_submission_bad_panel_column_name(tmp_path):
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: x\nfalsifiability_gate: passed\nstatus: active\n---\n\nbody"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "c.yaml").touch()
    (tmp_path / "lab.yaml").write_text(
        "lab_id: x\ndomain: y\n"
        "source:\n  dir: ./src/\n"
        "executor:\n  run_command: 'echo {config_path}'\n  config_template: c.yaml\n"
        "metrics:\n  headline:\n    column: loss\n    direction: min\n"
        "  panels:\n    - { column: '1bad', label: 'Bad' }\n"
    )
    with pytest.raises(SubmissionError, match="column"):
        LabConfig.from_submission(tmp_path)


def test_from_submission_dot_in_column_name_rejected(tmp_path):
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: x\nfalsifiability_gate: passed\nstatus: active\n---\n\nbody"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "c.yaml").touch()
    (tmp_path / "lab.yaml").write_text(
        "lab_id: x\ndomain: y\n"
        "source:\n  dir: ./src/\n"
        "executor:\n  run_command: 'echo {config_path}'\n  config_template: c.yaml\n"
        "metrics:\n  headline:\n    column: 'foo.bar'\n    direction: min\n"
    )
    with pytest.raises(SubmissionError, match="column"):
        LabConfig.from_submission(tmp_path)


def test_from_submission_accepts_underscore_and_digits_after_first(tmp_path):
    (tmp_path / "hypothesis.md").write_text(
        "---\nslug: x\nfalsifiability_gate: passed\nstatus: active\n---\n\nbody"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "c.yaml").touch()
    (tmp_path / "lab.yaml").write_text(
        "lab_id: x\ndomain: y\n"
        "source:\n  dir: ./src/\n"
        "executor:\n  run_command: 'echo {config_path}'\n  config_template: c.yaml\n"
        "metrics:\n  headline:\n    column: synthetic_loss_2\n    direction: min\n"
        "  panels:\n    - { column: _internal, label: 'I' }\n"
    )
    cfg = LabConfig.from_submission(tmp_path)
    assert cfg.metrics.headline.column == "synthetic_loss_2"
    assert cfg.metrics.panels[0].column == "_internal"
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest tests/test_lab_config.py -k column -v`
Expected: first 3 tests fail (no sanitizer yet); last passes vacuously.

- [ ] **Step 3: Add the sanitizer**

In `efferents/lab.py`, find `_build_labconfig`. Right after the existing `import re` at the top of the helpers section (or add `import re` to the existing imports if not present — `_FRONTMATTER_RE` already uses `re`, so the import exists), add this regex constant near the top of the helper block:

```python
_COL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
```

Then inside `_build_labconfig`, immediately after the headline direction check and BEFORE the `panels = tuple(...)` block, add:

```python
    if not _COL_NAME_RE.match(headline_col):
        raise SubmissionError(
            f"metrics.headline.column {headline_col!r} must match [A-Za-z_][A-Za-z0-9_]* "
            f"(SQL identifier rules)"
        )
```

And inside the existing panel loop (`for i, p in enumerate(...)`), after the `column` presence check, add a sanitizer guard:

```python
    for i, p in enumerate(metrics_raw.get("panels") or []):
        if not isinstance(p, dict) or "column" not in p:
            raise SubmissionError(f"metrics.panels[{i}] missing required 'column' field")
        if not _COL_NAME_RE.match(p["column"]):
            raise SubmissionError(
                f"metrics.panels[{i}].column {p['column']!r} must match "
                f"[A-Za-z_][A-Za-z0-9_]* (SQL identifier rules)"
            )
        panels_list.append(Panel(column=p["column"], label=p.get("label", p["column"]), target=p.get("target")))
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/test_lab_config.py -v`
Expected: all tests pass (existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add efferents/lab.py tests/test_lab_config.py
git commit -m "feat(lab): sanitize metric column names against SQL-identifier rules"
```

---

## Task 2: ensure_runs_table migration

Provisions the `runs` table with base meta columns plus a REAL column per LabConfig metric. Idempotent.

**Files:**
- Modify: `efferents/migrations/runner.py`
- Create: `tests/test_ensure_runs_table.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ensure_runs_table.py`:

```python
"""ensure_runs_table provisions a domain-agnostic runs schema from LabConfig."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from efferents.migrations.runner import ensure_runs_table
from efferents.lab import (
    Budget, Executor, Headline, LabConfig, Metrics, Panel, Source,
)


def _cfg(tmp_path: Path, headline="synthetic_loss", panels=()):
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.yaml").touch()
    return LabConfig(
        lab_id="t", domain="d", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command="echo {config_path}", smoke_command=None,
            config_template=src / "c.yaml",
        ),
        metrics=Metrics(
            headline=Headline(column=headline, direction="min"),
            panels=tuple(Panel(column=c, label=c) for c in panels),
        ),
        budget=Budget(),
    )


def _cols(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    finally:
        conn.close()


def test_creates_runs_table_with_base_columns(tmp_path):
    db = tmp_path / "state.db"
    ensure_runs_table(db, _cfg(tmp_path))
    cols = _cols(db)
    assert {"run_id", "started_at", "ended_at", "config_path",
            "campaign_id", "researcher_mode", "student_id",
            "git_commit", "duration_seconds"}.issubset(cols)


def test_creates_metric_columns_from_config(tmp_path):
    db = tmp_path / "state.db"
    ensure_runs_table(db, _cfg(tmp_path, headline="loss", panels=("loss", "accuracy")))
    cols = _cols(db)
    assert "loss" in cols
    assert "accuracy" in cols


def test_idempotent_on_second_call(tmp_path):
    db = tmp_path / "state.db"
    cfg = _cfg(tmp_path, headline="loss")
    ensure_runs_table(db, cfg)
    cols_before = _cols(db)
    ensure_runs_table(db, cfg)
    cols_after = _cols(db)
    assert cols_before == cols_after


def test_adds_new_metric_column_to_existing_table(tmp_path):
    db = tmp_path / "state.db"
    ensure_runs_table(db, _cfg(tmp_path, headline="loss"))
    # second call with a panel that introduces a new column
    ensure_runs_table(db, _cfg(tmp_path, headline="loss", panels=("accuracy",)))
    cols = _cols(db)
    assert "loss" in cols
    assert "accuracy" in cols


def test_leaves_unrelated_existing_columns_untouched(tmp_path):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, "
        "legacy_col TEXT)"
    )
    conn.commit()
    conn.close()
    ensure_runs_table(db, _cfg(tmp_path, headline="loss"))
    cols = _cols(db)
    assert "legacy_col" in cols
    assert "loss" in cols


def test_runs_table_primary_key_is_run_id(tmp_path):
    db = tmp_path / "state.db"
    ensure_runs_table(db, _cfg(tmp_path))
    conn = sqlite3.connect(db)
    try:
        pk_cols = [row[1] for row in conn.execute("PRAGMA table_info(runs)") if row[5] == 1]
        assert pk_cols == ["run_id"]
    finally:
        conn.close()
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest tests/test_ensure_runs_table.py -v`
Expected: ImportError — `ensure_runs_table` doesn't exist yet.

- [ ] **Step 3: Add `ensure_runs_table`**

Open `efferents/migrations/runner.py`. After the existing `apply_campaigns_migration` function (end of file), append:

```python


_RUNS_BASE_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    config_path TEXT,
    campaign_id TEXT,
    researcher_mode TEXT,
    student_id TEXT DEFAULT 'primary',
    git_commit TEXT,
    duration_seconds REAL
);
"""


def ensure_runs_table(db_path, cfg) -> None:
    """Create the runs table if absent; add REAL columns for any LabConfig
    metric not already present. Idempotent.

    db_path: str | Path. cfg: LabConfig.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_RUNS_BASE_DDL)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        metric_cols = {cfg.metrics.headline.column,
                       *(p.column for p in cfg.metrics.panels)}
        for col in sorted(metric_cols - existing):
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col} REAL")
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/test_ensure_runs_table.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add efferents/migrations/runner.py tests/test_ensure_runs_table.py
git commit -m "feat(migrations): add ensure_runs_table provisioning from LabConfig metrics"
```

---

## Task 3: Move `_execute_run` + `_persist_run_result` to `exec.py`; add ALTER-on-OperationalError retry

The two helpers were added to `orchestrator.py` in Task 17 of the v0.1 plan. Their natural home is `efferents/exec.py` alongside `_run_and_capture`. Moving them also unblocks Task 5 (executor rewrite) without creating a circular import. Add a single retry path when the metric column doesn't exist.

**Files:**
- Modify: `efferents/exec.py` (add the two functions + retry)
- Modify: `efferents/agents/orchestrator.py` (remove the two functions + their now-unused imports)
- Rename: `tests/test_orchestrator_run_persistence.py` → `tests/test_exec_persist.py` (`git mv`)
- Modify: the renamed test file (update import path; add ALTER+retry test)

- [ ] **Step 1: Rename the test file**

```bash
cd /Users/masha/Documents/efferents
git mv tests/test_orchestrator_run_persistence.py tests/test_exec_persist.py
```

- [ ] **Step 2: Update imports in the renamed test + add the ALTER-retry test**

Open `tests/test_exec_persist.py`. Replace `from efferents.agents import orchestrator` (or wherever the test imports the helpers) with:

```python
from efferents.exec import _execute_run, _persist_run_result, RunResult
```

Replace every `orchestrator._persist_run_result(...)` with `_persist_run_result(...)` and every `orchestrator._execute_run(...)` with `_execute_run(...)` in this file.

Then append a new test:

```python
def test_persist_run_result_adds_missing_column_and_retries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lab").mkdir()
    db = tmp_path / "lab" / "state.db"
    conn = sqlite3.connect(db)
    # Pre-create table with run_id + started_at + ended_at + config_path
    # but NO "synthetic_loss" column — _persist_run_result must ALTER + retry.
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT, "
        "config_path TEXT)"
    )
    conn.commit()
    conn.close()

    result = RunResult(
        ok=True,
        metrics={"synthetic_loss": 0.42},
        elapsed_s=1.2,
        git_commit=None,
    )
    _persist_run_result(result, "run-x", Path("configs/x.yaml"))

    conn = sqlite3.connect(db)
    rows = list(conn.execute("SELECT run_id, synthetic_loss FROM runs"))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
    conn.close()
    assert rows == [("run-x", 0.42)]
    assert "synthetic_loss" in cols
```

Make sure `import sqlite3` and `from pathlib import Path` are at the top of the file (they were already, but verify).

- [ ] **Step 3: Verify tests fail**

Run: `uv run pytest tests/test_exec_persist.py -v`
Expected: ImportError (`_execute_run`, `_persist_run_result` not in `efferents.exec`).

- [ ] **Step 4: Move the two functions into `efferents/exec.py`**

Open `efferents/agents/orchestrator.py`. Locate `def _execute_run(...)` and `def _persist_run_result(...)` near the end of the file (added in v0.1 Task 17). Also locate the imports they brought with them — most likely:

```python
import sqlite3
from datetime import datetime, timezone
from efferents.exec import RunResult, _run_and_capture
from efferents import lab as _lab
```

Cut both functions and the imports specific to them.

Open `efferents/exec.py`. Add the new imports at the top (next to existing imports), then append the two functions to the bottom:

```python
# Add to imports block at the top of exec.py:
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from efferents import lab as _lab
```

Then append at the bottom of `exec.py`:

```python
def _execute_run(config_path: Path) -> RunResult:
    """Render the lab's run_command and execute it, parsing stdout JSON."""
    cfg = _lab.get_config()
    cmd = cfg.executor.run_command.format(config_path=str(config_path))
    return _run_and_capture(
        cmd,
        timeout_s=cfg.executor.run_timeout_s,
        cwd=str(cfg.source.dir),
        env_passthrough=cfg.executor.env_passthrough,
    )


def _persist_run_result(result: RunResult, run_id: str, config_path: Path) -> None:
    """Insert a row into lab/state.db from a RunResult.

    Skips when result.metrics is None (failed run with no parseable metrics).
    If a metric column doesn't exist, ALTER TABLE to add it and retry once.
    """
    if not result.metrics:
        return
    db_path = Path("lab/state.db")
    cols = ["run_id", "started_at", "ended_at", "config_path"]
    now = datetime.now(timezone.utc).isoformat()
    vals: list = [run_id, now, now, str(config_path)]
    for k, v in result.metrics.items():
        cols.append(k)
        vals.append(v)
    if result.git_commit:
        cols.append("git_commit")
        vals.append(result.git_commit)
    if result.elapsed_s is not None:
        cols.append("duration_seconds")
        vals.append(result.elapsed_s)

    placeholders = ",".join("?" for _ in vals)
    col_list = ",".join(cols)
    sql = f"INSERT INTO runs ({col_list}) VALUES ({placeholders})"

    with sqlite3.connect(db_path) as conn:
        try:
            conn.execute(sql, vals)
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            msg = str(e)
            # SQLite signals missing columns as "no such column: <name>" (or similar).
            if "no such column" not in msg.lower():
                print(f"warning: could not persist metric row: {e}")
                return
            existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
            for col in cols:
                if col not in existing:
                    try:
                        conn.execute(f"ALTER TABLE runs ADD COLUMN {col} REAL")
                    except sqlite3.OperationalError as alter_err:
                        print(f"warning: could not add column {col}: {alter_err}")
                        return
            try:
                conn.execute(sql, vals)
                conn.commit()
            except sqlite3.OperationalError as retry_err:
                print(f"warning: persist retry failed: {retry_err}")
```

- [ ] **Step 5: Verify tests pass**

Run: `uv run pytest tests/test_exec_persist.py -v`
Expected: 3 passed (the 2 original tests + the new ALTER+retry test).

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration 2>&1 | tail -3`
Expected: no regressions; same pass/skip counts as before this task (excluding any failures rooted in this task).

- [ ] **Step 6: Commit**

```bash
git add efferents/exec.py efferents/agents/orchestrator.py tests/test_exec_persist.py
git commit -m "refactor(exec): relocate _execute_run/_persist_run_result + add ALTER-on-OperationalError retry"
```

---

## Task 4: `_init_lab_root` provisions `runs` table + scaffolds `context/`

**Files:**
- Modify: `efferents/cli.py` (`_init_lab_root`)
- Modify: `tests/test_cli.py` (existing `test_start_foreground_registers_and_runs` already exercises `_init_lab_root` indirectly; we'll extend it)

- [ ] **Step 1: Extend the existing test**

Open `tests/test_cli.py`. Find `test_start_foreground_registers_and_runs`. After the existing `Registry().get(...)` assertion, append:

```python
    # _init_lab_root must have provisioned runs table and context scaffold
    import sqlite3
    db = sub / "lab" / "state.db"
    assert db.exists()
    conn = sqlite3.connect(db)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    finally:
        conn.close()
    assert "run_id" in cols
    assert "synthetic_loss" in cols, f"expected synthetic_loss column, got {cols}"

    context_log = sub / "context" / "research_log.md"
    assert context_log.exists()
    assert "sample-conjecture research log" in context_log.read_text()
```

Note: the fixture `SAMPLE` (sample_submission) has `metrics.headline.column: synthetic_loss` per the fixture lab.yaml created in v0.1's Task 2, so `synthetic_loss` is the expected metric column.

- [ ] **Step 2: Verify it fails**

Run: `uv run pytest tests/test_cli.py::test_start_foreground_registers_and_runs -v`
Expected: AssertionError (either `runs` table missing the metric column or `context/research_log.md` missing).

- [ ] **Step 3: Update `_init_lab_root`**

Open `efferents/cli.py`. Find `_init_lab_root` (added in v0.1 Task 12). Locate the line that calls the campaigns migration (likely `apply_campaigns_migration(lab_root / "state.db")` or similar). Add an import at the top of `cli.py` if not already present:

```python
from efferents.migrations.runner import apply_campaigns_migration, ensure_runs_table
```

(Adjust to merge with whatever import shape exists.)

In `_init_lab_root`, AFTER `apply_campaigns_migration(...)` (or equivalent), add:

```python
    ensure_runs_table(lab_root / "state.db", lab_mod.get_config())
```

Note: `lab_mod.get_config()` is available because `_cmd_start` calls `lab_mod.set_config(cfg)` BEFORE `_init_lab_root` in the current cli.py flow. If your editing reveals the order is reversed, swap the two calls so `set_config` runs first.

After the existing `state.json` bootstrap block (writes `{}` if absent), add the context scaffold:

```python
    context_dir = submission_dir / "context"
    context_dir.mkdir(exist_ok=True)
    research_log = context_dir / "research_log.md"
    if not research_log.exists():
        cfg = lab_mod.get_config()
        research_log.write_text(
            f"# {cfg.lab_id} research log\n\n"
            "*(empty — populate to guide the Researcher; "
            "the lab will operate from the hypothesis if left blank)*\n"
        )
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: all CLI tests pass (12 — same as before, plus the extended assertions on the existing test).

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration 2>&1 | tail -3`
Expected: no regressions.

- [ ] **Step 5: Commit**

```bash
git add efferents/cli.py tests/test_cli.py
git commit -m "feat(cli): _init_lab_root provisions runs table + scaffolds context/research_log.md"
```

---

## Task 5: `conftest.py` smoke fixture provisions `lab/state.db`

Makes `_persist_run_result` work in tests without each test re-creating the table.

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Update the fixture**

Open `tests/conftest.py`. Find the `smoke_lab_config` autouse fixture. After the existing `lab_mod.set_config(cfg)` call and BEFORE the `yield cfg` line, add:

```python
    # Provision lab/state.db with the smoke schema so persistence-touching
    # tests don't have to bootstrap it themselves.
    import os
    lab_dir = tmp / "lab"
    lab_dir.mkdir(exist_ok=True)
    from efferents.migrations.runner import ensure_runs_table
    ensure_runs_table(lab_dir / "state.db", cfg)
    # Chdir so relative "lab/state.db" lookups in _persist_run_result resolve.
    prev_cwd = os.getcwd()
    os.chdir(tmp)
```

Then change the existing `yield cfg` block to restore CWD on teardown:

```python
    try:
        yield cfg
    finally:
        os.chdir(prev_cwd)
        lab_mod._active = None
```

(Replace the existing `yield cfg` / `lab_mod._active = None` block with the version above.)

- [ ] **Step 2: Verify nothing regresses**

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration 2>&1 | tail -3`
Expected: same pass/skip counts as before this task. No new failures.

If a test that previously asserted on the CWD now fails, surface it — the test may have assumed `tmp_path` was the CWD. Most should be fine since they use `tmp_path` directly.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: smoke_lab_config fixture provisions lab/state.db + chdirs into tmp"
```

---

## Task 6: Rewrite `executor.py` (domain-agnostic, signature preserved)

Same `execute(*, paths, proposal, base_config=None)` signature; same return shape. New internals route through `_execute_run` + `_persist_run_result`. Notebook formatter is generic.

**Files:**
- Modify: `efferents/agents/executor.py` (full rewrite)
- Create: `tests/test_executor_rewrite.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_executor_rewrite.py`:

```python
"""Rewritten executor.execute routes through exec.py with generic notebook formatting."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

from efferents.agents import executor
from efferents.agents.state import LabPaths
from efferents.lab import (
    Budget, Executor, Headline, LabConfig, Metrics, Panel, Source,
)
from efferents import lab as lab_mod
from efferents.migrations.runner import ensure_runs_table


def _install_smoke(tmp_path: Path, run_cmd: str, headline="synthetic_loss"):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    cfg_template = src / "default.yaml"
    cfg_template.write_text("coefficient: 0.5\n")
    cfg = LabConfig(
        lab_id="x", domain="y", pi_handle=None,
        source=Source(dir=src),
        executor=Executor(
            run_command=run_cmd,
            smoke_command=None,
            config_template=cfg_template,
            run_timeout_s=30,
        ),
        metrics=Metrics(
            headline=Headline(column=headline, direction="min"),
            panels=(Panel(column=headline, label="Loss"),),
        ),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    return cfg


def _make_paths(tmp_path: Path) -> LabPaths:
    from efferents.agents.state import lab_paths
    lab_dir = tmp_path / "lab"
    lab_dir.mkdir(exist_ok=True)
    return lab_paths(lab_dir)


def test_execute_happy_path_writes_row_and_notebook(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = json.dumps({"run_id": "ignored", "metrics": {"synthetic_loss": 0.42}, "elapsed_s": 0.01})
    cmd = f"echo '{payload}'"
    cfg = _install_smoke(tmp_path, cmd)
    ensure_runs_table(tmp_path / "lab" / "state.db", cfg)
    paths = _make_paths(tmp_path)

    outcome = executor.execute(
        paths=paths,
        proposal={"name": "trial-1", "config_overrides": {"coefficient": 0.8},
                  "hypothesis": "lower coefficient helps", "expected": "loss < 0.1"},
    )

    assert outcome["ok"] is True
    assert outcome["name"] == "trial-1"
    assert len(outcome["rows"]) == 1
    assert outcome["rows"][0]["synthetic_loss"] == 0.42
    # The orchestrator-side run_id wins over the run_command's payload run_id.
    assert outcome["rows"][0]["run_id"] != "ignored"

    # Row landed in state.db
    conn = sqlite3.connect(tmp_path / "lab" / "state.db")
    try:
        rows = list(conn.execute("SELECT run_id, synthetic_loss FROM runs"))
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0][1] == 0.42

    # Notebook entry written with generic columns (no QML references)
    nb_text = paths.notebook.read_text()
    assert "trial-1" in nb_text
    assert "synthetic_loss" in nb_text
    assert "E_w1" not in nb_text  # legacy QML column must NOT appear
    assert "amp_ratio" not in nb_text


def test_execute_nonzero_exit_returns_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd = "echo no-json-here && exit 1"
    cfg = _install_smoke(tmp_path, cmd)
    ensure_runs_table(tmp_path / "lab" / "state.db", cfg)
    paths = _make_paths(tmp_path)

    outcome = executor.execute(
        paths=paths,
        proposal={"name": "fail-1", "config_overrides": {},
                  "hypothesis": "", "expected": ""},
    )
    assert outcome["ok"] is False
    assert outcome["name"] == "fail-1"
    assert outcome.get("error")

    conn = sqlite3.connect(tmp_path / "lab" / "state.db")
    try:
        count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    finally:
        conn.close()
    assert count == 0  # no row inserted on failure


def test_execute_no_json_returns_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd = "echo plain-text-no-json"
    cfg = _install_smoke(tmp_path, cmd)
    ensure_runs_table(tmp_path / "lab" / "state.db", cfg)
    paths = _make_paths(tmp_path)

    outcome = executor.execute(
        paths=paths,
        proposal={"name": "nojson", "config_overrides": {},
                  "hypothesis": "", "expected": ""},
    )
    assert outcome["ok"] is False
    assert "JSON" in (outcome.get("error") or "")


def test_execute_writes_rendered_config_yaml(tmp_path, monkeypatch):
    """The rendered config (template + overrides) lands at lab/configs/run_<id>.yaml."""
    monkeypatch.chdir(tmp_path)
    payload = json.dumps({"run_id": "x", "metrics": {"synthetic_loss": 0.1}, "elapsed_s": 0.0})
    cmd = f"echo '{payload}'"
    cfg = _install_smoke(tmp_path, cmd)
    ensure_runs_table(tmp_path / "lab" / "state.db", cfg)
    paths = _make_paths(tmp_path)

    outcome = executor.execute(
        paths=paths,
        proposal={"name": "render-test", "config_overrides": {"coefficient": 0.9},
                  "hypothesis": "", "expected": ""},
    )
    assert outcome["ok"] is True
    configs_dir = paths.root / "configs"
    files = list(configs_dir.glob("run_*.yaml"))
    assert len(files) == 1
    rendered = yaml.safe_load(files[0].read_text())
    assert rendered["coefficient"] == 0.9
    assert rendered["run"]["name"] == "render-test"
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest tests/test_executor_rewrite.py -v`
Expected: most tests fail or error — the current executor.py still calls `auto_qml.run_from_config` which lazy-raises.

- [ ] **Step 3: Rewrite `efferents/agents/executor.py`**

Replace the entire contents of `efferents/agents/executor.py` with:

```python
"""Executor agent: render a proposal's config, run it, persist + log.

The execute() signature and return shape are preserved for the
orchestrator's downstream consumers. Internals route through
efferents.exec._execute_run + _persist_run_result, and the notebook
formatter renders dynamic columns from RunResult.metrics — no domain-
specific (QML) references survive.
"""
from __future__ import annotations

import copy
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from efferents import lab as _lab
from efferents.agents.state import LabPaths, notebook_append, now_iso
from efferents.exec import _execute_run, _persist_run_result, RunResult


def load_default_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open() as f:
        return yaml.safe_load(f)


def apply_overrides(cfg: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Apply dotted-path overrides ('augmentation.aug_depth' -> 4) to a nested dict."""
    out = copy.deepcopy(cfg)
    for path, value in overrides.items():
        keys = path.split(".")
        cursor = out
        for k in keys[:-1]:
            if k not in cursor or not isinstance(cursor[k], dict):
                cursor[k] = {}
            cursor = cursor[k]
        cursor[keys[-1]] = value
    return out


def execute(
    *,
    paths: LabPaths,
    proposal: dict[str, Any],
    base_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one proposal end-to-end. Returns {ok, name, rows | error}."""
    cfg = _lab.get_config()
    name = proposal.get("name", "unnamed")
    overrides = dict(proposal.get("config_overrides", {}) or {})
    if proposal.get("campaign_id"):
        overrides["run.campaign_id"] = proposal["campaign_id"]
    if proposal.get("mode"):
        overrides["run.researcher_mode"] = proposal["mode"]
    if proposal.get("student_id"):
        overrides["run.student_id"] = proposal["student_id"]

    base = base_config or load_default_config(cfg.executor.config_template)
    rendered = apply_overrides(base, overrides)
    rendered.setdefault("run", {})["name"] = name

    run_id = uuid.uuid4().hex
    config_dir = paths.root / "configs"
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / f"run_{run_id}.yaml"
    with config_path.open("w") as f:
        yaml.safe_dump(rendered, f)

    started = now_iso()
    t0 = time.monotonic()
    result = _execute_run(config_path)
    duration = time.monotonic() - t0

    _persist_run_result(result, run_id, config_path)

    notebook_append(
        paths.notebook,
        _format_outcome(
            name=name,
            hypothesis=proposal.get("hypothesis", ""),
            expected=proposal.get("expected", ""),
            overrides=overrides,
            result=result,
            duration=duration,
            started=started,
        ),
    )

    if result.ok:
        row: dict[str, Any] = {"run_id": run_id, "name": name}
        if result.metrics:
            row.update(result.metrics)
        if result.git_commit:
            row["git_commit"] = result.git_commit
        return {"ok": True, "name": name, "rows": [row], "duration_seconds": duration}

    err_tail = (result.stderr or "")[-200:]
    return {
        "ok": False,
        "name": name,
        "error": result.error or err_tail or "run failed",
        "traceback": "",
        "duration_seconds": duration,
    }


def _format_outcome(
    *,
    name: str,
    hypothesis: str,
    expected: str,
    overrides: dict[str, Any],
    result: RunResult,
    duration: float,
    started: str,
) -> str:
    lines = [
        f"## {started} — {name}",
        "",
        f"**Hypothesis**: {hypothesis}",
        "",
        f"**Expected**: {expected}",
        "",
        f"**Overrides**: `{overrides}`",
        "",
        f"**Duration**: {duration:.1f}s",
        "",
    ]
    if result.metrics:
        cols = list(result.metrics.keys())
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join("---" for _ in cols) + "|")

        def _fmt(v: Any) -> str:
            if isinstance(v, float):
                return f"{v:.4g}"
            if isinstance(v, int):
                return str(v)
            return str(v)

        lines.append("| " + " | ".join(_fmt(result.metrics[c]) for c in cols) + " |")
    else:
        lines.append(f"**Error**: {result.error or 'no metrics emitted'}")
        if result.stderr:
            tail = result.stderr[-1024:]
            lines.append("")
            lines.append("```")
            lines.append(tail)
            lines.append("```")
    return "\n".join(lines)
```

Note: this drops the previous `DEFAULT_CONFIG_PATH = Path("config/default.yaml")` constant and the `load_default_config()` no-arg default. The new `load_default_config(path)` requires an explicit path. Verify no other module imports it without an arg:

```bash
grep -rn "load_default_config" efferents/ tests/
```

If any caller passed nothing, fix that caller to pass `_lab.get_config().executor.config_template`.

Also drop the `try: from auto_qml.run import run_from_config` block from the top of the file — the rewrite no longer needs `run_from_config` at all. (That import was added during v0.1's Task-0 prep.)

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/test_executor_rewrite.py -v`
Expected: 4 passed.

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration 2>&1 | tail -3`
Expected: no regressions. If tests that depended on the old QML notebook format break, they're QML-coupled and should be `@pytest.mark.skip`-ed per the existing `tests/lab_reference/` convention.

- [ ] **Step 5: Commit**

```bash
git add efferents/agents/executor.py tests/test_executor_rewrite.py
git commit -m "refactor(executor): rewrite to route through exec.py with generic notebook formatting"
```

---

## Task 7: Manual verification + tag v0.1.1

Confirm the smoke lab runs an actual research cycle, then bump version and tag.

**Files:**
- Modify: `pyproject.toml` (version)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest tests/ --ignore=tests/lab_reference 2>&1 | tail -3`
Expected: all generic tests pass; pre-existing skips unchanged.

- [ ] **Step 2: Run the smoke lab daemon in foreground**

Pre-clean (if a previous run left state):

```bash
rm -rf examples/smoke-lab/lab examples/smoke-lab/context
```

Then:

```bash
.venv/bin/efferents validate --submission examples/smoke-lab/
```
Expected: `OK lab_id=smoke-coefficient domain=synthetic source_dir=...`

```bash
timeout 120 .venv/bin/efferents start --submission examples/smoke-lab/ 2>&1 | tee /tmp/smoke-daemon.log | head -40
```

Expected: the daemon registers, prints `lab_id=smoke-coefficient pid=... dashboard=...`, the orchestrator starts cleanly (no `context/` crash), and at least one cycle runs Researcher → Coder skip (smoke is single-campaign) → real run → analyst log. Output will probably stop at the 120s timeout.

If the Researcher/Coder crash for prompt-related reasons (QML-flavored), that's the documented prompt-templating gap — Phase B — NOT a v0.1.1 issue. The success criterion is "at least one run row landed in state.db".

- [ ] **Step 3: Inspect state.db**

```bash
sqlite3 examples/smoke-lab/lab/state.db "SELECT COUNT(*), MIN(synthetic_loss), MAX(synthetic_loss) FROM runs"
```
Expected: count >= 1, min/max are floats in the range (0, 1).

If count is 0, investigate `examples/smoke-lab/lab/daemon.log` for the failure. Common causes:
- Researcher/Coder budget-exhausted on first call (raise daily_cap_usd in smoke-lab/lab.yaml if needed)
- run_command failed (test it standalone: `cd examples/smoke-lab && python -m src.stub_run --config configs/default.yaml`)

- [ ] **Step 4: Confirm dashboard rendered**

```bash
ls examples/smoke-lab/lab/progress/
```
Expected: at least `index.html` (or similar — progress.py writes whatever it writes).

- [ ] **Step 5: Bump version + tag**

Edit `pyproject.toml`:

```toml
version = "0.1.1"
```

Run:

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.1.1 (research-loop e2e)"
git tag -a v0.1.1 -m "v0.1.1 — research loop runs end-to-end on smoke lab"
```

- [ ] **Step 6: Update the verification doc**

Open `docs/superpowers/specs/2026-05-28-deployment-verification.md` and update section 5 ("End-to-end smoke-lab cycle") from ❌ to ✅, with a brief note like:

```
## 5. End-to-end smoke-lab cycle

✅ Resolved in v0.1.1. See `docs/superpowers/specs/2026-05-29-research-loop-e2e-design.md`.
Smoke lab now runs a full Researcher → Executor → analyst cycle. Confirmed
locally: <N> runs landed in state.db with synthetic_loss values in
(min=<x>, max=<y>); progress dashboard rendered.
```

Commit:

```bash
git add docs/superpowers/specs/2026-05-28-deployment-verification.md
git commit -m "docs: mark deployment-verification §5 resolved in v0.1.1"
```

The branch is ready to merge to main.
