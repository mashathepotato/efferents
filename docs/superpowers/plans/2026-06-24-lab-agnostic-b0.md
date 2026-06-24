# B0 — Finish lab-agnosticism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `analyst.py` and `progress.py` domain-agnostic by routing all "which column / which is best / did it improve" logic through a new `efferents/metrics_view.py` driven by `LabConfig.metrics`, and delete the dead auto_qml LaTeX/figure path from `writer.py`/`__main__.py`.

**Architecture:** One new helper module (`metrics_view.py`) is the single source of truth: headline + panels are the named metrics (headline+direction drives best-run and the flat-digest counter), all other non-meta columns are auto-discovered and shown generically. The two live consumers (analyst digest, static progress.html) are refactored onto it; the dead writer path is removed.

**Tech Stack:** Python ≥3.10, `LabConfig` (`efferents/lab.py`), sqlite3, pytest. No new dependencies.

**Reference spec:** `docs/superpowers/specs/2026-06-24-lab-agnostic-b0-design.md`

**Branch:** `feat/lab-agnostic-b0` (already created; spec committed there).

**Note for the implementer:** Tasks 2–4 refactor large existing files (`analyst.py`, `progress.py`, `writer.py`). For those, the plan gives the exact change-list and the pinning tests that define correct generic behavior — **read the target file first**, then make the changes so the (updated) tests pass and no QML column names remain. Run the FULL suite (`uv run pytest -q`) after each task; existing QML-encoding tests are updated within the task that causes them to change.

---

## File Structure

| File | Change |
|------|--------|
| `efferents/metrics_view.py` | **New.** META_COLUMNS, finite, discover_columns, headline, panels, headline_value, best_run, improved |
| `tests/test_metrics_view.py` | **New.** Unit tests for the helper |
| `efferents/agents/analyst.py` | Refactor `_format_campaign_blocks`, `_format_recent_runs`, `write_digest`, `update_flat_digest_counter` onto metrics_view; direction-aware |
| `efferents/agents/progress.py` | Remove `_META_COLUMNS`/`_discover_metric_columns`; refactor `_snapshot`, `_scored_sample_runs`, `_best_run_in`, render fns onto metrics_view |
| `efferents/agents/researcher.py` | Update import of `_discover_metric_columns` → `metrics_view.discover_columns` |
| `efferents/agents/writer.py` | Delete `write_once`, `regenerate_*`, `ALL_RUNS_SQL`, `_format_all_runs`, unused WriterPaths figure/table fields + imports |
| `efferents/agents/__main__.py` | Remove `cmd_write_once` + `write-once` subparser; remove `cmd_start_writer`/`start-writer` if it drives `write_once` |
| `tests/test_analyst_grouping.py`, `test_analyst_epsilon.py`, `test_flat_digest_counter.py` | Update to generic/direction-aware behavior |
| `tests/test_progress.py`, `test_progress_panels.py`, `test_progress_autodiscovery.py` | Update to config-driven columns; no QML names |
| `tests/test_writer_output.py`, `test_writer_metric_resolution.py` | Remove deleted-function tests; keep write_phase_a_paper/should_publish tests |

---

## Task 1: Create `efferents/metrics_view.py` (greenfield)

**Files:**
- Create: `efferents/metrics_view.py`
- Test: `tests/test_metrics_view.py`

- [ ] **Step 1: Write `tests/test_metrics_view.py`**

