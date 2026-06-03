# Agent-proposed domain-specific evals (v0.1.3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Researcher propose a domain-fitting headline metric per hypothesis, stored on the campaign, and read by the Writer, exporter, dashboard, and saturation report (with a `LabConfig` fallback) — so a non-QML lab can gate and emit a paper.

**Architecture:** The metric lives on the `campaigns` row (two new columns). The Researcher's `new_campaign` declaration carries `headline_metric` + `direction`; `campaign_insert` persists them. Every downstream consumer resolves `(metric, direction)` from the campaign row, falling back to `lab.get_config().metrics.headline` when null. Run-metric *storage* is unchanged — `exec.py:_persist_run_result` already ALTERs in any emitted metric column.

**Tech Stack:** Python 3.11+, SQLite (stdlib `sqlite3`), pydantic (existing schemas), pytest, `uv` for the venv.

**Spec:** [`docs/superpowers/specs/2026-06-03-agent-proposed-evals-design.md`](../specs/2026-06-03-agent-proposed-evals-design.md)

**Conventions:**
- Run tests with `uv run pytest`.
- The SQL-identifier sanitizer already exists: `efferents.lab._COL_NAME_RE` (`^[A-Za-z_][A-Za-z0-9_]*$`). Reuse it; do not invent a new one.
- Commit after each task.

---

### Task 1: Add `headline_metric` + `headline_direction` columns to the campaigns table

**Files:**
- Modify: `efferents/migrations/runner.py:42-44` (`_NEW_CAMPAIGN_COLUMNS`)
- Test: `tests/test_campaign_metric_migration.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_campaign_metric_migration.py
import sqlite3

from efferents.migrations.runner import apply_campaigns_migration


def _columns(db_path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(campaigns)")}
    finally:
        conn.close()


def test_migration_adds_metric_columns(tmp_path):
    db = tmp_path / "runs.sqlite"
    apply_campaigns_migration(db)
    cols = _columns(db)
    assert "headline_metric" in cols
    assert "headline_direction" in cols


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / "runs.sqlite"
    apply_campaigns_migration(db)
    apply_campaigns_migration(db)  # must not raise "duplicate column"
    cols = _columns(db)
    assert "headline_metric" in cols
    assert "headline_direction" in cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_campaign_metric_migration.py -v`
Expected: FAIL — `headline_metric` not in columns.

- [ ] **Step 3: Add the columns to the idempotent ALTER list**

In `efferents/migrations/runner.py`, replace the `_NEW_CAMPAIGN_COLUMNS` tuple:

```python
# Idempotent ALTERs for the campaigns table. SQLite can't conditionally add
# a column in DDL, so we PRAGMA first and ALTER only when missing.
_NEW_CAMPAIGN_COLUMNS = (
    ("student_id", "TEXT DEFAULT 'primary'"),
    # v0.1.3: the agent-proposed headline metric for this campaign. Null →
    # consumers fall back to LabConfig.metrics.headline.
    ("headline_metric", "TEXT"),
    ("headline_direction", "TEXT"),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_campaign_metric_migration.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add efferents/migrations/runner.py tests/test_campaign_metric_migration.py
git commit -m "feat(migrations): add campaign headline_metric + headline_direction columns"
```

---

### Task 2: `campaign_insert` accepts and persists the metric

**Files:**
- Modify: `efferents/agents/state.py:317-353` (`campaign_insert`)
- Test: `tests/test_campaign_insert_metric.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_campaign_insert_metric.py
import sqlite3

from efferents.migrations.runner import apply_campaigns_migration
from efferents.agents.state import campaign_insert


def _row(db, cid):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone())
    finally:
        conn.close()


def test_insert_with_metric(tmp_path):
    db = tmp_path / "runs.sqlite"
    apply_campaigns_migration(db)
    campaign_insert(
        db, id="c1", lab_id="L", question="q", hypothesis_path="h.md",
        hypothesis_hash="sha256:" + "a" * 64,
        headline_metric="synthetic_loss", headline_direction="min",
    )
    row = _row(db, "c1")
    assert row["headline_metric"] == "synthetic_loss"
    assert row["headline_direction"] == "min"


def test_insert_without_metric_leaves_nulls(tmp_path):
    db = tmp_path / "runs.sqlite"
    apply_campaigns_migration(db)
    campaign_insert(
        db, id="c2", lab_id="L", question="q", hypothesis_path="h.md",
        hypothesis_hash="sha256:" + "b" * 64,
    )
    row = _row(db, "c2")
    assert row["headline_metric"] is None
    assert row["headline_direction"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_campaign_insert_metric.py -v`