```python
import sqlite3
from pathlib import Path

from efferents import metrics_view as mv


def test_finite():
    assert mv.finite(0.04) == 0.04
    assert mv.finite(3) == 3.0
    assert mv.finite(True) is None
    assert mv.finite(float("nan")) is None
    assert mv.finite(float("inf")) is None
    assert mv.finite("0.04") is None
    assert mv.finite(None) is None


def test_discover_columns(tmp_path):
    db = tmp_path / "runs.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT, started_at TEXT, campaign_id TEXT, "
        "synthetic_loss REAL, coefficient REAL)"
    )
    conn.commit(); conn.close()
    assert set(mv.discover_columns(db)) == {"synthetic_loss", "coefficient"}


def test_discover_columns_missing_db(tmp_path):
    assert mv.discover_columns(tmp_path / "nope.sqlite") == []


def test_best_run_min(smoke_lab_config):  # smoke headline = synthetic_loss / min
    rows = [{"run_id": "a", "synthetic_loss": 0.08},
            {"run_id": "b", "synthetic_loss": 0.03},
            {"run_id": "c", "synthetic_loss": float("nan")}]
    assert mv.best_run(rows)["run_id"] == "b"


def test_best_run_empty_or_unscored(smoke_lab_config):
    assert mv.best_run([]) is None
    assert mv.best_run([{"run_id": "x", "synthetic_loss": None}]) is None


def test_best_run_max():
    from efferents import lab as lab_mod
    from efferents.lab import (
        Budget, Executor, Headline, LabConfig, Metrics, Source,
    )
    cfg = LabConfig(
        lab_id="t", domain="d", pi_handle=None,
        source=Source(dir=Path("/tmp")),
        executor=Executor(run_command="x {config_path}", smoke_command=None,
                          config_template=Path("c.yaml")),
        metrics=Metrics(headline=Headline(column="accuracy", direction="max"),
                        panels=()),
        budget=Budget(),
    )
    lab_mod.set_config(cfg)
    try:
        rows = [{"run_id": "a", "accuracy": 0.7}, {"run_id": "b", "accuracy": 0.9}]
        assert mv.best_run(rows)["run_id"] == "b"
    finally:
        lab_mod._active = None


def test_improved_min():
    assert mv.improved(0.10, 0.04, direction="min", epsilon=0.005) is True
    assert mv.improved(0.10, 0.099, direction="min", epsilon=0.005) is False
    assert mv.improved(None, 0.04, direction="min", epsilon=0.005) is True
    assert mv.improved(0.04, None, direction="min", epsilon=0.005) is False


def test_improved_max():
    assert mv.improved(0.80, 0.90, direction="max", epsilon=0.005) is True
    assert mv.improved(0.80, 0.802, direction="max", epsilon=0.005) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_metrics_view.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'efferents.metrics_view'`

- [ ] **Step 3: Create `efferents/metrics_view.py`**

```python
"""Lab-agnostic view over a run set.

Single source of truth for "what a run's columns mean": which is the headline
metric, which are configured panels, which are other (auto-discovered) columns,
and direction-aware best/improvement. Everything derives from the active
LabConfig.metrics plus the runs schema, so no consumer hardcodes domain column
names.
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

from efferents import lab as _lab

META_COLUMNS = (
    "run_id", "started_at", "ended_at", "config_path",
    "campaign_id", "researcher_mode", "student_id",
    "git_commit", "duration_seconds",
)


def finite(x) -> float | None:
    """Return x as a float iff it is a finite real number, else None.
    bool is excluded; NaN/inf and non-numeric values return None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if math.isfinite(x) else None


def discover_columns(db_path, *, meta: tuple[str, ...] = META_COLUMNS) -> list[str]:
    """Non-meta columns present in the runs table (a lab's params + metrics).
    Missing db or missing table -> []."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(runs)")]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    return [c for c in cols if c not in meta]


def headline():
    """The active lab's headline metric (column + direction)."""
    return _lab.get_config().metrics.headline


def panels():
    """The active lab's configured metric panels."""
    return _lab.get_config().metrics.panels


def headline_value(row: dict) -> float | None:
    """The finite headline-metric value of a run row, or None."""
    return finite(row.get(headline().column))


def best_run(rows: list[dict]) -> dict | None:
    """Best row by the headline column + direction, skipping rows whose headline
    value isn't finite. None if no scored rows."""
    h = headline()
    scored = [r for r in rows if finite(r.get(h.column)) is not None]
    if not scored:
        return None
    chooser = min if h.direction == "min" else max
    return chooser(scored, key=lambda r: finite(r.get(h.column)))


def improved(prev: float | None, current: float | None, *,
             direction: str, epsilon: float) -> bool:
    """True iff `current` improves on `prev` by more than epsilon in `direction`
    ('min' -> decrease, 'max' -> increase). prev None -> True when current is not
    None (first measurement counts as improvement)."""
    if current is None:
        return False
    if prev is None:
        return True
    return (prev - current) > epsilon if direction == "min" else (current - prev) > epsilon
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_metrics_view.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add efferents/metrics_view.py tests/test_metrics_view.py
git commit -m "feat(metrics): add lab-agnostic metrics_view helper"
```