Expected: FAIL — `campaign_insert() got an unexpected keyword argument 'headline_metric'`.

- [ ] **Step 3: Add the params and persist them when the columns exist**

In `efferents/agents/state.py`, replace `campaign_insert` (lines 317-353) with:

```python
def campaign_insert(
    db_path: Path,
    *,
    id: str,
    lab_id: str,
    question: str,
    hypothesis_path: str,
    hypothesis_hash: str,
    opened_at: str | None = None,
    student_id: str = "primary",
    headline_metric: str | None = None,
    headline_direction: str | None = None,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        # Detect which optional columns the campaigns table has. Pre-migration
        # DBs (old tests / fresh-without-migration) lack student_id and the
        # v0.1.3 metric columns; build the INSERT from whatever is present so
        # the caller never blows up.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(campaigns)").fetchall()}
        names = ["id", "lab_id", "question", "hypothesis_path", "hypothesis_hash", "opened_at"]
        values = [id, lab_id, question, hypothesis_path, hypothesis_hash, opened_at or now_iso()]
        if "student_id" in cols:
            names.append("student_id")
            values.append(student_id)
        if "headline_metric" in cols:
            names.append("headline_metric")
            values.append(headline_metric)
        if "headline_direction" in cols:
            names.append("headline_direction")
            values.append(headline_direction)
        placeholders = ", ".join("?" for _ in names)
        conn.execute(
            f"INSERT INTO campaigns ({', '.join(names)}) VALUES ({placeholders})",
            values,
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_campaign_insert_metric.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the existing state tests to confirm no regression**

Run: `uv run pytest tests/ -k campaign -v`
Expected: PASS (existing campaign tests still green — the new params default to None).

- [ ] **Step 6: Commit**

```bash
git add efferents/agents/state.py tests/test_campaign_insert_metric.py
git commit -m "feat(state): campaign_insert persists agent-proposed headline metric"
```

---

### Task 3: `_best_metric` helper + Writer reads the campaign metric

**Files:**
- Modify: `efferents/agents/writer.py` (add `_best_metric`; rework the metric block in `write_phase_a_paper`, lines ~250-335)
- Test: `tests/test_writer_metric_resolution.py` (create)

- [ ] **Step 1: Write the failing test for the helper**

```python
# tests/test_writer_metric_resolution.py
from efferents.agents.writer import _best_metric, _resolve_campaign_metric


def test_best_metric_min():
    rows = [{"loss": 0.5}, {"loss": 0.2}, {"loss": None}, {}]
    assert _best_metric(rows, "loss", "min") == 0.2


def test_best_metric_max():
    rows = [{"acc": 0.5}, {"acc": 0.9}, {"acc": None}]
    assert _best_metric(rows, "acc", "max") == 0.9


def test_best_metric_absent_column_returns_none():
    rows = [{"other": 1.0}, {}]
    assert _best_metric(rows, "loss", "min") is None


def test_resolve_campaign_metric_prefers_campaign():
    campaign = {"headline_metric": "synthetic_loss", "headline_direction": "min"}
    assert _resolve_campaign_metric(campaign, default=("e_w1", "min")) == ("synthetic_loss", "min")