---

## Task 2: Generalize `analyst.py` onto `metrics_view`

**Files:**
- Modify: `efferents/agents/analyst.py`
- Test: `tests/test_analyst_grouping.py`, `tests/test_analyst_epsilon.py`, `tests/test_flat_digest_counter.py`

**Read `efferents/agents/analyst.py` fully first.** Change-list (per spec §2):

1. `from efferents import metrics_view as mv` at top.
2. `_format_campaign_blocks(groups, db_path)` and `_format_recent_runs(rows)`: delete the hardcoded `metric_keys = ["e_w1", ...]` and `cols = [..., "raw_q", "aug_depth", ...]`. Build columns generically: a fixed meta subset (`run_id` shortened, `started_at`, `campaign_id`, `researcher_mode`) + `mv.headline().column` + `[p.column for p in mv.panels()]` + the remaining `mv.discover_columns(db_path)` (de-duplicated, preserving that order). Render each value with `mv.finite(...)` falling back to the raw value or `—` when absent.
3. `write_digest`: replace the `best_w1 = ...` computation and
   `update_flat_digest_counter(state, current_best_w1=best_w1, epsilon=0.005)`
   with: `best = mv.best_run(rows)`, `best_headline = mv.headline_value(best) if best else None`, and `update_flat_digest_counter(state, current_best_headline=best_headline)` (let epsilon default from config).
4. `update_flat_digest_counter(state, *, current_best_headline, epsilon=None)`:
   rename the keyword from `current_best_w1`. Direction-aware:
   ```python
   if epsilon is None:
       epsilon = _flat_digest_epsilon()
   direction = _lab.get_config().metrics.headline.direction
   prev = state.get("last_digest_best_headline", state.get("last_digest_best_w1"))
   out = dict(state)
   if current_best_headline is None:
       out.setdefault("digests_without_improvement", out.get("digests_without_improvement", 0))
       return out
   if mv.improved(prev, current_best_headline, direction=direction, epsilon=epsilon):
       out["digests_without_improvement"] = 0
   else:
       out["digests_without_improvement"] = out.get("digests_without_improvement", 0) + 1
   out["last_digest_best_headline"] = current_best_headline
   return out
   ```
   (Reads the legacy `last_digest_best_w1` as fallback so existing state.json is preserved. Keep `_lab` imported.)

- [ ] **Step 1: Update the failing tests first**

In `tests/test_flat_digest_counter.py` and `tests/test_analyst_epsilon.py`, rename `current_best_w1=` call sites to `current_best_headline=` and the asserted state key `last_digest_best_w1` → `last_digest_best_headline`. Add a direction-aware case under a `max` config:

```python
def test_flat_digest_counter_direction_max():
    from efferents import lab as lab_mod
    from efferents.lab import (Budget, Executor, Headline, LabConfig, Metrics, Source)
    from pathlib import Path
    from efferents.agents.analyst import update_flat_digest_counter
    cfg = LabConfig(lab_id="t", domain="d", pi_handle=None,
        source=Source(dir=Path("/tmp")),
        executor=Executor(run_command="x {config_path}", smoke_command=None, config_template=Path("c.yaml")),
        metrics=Metrics(headline=Headline(column="accuracy", direction="max"), panels=()),
        budget=Budget())
    lab_mod.set_config(cfg)
    try:
        s = {"last_digest_best_headline": 0.80, "digests_without_improvement": 0}
        s2 = update_flat_digest_counter(s, current_best_headline=0.90)  # improved (max)
        assert s2["digests_without_improvement"] == 0
        s3 = update_flat_digest_counter(s2, current_best_headline=0.901)  # within epsilon
        assert s3["digests_without_improvement"] == 1
    finally:
        lab_mod._active = None
```