def test_resolve_campaign_metric_falls_back_when_null():
    campaign = {"headline_metric": None, "headline_direction": None}
    assert _resolve_campaign_metric(campaign, default=("e_w1", "min")) == ("e_w1", "min")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_writer_metric_resolution.py -v`
Expected: FAIL — `cannot import name '_best_metric'`.

- [ ] **Step 3: Add the helpers near `_resolve_code_sha` in writer.py**

Add these two functions to `efferents/agents/writer.py` (e.g. just below `_resolve_code_sha`, around line 125):

```python
def _best_metric(runs: list[dict], col: str, direction: str) -> float | None:
    """Return the best value of `col` across runs. min when direction=='min',
    max otherwise. None when no run carries the column."""
    vals = [r[col] for r in runs if r.get(col) is not None]
    if not vals:
        return None
    return min(vals) if direction == "min" else max(vals)


def _resolve_campaign_metric(
    campaign: dict, *, default: tuple[str, str]
) -> tuple[str, str]:
    """Resolve (metric, direction) for a campaign, preferring the
    campaign-declared values and falling back to `default` when null."""
    metric = campaign.get("headline_metric") or default[0]
    direction = campaign.get("headline_direction") or default[1]
    if direction not in ("min", "max"):
        direction = default[1]
    return metric, direction
```

- [ ] **Step 4: Run the helper test to verify it passes**

Run: `uv run pytest tests/test_writer_metric_resolution.py -v`
Expected: PASS.

- [ ] **Step 5: Rewire `write_phase_a_paper` to use the resolved metric**

In `efferents/agents/writer.py:write_phase_a_paper`, make these edits inside the function body:

Replace the nested `_best_e_w1` definition (lines ~250-252) with nothing (delete it), and after `campaign_runs`/`other_runs` are loaded (line ~275) insert metric resolution:

```python
    from efferents import lab as _lab_cfg  # local import; cfg may be unset in unit tests
    try:
        _default = (_lab_cfg.get_config().metrics.headline.column,
                    _lab_cfg.get_config().metrics.headline.direction)
    except Exception:
        _default = ("e_w1", "min")
    metric, direction = _resolve_campaign_metric(campaign, default=_default)

    candidate_value = _best_metric(campaign_runs, metric, direction)
    baseline_value = _best_metric(other_runs, metric, direction)
```

(Delete the old `candidate_value = _best_e_w1(campaign_runs)` / `baseline_value = _best_e_w1(other_runs)` lines.)

Then update the baseline fallback to be direction-aware (replace the `baseline_value is None` block, lines ~285-286):

```python
    if baseline_value is None:
        # No baseline: assume headroom in the improving direction so the gate
        # can still pass. min → baseline 20% higher; max → 20% lower.
        baseline_value = candidate_value * (1.2 if direction == "min" else 0.8)
```

Then in the `GateInputs(...)` construction (line ~291) change `primary_metric_name="e_w1"` to `primary_metric_name=metric`.

Then in the `metric_provenance` build (lines ~318-335), replace every `r.get("e_w1")`/`r["e_w1"]`/`"name": "e_w1"` with the resolved `metric`:

```python
    runs_by_seed: dict[int, list[float]] = {}
    run_ids: list[str] = []
    for r in campaign_runs:
        if r.get(metric) is None:
            continue
        seed = r.get("seed", 0) or 0
        runs_by_seed.setdefault(seed, []).append(r[metric])
        run_ids.append(r["run_id"])

    metric_provenance = [
        {
            "name": metric,
            "value": candidate_value,
            "delta_vs_baseline": candidate_value - baseline_value,
            "runs": run_ids or [campaign_id],
            "seeds": list(runs_by_seed.keys()) or [0],
        }
    ]