In `tests/test_analyst_grouping.py`, change assertions that look for QML columns (`e_w1`, `raw_q`, …) in the digest output to instead assert the digest contains the configured headline column name (`synthetic_loss` under `smoke_lab_config`) and does NOT contain `e_w1`/`raw_q`. (Read the existing test to adapt its fixtures; keep its grouping assertions.)

- [ ] **Step 2: Run the updated tests — expect FAIL**

Run: `uv run pytest tests/test_flat_digest_counter.py tests/test_analyst_epsilon.py tests/test_analyst_grouping.py -v`
Expected: FAIL (current code still uses `current_best_w1` / QML columns).

- [ ] **Step 3: Apply the analyst change-list above**

Edit `efferents/agents/analyst.py` per the 4-point change-list. Show the diff in your report.

- [ ] **Step 4: Run the tests — expect PASS**

Run: `uv run pytest tests/test_flat_digest_counter.py tests/test_analyst_epsilon.py tests/test_analyst_grouping.py -v`
Expected: PASS. Then `uv run pytest -q` — no regressions.

- [ ] **Step 5: Verify no QML columns remain in analyst.py**

Run: `grep -nE "e_w1|raw_q|aug_depth|radial_l2|val_x0_mse|active_frac|gen_max|aug_shared|cond_drop|current_best_w1" efferents/agents/analyst.py || echo "clean"`
Expected: `clean`.

- [ ] **Step 6: Commit**

```bash
git add efferents/agents/analyst.py tests/test_analyst_grouping.py tests/test_analyst_epsilon.py tests/test_flat_digest_counter.py
git commit -m "refactor(analyst): drive digests + flat-digest counter from metrics_view (direction-aware)"
```

---

## Task 3: Generalize `progress.py` onto `metrics_view`

**Files:**
- Modify: `efferents/agents/progress.py`, `efferents/agents/researcher.py`
- Test: `tests/test_progress.py`, `tests/test_progress_panels.py`, `tests/test_progress_autodiscovery.py`

**Read `efferents/agents/progress.py` and the three progress tests first.** Change-list (per spec §2):

1. Remove `_META_COLUMNS` and `_discover_metric_columns` from `progress.py`; add `from efferents import metrics_view as mv` and use `mv.META_COLUMNS` / `mv.discover_columns`.
2. In `efferents/agents/researcher.py`, change `from efferents.agents.progress import _discover_metric_columns` to `from efferents.metrics_view import discover_columns` and update its call site(s) accordingly (`discover_columns(...)`).
3. `_snapshot`: replace the hardcoded `wanted` QML column list with `list(mv.META_COLUMNS) + [mv.headline().column] + [p.column for p in mv.panels()] + mv.discover_columns(db_path)` (de-duplicated, order-preserving).
4. `_scored_sample_runs`: a run is scored iff `mv.headline_value(row) is not None`; remove the `eval_kind == "sample"` filter entirely.
5. `_best_run_in`: `return mv.best_run(rows)`.
6. Render functions (`_render_card`, `_render_run_tile`, `_render_architectures`, and any others referencing QML columns): render the headline metric, each configured panel, then the remaining discovered columns as generic key/value pairs. `_render_architectures` becomes a generic "run config" tile from discovered non-panel columns (or is removed if it has no generic meaning — your judgment; note which in your report).
7. `_panel_metrics` already reads LabConfig — leave it.

- [ ] **Step 1: Update the failing tests first**

In `tests/test_progress.py` / `test_progress_panels.py` / `test_progress_autodiscovery.py`, under `smoke_lab_config` (headline `synthetic_loss`), assert the rendered `progress.html`:
- contains the configured panel label(s) and the `synthetic_loss` column, and
- does NOT contain `e_w1`, `raw_q`, `aug_depth`, `radial_l2_log`, `val_x0_mse`, `gen_max_to_real_max`, or `eval_kind`.

Add an autodiscovery assertion: insert a run row with an arbitrary extra column (e.g. `coefficient`) and assert it appears in the rendered HTML (proving generic discovery). Read each test and adapt its existing setup (DB rows, fixture) rather than rewriting wholesale.