```

Finally, update the notebook-skip message (lines ~306-309) and the `headline`/`delta_pct` lines (~379-386) that interpolate `e_w1` / `candidate_value` to use `metric` in the label text and keep `delta_pct` computed as `100*(baseline-candidate)/baseline` for `min` or `100*(candidate-baseline)/baseline` for `max`:

```python
    delta_pct = (
        100.0 * (baseline_value - candidate_value) / baseline_value
        if direction == "min" and baseline_value
        else (100.0 * (candidate_value - baseline_value) / baseline_value
              if baseline_value else 0.0)
    )
    headline = (
        f"{novelty_claim} — {metric} {candidate_value:.3f} vs baseline "
        f"{baseline_value:.3f} ({delta_pct:+.1f}%)"
    )
```

- [ ] **Step 6: Write a Writer integration test on a non-e_w1 metric**

```python
# append to tests/test_writer_metric_resolution.py
import sqlite3
from pathlib import Path


def _seed_runs(db: Path, campaign_id: str, metric: str, vals: list[float]):
    conn = sqlite3.connect(db)
    conn.execute(
        f"CREATE TABLE runs (run_id TEXT, started_at TEXT, campaign_id TEXT, "
        f"seed INTEGER, {metric} REAL)"
    )
    for i, v in enumerate(vals):
        conn.execute(
            "INSERT INTO runs (run_id, started_at, campaign_id, seed, " + metric + ") "
            "VALUES (?, ?, ?, ?, ?)",
            (f"r{i}", "2026-01-01T00:00:00+00:00", campaign_id, 0, v),
        )
    conn.commit()
    conn.close()


def test_best_metric_reads_campaign_runs(tmp_path):
    db = tmp_path / "runs.sqlite"
    _seed_runs(db, "c1", "synthetic_loss", [0.4, 0.1, 0.3])
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM runs WHERE campaign_id='c1'")]
    conn.close()
    assert _best_metric(rows, "synthetic_loss", "min") == 0.1
```

- [ ] **Step 7: Run tests + the existing writer suite**

Run: `uv run pytest tests/test_writer_metric_resolution.py tests/ -k writer -v`
Expected: new tests PASS; existing non-QML writer tests PASS. (QML `e_w1`-asserting writer tests move in Task 8 — if they fail here on `e_w1`, that is expected and resolved in Task 8.)

- [ ] **Step 8: Commit**

```bash
git add efferents/agents/writer.py tests/test_writer_metric_resolution.py
git commit -m "feat(writer): gate + provenance on the campaign's headline metric (config fallback)"
```

---

### Task 4: Exporter reads the campaign metric

**Files:**
- Modify: `efferents/agents/federation.py:export_paper_bundle` (lines ~465-509, 552-571)
- Test: `tests/test_export_bundle_metric.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_bundle_metric.py
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest

from efferents.agents import federation
from efferents.migrations.runner import apply_campaigns_migration
from efferents.agents.state import campaign_insert


def _setup(tmp_path, metric):
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "c1.md").write_text("---\nlab_id: L\n---\n## Motivation\nx\n")
    db = tmp_path / "runs.sqlite"
    apply_campaigns_migration(db)
    campaign_insert(
        db, id="c1", lab_id="L", question="q", hypothesis_path="h.md",
        hypothesis_hash="sha256:" + "a" * 64,
        headline_metric=metric, headline_direction="min",
    )
    conn = sqlite3.connect(db)
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS runs (run_id TEXT, started_at TEXT, "
        f"campaign_id TEXT, seed INTEGER, config_yaml TEXT, {metric} REAL)"
    )
    conn.execute(
        f"INSERT INTO runs (run_id, started_at, campaign_id, seed, {metric}) "
        f"VALUES ('r0','2026-01-01T00:00:00+00:00','c1',0,0.12)"
    )
    conn.commit()
    conn.close()
    return paper_dir, db