- [ ] **Step 2: Run the updated tests — expect FAIL**

Run: `uv run pytest tests/test_progress.py tests/test_progress_panels.py tests/test_progress_autodiscovery.py -v`
Expected: FAIL (current render hardcodes QML columns / filters `eval_kind`).

- [ ] **Step 3: Apply the progress change-list above**

Edit `progress.py` and the `researcher.py` import. Show the diff in your report.

- [ ] **Step 4: Run the tests — expect PASS**

Run: `uv run pytest tests/test_progress.py tests/test_progress_panels.py tests/test_progress_autodiscovery.py -v`
Expected: PASS. Then `uv run pytest -q` — no regressions (watch `test_*researcher*` for the import change).

- [ ] **Step 5: Verify no QML columns remain in progress.py**

Run: `grep -nE "e_w1|raw_q|aug_depth|radial_l2|val_x0_mse|active_frac|gen_max|aug_shared|cond_drop|eval_kind" efferents/agents/progress.py || echo "clean"`
Expected: `clean`.

- [ ] **Step 6: Commit**

```bash
git add efferents/agents/progress.py efferents/agents/researcher.py tests/test_progress.py tests/test_progress_panels.py tests/test_progress_autodiscovery.py
git commit -m "refactor(progress): render static dashboard from metrics_view (config-driven, autodiscovered columns)"
```

---

## Task 4: Delete the dead auto_qml writer path

**Files:**
- Modify: `efferents/agents/writer.py`, `efferents/agents/__main__.py`
- Test: `tests/test_writer_output.py`, `tests/test_writer_metric_resolution.py`

**Read `writer.py`, `__main__.py`, and the two writer tests first.** This task REMOVES code; verify the live path (`write_phase_a_paper`) is untouched and stays green.

Delete from `writer.py`: `write_once`, `regenerate_data_efficiency_figure`, `regenerate_aug_depth_figure`, `regenerate_recent_runs_table`, `regenerate_best_per_config_table`, `ALL_RUNS_SQL`, `_format_all_runs`, and any private helper used ONLY by those (confirm via grep before deleting each). Remove `WriterPaths` fields used only by the deleted figure/table path (`paper_figures`, `paper_tables`) if no remaining code references them. Remove now-unused imports (e.g. `matplotlib`/`pyplot` if only the deleted figures imported it).

Delete from `__main__.py`: `cmd_write_once` and the `write-once` subparser; and `cmd_start_writer` + the `start-writer` subparser IF it calls `write_once` (confirm by reading it — if it drives the deleted path, remove it).

- [ ] **Step 1: Trim/adjust the writer tests first**

In `tests/test_writer_output.py` and `tests/test_writer_metric_resolution.py`, delete any test that imports or calls `write_once`, `regenerate_*`, `ALL_RUNS_SQL`, or `_format_all_runs`. Keep every test exercising `write_phase_a_paper`, `should_publish`, `compose_paper`, `writer_paths`. (Read the files; remove only the dead-path tests.)

- [ ] **Step 2: Confirm what references the to-be-deleted symbols**

Run:
```bash
grep -rnE "write_once|regenerate_data_efficiency_figure|regenerate_aug_depth_figure|regenerate_recent_runs_table|regenerate_best_per_config_table|ALL_RUNS_SQL|_format_all_runs" efferents/ tests/
```
Expected after Step 1: references only inside `writer.py` (definitions) and `__main__.py` (`cmd_write_once`/subparser). If anything else references them, STOP and report.

- [ ] **Step 3: Delete the dead code**

Remove the listed symbols from `writer.py` and the listed commands from `__main__.py`. Show the diff in your report.

- [ ] **Step 4: Verify imports resolve and the live path is intact**

Run:
```bash
uv run python -c "import efferents.agents.writer as w; assert hasattr(w,'write_phase_a_paper') and hasattr(w,'should_publish') and hasattr(w,'compose_paper'); assert not hasattr(w,'write_once'); print('writer live path intact, dead path gone')"
uv run python -c "import efferents.agents.__main__ as m; print('__main__ imports OK')"
```
Expected: both print success.