def test_export_provenance_uses_campaign_metric(tmp_path):
    paper_dir, db = _setup(tmp_path, "synthetic_loss")
    out = tmp_path / "bundle.tar.gz"
    federation.export_paper_bundle(
        campaign_id="c1", db=db, paper_dir=paper_dir, out_path=out,
        lab_id="L", code_repo="https://example.com/r", code_sha="abc123",
    )
    with tarfile.open(out) as tar:
        manifest = json.loads(tar.extractfile("manifest.json").read())
        metrics = json.loads(tar.extractfile("metric_provenance.json").read())
    assert manifest["primary_metric"]["name"] == "synthetic_loss"
    assert metrics[0]["synthetic_loss"] == 0.12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export_bundle_metric.py -v`
Expected: FAIL — `primary_metric["name"]` is `"e_w1"`, not `"synthetic_loss"`.

- [ ] **Step 3: Resolve the metric in `export_paper_bundle` and use it**

In `efferents/agents/federation.py:export_paper_bundle`, after `campaign_row` is loaded (line ~465) add:

```python
    from efferents import lab as _lab_cfg
    try:
        _default = (_lab_cfg.get_config().metrics.headline.column,
                    _lab_cfg.get_config().metrics.headline.direction)
    except Exception:
        _default = ("e_w1", "min")
    metric = campaign_row.get("headline_metric") or _default[0]
```

Replace the `metric_provenance` comprehension (lines ~504-509):

```python
    metric_provenance: list[dict[str, Any]] = [
        {"run_id": r.get("run_id"), metric: r.get(metric),
         "seed": r.get("seed"), "model": r.get("model")}
        for r in runs
    ]