- [ ] **Step 5: Run the writer tests + full suite**

Run: `uv run pytest tests/test_writer_output.py tests/test_writer_metric_resolution.py -v && uv run pytest -q`
Expected: writer tests PASS; full suite no regressions.

- [ ] **Step 6: Verify no QML columns remain in writer.py**

Run: `grep -nE "e_w1|raw_q|aug_depth|radial_l2|val_x0_mse|active_frac|gen_max|aug_shared|cond_drop" efferents/agents/writer.py || echo "clean"`
Expected: `clean`.

- [ ] **Step 7: Commit**

```bash
git add efferents/agents/writer.py efferents/agents/__main__.py tests/test_writer_output.py tests/test_writer_metric_resolution.py
git commit -m "refactor(writer): delete dead auto_qml LaTeX/figure path (write_once + regenerate_*)"
```

---

## Task 5: Whole-feature verification

**Files:** none modified (verification + a manual smoke check).

- [ ] **Step 1: Full suite green**

Run: `uv run pytest -q`
Expected: all pass (the 3 skipped integration tests may remain skipped). If anything fails, fix within the owning task's file and re-run.

- [ ] **Step 2: No QML column names remain in the three target files**

Run:
```bash
grep -rnE "e_w1|raw_q|aug_depth|radial_l2|val_x0_mse|active_frac|gen_max_to_real_max|aug_shared_unitary|cond_drop_p|eval_kind" efferents/agents/analyst.py efferents/agents/progress.py efferents/agents/writer.py || echo "ALL CLEAN"
```
Expected: `ALL CLEAN`.

- [ ] **Step 3: Manual smoke-lab agnosticism check**

The smoke lab (`examples/smoke-lab/`, headline `synthetic_loss`) has a populated `lab/`. Force a digest + progress render against it and confirm clean output:
```bash
cd /Users/masha/Documents/efferents
uv run python -m efferents.agents progress-now --lab examples/smoke-lab/lab --context examples/smoke-lab/context 2>&1 | tail -3
grep -cE "e_w1|raw_q|aug_depth|eval_kind" examples/smoke-lab/lab/progress.html && echo "FOUND QML (bad)" || echo "progress.html clean of QML"
grep -c "synthetic_loss" examples/smoke-lab/lab/progress.html | sed 's/^/synthetic_loss occurrences: /'
```
Expected: `progress.html clean of QML` and a non-zero `synthetic_loss` count. (If `progress-now`'s flags differ, read `efferents/agents/__main__.py:cmd_progress_now` for the exact arg names and adjust.)

- [ ] **Step 4: Report readiness** — summarize: metrics_view added; analyst + progress config-driven & direction-aware; dead writer path removed; suite green; smoke progress.html clean.

---

## Self-Review Notes

- **Spec coverage:** §1 helper → Task 1 (full code + tests). §2 analyst → Task 2. §2 progress (+ researcher import) → Task 3. §2 writer/__main__ deletion → Task 4. Direction-awareness → `mv.improved`/`mv.best_run` (Task 1) consumed in Tasks 2–3, tested with a `max` case. State-key rename + fallback → Task 2 Step-3 change-list. Test plan (new + updates + trims) → Tasks 1–4 Step 1s. Acceptance (suite green + clean smoke progress.html) → Task 5.
- **Placeholder scan:** Task 1 is complete code. Tasks 2–4 are refactors of large existing files, so they specify exact change-lists + the pinning tests + verification greps rather than re-pasting whole files — the implementer reads the target file (instructed in the header). No "TBD"/"handle edge cases" left.
- **Consistency:** `metrics_view` API names (`finite`, `discover_columns`, `headline`, `panels`, `headline_value`, `best_run`, `improved`, `META_COLUMNS`) are defined in Task 1 and used verbatim in Tasks 2–3. `update_flat_digest_counter` keyword `current_best_headline` and state key `last_digest_best_headline` (with `last_digest_best_w1` fallback) are consistent between Task 2's change-list and its tests.