```

Replace the manifest `primary_metric` block (lines ~565-569):

```python
            "primary_metric": (
                {"name": metric, "value": runs[0].get(metric),
                 "run_id": runs[0]["run_id"]}
                if runs else None
            ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_export_bundle_metric.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add efferents/agents/federation.py tests/test_export_bundle_metric.py
git commit -m "feat(federation): export bundle provenance reads the campaign metric"
```

---

### Task 5: Researcher proposes the eval (thread + prompt + validate)

**Files:**
- Modify: `efferents/agents/researcher.py:911-920` (the `_campaign_insert` call)
- Modify: `efferents/agents/prompts/student.md` (add the eval-design instruction)
- Test: `tests/test_researcher_proposes_metric.py` (create)

- [ ] **Step 1: Write the failing test for threading + validation**

```python
# tests/test_researcher_proposes_metric.py
from efferents.agents.researcher import _campaign_metric_from_proposal


def test_valid_metric_passes_through():
    nc = {"headline_metric": "synthetic_loss", "direction": "min"}
    assert _campaign_metric_from_proposal(nc) == ("synthetic_loss", "min")


def test_invalid_metric_name_drops_to_none():
    nc = {"headline_metric": "bad name!", "direction": "min"}
    assert _campaign_metric_from_proposal(nc) == (None, None)


def test_bad_direction_drops_to_none():
    nc = {"headline_metric": "loss", "direction": "sideways"}
    assert _campaign_metric_from_proposal(nc) == (None, None)


def test_missing_metric_is_none():
    assert _campaign_metric_from_proposal({}) == (None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_researcher_proposes_metric.py -v`
Expected: FAIL — `cannot import name '_campaign_metric_from_proposal'`.

- [ ] **Step 3: Add the validation helper to researcher.py**

Add near the top-level helpers of `efferents/agents/researcher.py` (e.g. below `_slugify`, around line 86):

```python
from efferents.lab import _COL_NAME_RE  # SQL-identifier sanitizer


def _campaign_metric_from_proposal(
    new_campaign: dict,
) -> tuple[str | None, str | None]:
    """Extract + validate (headline_metric, direction) from a Student's
    new_campaign declaration. Returns (None, None) when absent or invalid,
    so the campaign falls back to the LabConfig default."""
    metric = (new_campaign.get("headline_metric") or "").strip()
    direction = (new_campaign.get("direction") or "").strip()
    if not metric or not _COL_NAME_RE.match(metric):
        return (None, None)
    if direction not in ("min", "max"):
        return (None, None)
    return (metric, direction)
```

- [ ] **Step 4: Run the helper test to verify it passes**

Run: `uv run pytest tests/test_researcher_proposes_metric.py -v`
Expected: PASS.

- [ ] **Step 5: Thread the validated metric into the `_campaign_insert` call**

In `efferents/agents/researcher.py`, just before the `_campaign_insert(` call (line ~912) add:

```python
            _hm, _hd = _campaign_metric_from_proposal(new_campaign)
```

and add the two kwargs to the call:

```python
            _campaign_insert(
                paths.runs_db,
                id=campaign_id,
                lab_id=_lab.LAB_ID,
                question=new_campaign.get("question", ""),
                hypothesis_path=str(gate_result.path.relative_to(paths.root.parent)),
                hypothesis_hash=gate_result.hash,
                student_id=student_id,
                headline_metric=_hm,
                headline_direction=_hd,
            )
```

- [ ] **Step 6: Add the eval-design instruction to the Student prompt**

In `efferents/agents/prompts/student.md`, inside the section that documents the `new_campaign` object, add this bullet (keep `str.format` braces escaped as `{{`/`}}` — `new_campaign` is JSON the Student emits, so literal braces in any example must be doubled):

```markdown
When you declare a `new_campaign`, also design its eval:
- `headline_metric`: the single metric name (a valid identifier: letters,
  digits, underscores) that would corroborate or refute this hypothesis.
- `direction`: `"min"` if lower is better, `"max"` if higher is better.
Your run command MUST emit this metric under the stdout `metrics` JSON object.
If you omit these, the lab falls back to its default headline metric
(`{headline_metric}`, optimized toward `{headline_direction}`).
```

- [ ] **Step 7: Verify the prompt still renders (no unescaped braces)**

Run: `uv run pytest tests/test_prompt_loader.py -v`
Expected: PASS — the parametrized "renders without error" test covers `student.md`.

- [ ] **Step 8: Commit**

```bash
git add efferents/agents/researcher.py efferents/agents/prompts/student.md tests/test_researcher_proposes_metric.py
git commit -m "feat(researcher): propose + validate a per-campaign headline metric"
```

---

### Task 6: Dashboard auto-discovery of observed metric columns

**Files:**
- Modify: `efferents/agents/progress.py:54-62` (`_panel_metrics`)
- Test: `tests/test_progress_autodiscovery.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_progress_autodiscovery.py
import sqlite3

from efferents.agents.progress import _discover_metric_columns

_META = {
    "run_id", "started_at", "ended_at", "config_path", "campaign_id",
    "researcher_mode", "student_id", "git_commit", "duration_seconds", "seed",
    "config_yaml", "eval_kind",
}


def test_discovers_non_meta_real_columns(tmp_path):
    db = tmp_path / "runs.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT, started_at TEXT, campaign_id TEXT, "
        "seed INTEGER, synthetic_loss REAL, extra_metric REAL)"
    )
    conn.commit()
    conn.close()
    found = _discover_metric_columns(db, meta=_META)
    assert "synthetic_loss" in found
    assert "extra_metric" in found
    assert "run_id" not in found
    assert "campaign_id" not in found
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_progress_autodiscovery.py -v`
Expected: FAIL — `cannot import name '_discover_metric_columns'`.

- [ ] **Step 3: Add discovery + union into `_panel_metrics`**

In `efferents/agents/progress.py`, add the discovery helper and the meta-column set above `_panel_metrics`, then union it in:

```python
_META_COLUMNS = frozenset({
    "run_id", "started_at", "ended_at", "config_path", "campaign_id",
    "researcher_mode", "student_id", "git_commit", "duration_seconds", "seed",
    "config_yaml", "eval_kind",
})


def _discover_metric_columns(db_path, *, meta=_META_COLUMNS) -> list[str]:
    """Metric columns present in the runs table, minus known meta columns."""
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path
    db_path = _Path(db_path)
    if not db_path.exists():
        return []
    conn = _sqlite3.connect(db_path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(runs)")]
    except _sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    return [c for c in cols if c not in meta]


def _panel_metrics(db_path=None) -> list[tuple[str, str, float | None]]:
    """Per-lab panel definitions: LabConfig panels unioned with any metric
    columns actually observed in the runs table (agent-proposed metrics the
    lab never declared still appear)."""
    cfg = _lab.get_config()
    panels = [(p.column, p.label, p.target) for p in cfg.metrics.panels]
    declared = {p[0] for p in panels}
    if db_path is not None:
        for col in _discover_metric_columns(db_path):
            if col not in declared:
                panels.append((col, col, None))
    return panels
```

Update the single call site (line ~260, inside `_render_html`/`write_progress`) to pass the runs db path. Find the `zip(axes, _panel_metrics())` line and change it to `zip(axes, _panel_metrics(paths.runs_db))` (the `paths` object is in scope there — it exposes `runs_db`, the same attribute the writer uses).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_progress_autodiscovery.py -v`
Expected: PASS.

- [ ] **Step 5: Run existing progress tests**

Run: `uv run pytest tests/ -k progress -v`
Expected: PASS (config-only panels still work; `db_path=None` preserves old behavior).

- [ ] **Step 6: Commit**

```bash
git add efferents/agents/progress.py tests/test_progress_autodiscovery.py
git commit -m "feat(progress): dashboard auto-discovers observed metric columns"
```

---

### Task 7: Saturation report light generalization

**Files:**
- Modify: `efferents/agents/researcher.py:_saturation_report` + `PRIMARY_METRICS` (lines ~122-260)
- Test: `tests/test_saturation_generalized.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_saturation_generalized.py
import sqlite3

from efferents.agents.researcher import _observed_metric_columns


def test_observed_metrics_excludes_meta(tmp_path):
    db = tmp_path / "runs.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (run_id TEXT, started_at TEXT, campaign_id TEXT, "
        "seed INTEGER, config_yaml TEXT, synthetic_loss REAL)"
    )
    conn.commit()
    conn.close()
    cols = _observed_metric_columns(db)
    assert "synthetic_loss" in cols
    assert "run_id" not in cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_saturation_generalized.py -v`
Expected: FAIL — `cannot import name '_observed_metric_columns'`.

- [ ] **Step 3: Add the discovery helper and use it for the metric set**

In `efferents/agents/researcher.py`, add a discovery helper (reuse the progress meta set by importing it):

```python
from efferents.agents.progress import _discover_metric_columns


def _observed_metric_columns(db_path) -> list[str]:
    """Metric columns present in runs, for saturation analysis. Falls back to
    the QML PRIMARY_METRICS set only when it is actually present."""
    found = _discover_metric_columns(db_path)
    return found or [m for m in PRIMARY_METRICS]
```

Then in `_saturation_report`, replace the hardcoded iteration over `PRIMARY_METRICS` with `metrics = _observed_metric_columns(paths.runs_db)` and iterate over `metrics` instead. Keep the existing `try/except sqlite3.OperationalError` guard that no-ops when the needed columns are absent (so a thin schema still degrades gracefully). The "≥2 of 3 saturated" rule becomes "≥ ceil(len(metrics)/2) saturated, min 1" — compute the threshold as `max(1, (len(metrics) + 1) // 2)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_saturation_generalized.py -v`
Expected: PASS.

- [ ] **Step 5: Run existing researcher tests**

Run: `uv run pytest tests/ -k researcher -v`
Expected: PASS (QML path still uses PRIMARY_METRICS when those columns are present).

- [ ] **Step 6: Commit**

```bash
git add efferents/agents/researcher.py tests/test_saturation_generalized.py
git commit -m "feat(researcher): saturation report operates over observed metric columns"
```

---

### Task 8: Move QML-coupled tests to lab_reference + extend the acceptance gate

**Files:**
- Move: any test under `tests/` asserting on `e_w1` in writer/exporter output → `tests/lab_reference/`
- Modify: `tests/integration/test_smoke_lab_e2e.py` (extend acceptance)
- Test: the moved + extended tests

- [ ] **Step 1: Find the QML-coupled tests**

Run: `grep -rln "e_w1" tests/ --include=*.py`
Expected: a list of test files. For each that asserts `e_w1` as a *framework* expectation (writer/exporter), it is now lab-specific.

- [ ] **Step 2: Move them under `tests/lab_reference/` with a skip marker**

For each identified file, `git mv` it into `tests/lab_reference/` and add at the top:

```python
import pytest

pytestmark = pytest.mark.skip(
    reason="QML-specific; re-covered by auto-qml's lab override after migration"
)
```

(`tests/lab_reference/` is the existing home for QML-coupled tests per `tests/README.md`.)

- [ ] **Step 3: Run the default suite to confirm green**

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration -q`
Expected: PASS — no framework test asserts `e_w1` anymore.

- [ ] **Step 4: Extend the smoke-lab E2E acceptance**

In `tests/integration/test_smoke_lab_e2e.py`, add an assertion that a paper is composed for the smoke lab. After the existing run-row assertions, add:

```python
    # v0.1.3 acceptance: the Researcher proposed synthetic_loss/min, the run
    # emitted it, and the Writer composed a paper for the smoke lab.
    papers = list((lab_root / "papers").glob("*.md"))
    assert papers, "expected at least one composed paper under lab/papers/"
    text = papers[0].read_text()
    assert "synthetic_loss" in text
```

(Keep `@pytest.mark.integration`; this opt-in test needs `ANTHROPIC_API_KEY`.)

- [ ] **Step 5: Run the integration test (requires API key)**

Run: `uv run pytest tests/integration/test_smoke_lab_e2e.py -m integration -v`
Expected: PASS when `ANTHROPIC_API_KEY` is set; SKIP otherwise.

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test: relocate e_w1-coupled tests to lab_reference; assert smoke lab composes a paper"
```

---

### Task 9: Version bump + verification note

**Files:**
- Modify: `pyproject.toml` (version → `0.1.3`)
- Create: `docs/superpowers/specs/2026-06-03-eval-decouple-verification.md`

- [ ] **Step 1: Bump the version**

In `pyproject.toml`, set `version = "0.1.3"`.

- [ ] **Step 2: Run the full non-integration suite**

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration -q`
Expected: PASS. Capture the count for the note.

- [ ] **Step 3: Manual smoke-lab verification**

Run (in a tmp copy of `examples/smoke-lab/`, with `ANTHROPIC_API_KEY` set):

```bash
.venv/bin/efferents start --submission examples/smoke-lab/
```

Let it run ~2 minutes, then confirm:
- A campaigns row has `headline_metric=synthetic_loss` (`sqlite3 examples/smoke-lab/lab/runs.sqlite "SELECT id, headline_metric, headline_direction FROM campaigns"`).
- A paper exists under `examples/smoke-lab/lab/papers/`.
- The dashboard (`lab/progress/index.html`) shows a `synthetic_loss` panel.

- [ ] **Step 4: Write the verification note**

Create `docs/superpowers/specs/2026-06-03-eval-decouple-verification.md` documenting: the test count from Step 2, the manual observations from Step 3 (campaign metric, composed paper, dashboard panel), and confirmation that the smoke lab now emits a paper.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml docs/superpowers/specs/2026-06-03-eval-decouple-verification.md
git commit -m "chore: bump to 0.1.3 — agent-proposed evals; smoke lab emits a paper"
```

---

## Notes for the implementer

- **Fallback is load-bearing.** Every consumer must tolerate a null campaign metric and a LabConfig that isn't set (unit tests run without `set_config`). The `try/except → ("e_w1","min")` pattern in Tasks 3-4 handles the latter.
- **No storage migration for metrics.** Run-metric columns are added on demand by `exec.py:_persist_run_result`. Do not add metric columns to `ensure_runs_table` for agent-proposed metrics — they appear when the first run emits them.
- **QML stays working** through the config fallback and the `lab_reference` test relocation; auto-qml restores its eval set via its own prompt/config override after it migrates.
