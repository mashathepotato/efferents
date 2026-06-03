# Writer cadence in the orchestrator (v0.1.4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the running daemon compose papers on its own by adding a throttled `_maybe_write` step to the orchestrator loop that calls `write_phase_a_paper` on open campaigns clearing the publish gate.

**Architecture:** A new `Orchestrator._maybe_write()` mirrors `_maybe_digest`/`_maybe_code`: a run-count/time cursor in `state.json` throttles it; when due it scans `campaign_open_list`, skips campaigns that already have a `lab/paper/<id>.md`, and calls `write_phase_a_paper` (whose cheap `should_publish` gate runs before any LLM call). It is wired into both `step()` branches after `_maybe_code()`, and in the no-proposal branch before `close_stale_campaigns`.

**Tech Stack:** Python 3.11+, SQLite (stdlib), pytest, `uv`.

**Spec:** [`docs/superpowers/specs/2026-06-03-writer-cadence-design.md`](../specs/2026-06-03-writer-cadence-design.md)

**Conventions:**
- Run tests with `uv run pytest`.
- A test `conftest.py` autouses a minimal `LabConfig` (headline `synthetic_loss`); `_lab.LAB_ID` resolves to that config's `lab_id`. Tests that seed a campaign must use that same `lab_id` so `campaign_open_list` finds it.
- Commit after each task.

**Key code facts (verified):**
- `Orchestrator.__init__(*, lab_dir="lab", context_dir="context", daily_cap_usd=100.0, runs_per_digest=40, hours_per_digest=4.0, runs_per_coder=8, hours_per_coder=6.0, dry_run=False, startup_message=None)`. When `dry_run=True`, `self.client` stays `None` and `anthropic.Anthropic()` is NOT constructed (so no API key needed in tests).
- The constructor already calls `apply_campaigns_migration(self.paths.runs_db)` but does NOT create the `runs` table; tests seed it.
- `_hours_since(iso) -> float` is a module-level function in orchestrator.py. `runs_count`, `load_state`, `save_state`, `notebook_append`, `now_iso`, `notify_all` are imported. `_lab_label()` exists.
- `writer.writer_paths(*, lab, paper, reports, context) -> WriterPaths` sets `runs_db = lab/"runs.sqlite"`, `notebook = lab/"lab_notebook.md"`, `state = lab/"state.json"`, `budget = lab/"budget.jsonl"`, `paper = paper`. `write_phase_a_paper(paths, campaign, client, *, gain_threshold=0.05, model=..., budget=None) -> str | None`.
- `campaign_open_list(db_path, lab_id) -> list[dict]` (SELECT *, so dicts carry `headline_metric`/`headline_direction`).
- `step()` no-proposal branch calls `self._maybe_digest(); self._maybe_code(); closed = close_stale_campaigns(self.paths.runs_db, lab_id=_lab.LAB_ID)` then `time.sleep(60)`. Ran branch calls `self._maybe_digest(); self._maybe_code()` then returns.

---

### Task 1: Add `_maybe_write` + cadence config + imports

**Files:**
- Modify: `efferents/agents/orchestrator.py` (imports ~line 22 and ~line 26-40; constructor ~line 108-130; add method near `_maybe_code` ~line 283)
- Test: `tests/test_orchestrator_writer_cadence.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_orchestrator_writer_cadence.py
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from efferents.agents import orchestrator as orch
from efferents.agents.state import campaign_insert, now_iso, load_state, save_state
from efferents.migrations.runner import apply_campaigns_migration
from efferents import lab as _lab


def _seed_runs(db: Path, n: int):
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS runs (run_id TEXT, started_at TEXT, "
        "campaign_id TEXT, synthetic_loss REAL)"
    )
    for i in range(n):
        conn.execute(
            "INSERT INTO runs (run_id, started_at, campaign_id, synthetic_loss) "
            "VALUES (?, ?, ?, ?)",
            (f"r{i}", "2026-01-01T00:00:00+00:00", "c1", 0.1),
        )
    conn.commit()
    conn.close()


def _make_orch(tmp_path):
    """Build an Orchestrator without needing an API key, then flip into the
    non-dry path with a fake client."""
    o = orch.Orchestrator(
        lab_dir=tmp_path / "lab",
        context_dir=tmp_path / "context",
        dry_run=True,
    )
    o.dry_run = False
    o.client = object()  # never used: write_phase_a_paper is monkeypatched
    return o


def _seed_campaign(o):
    apply_campaigns_migration(o.paths.runs_db)
    campaign_insert(
        o.paths.runs_db,
        id="c1",
        lab_id=_lab.LAB_ID,
        question="q",
        hypothesis_path="h.md",
        hypothesis_hash="sha256:" + "a" * 64,
        headline_metric="synthetic_loss",
        headline_direction="min",
    )


def test_writes_when_due(tmp_path, monkeypatch):
    o = _make_orch(tmp_path)
    _seed_campaign(o)
    _seed_runs(o.paths.runs_db, 25)  # >= runs_per_paper (20)

    # Stub notify so the non-None (published) path doesn't fire a real
    # OS/ntfy notification during the test.
    monkeypatch.setattr(orch, "notify_all", lambda **k: None)

    calls = []
    monkeypatch.setattr(
        orch.writer, "write_phase_a_paper",
        lambda paths, campaign, **kw: calls.append(campaign["id"]) or "artifact",
    )
    o._maybe_write()
    assert calls == ["c1"]
    state = load_state(o.paths.state)
    assert state["last_paper_runs"] == 25


def test_skips_when_below_threshold(tmp_path, monkeypatch):
    o = _make_orch(tmp_path)
    _seed_campaign(o)
    _seed_runs(o.paths.runs_db, 25)
    # Cursor recent: only 0 new runs since last paper, ts = now.
    state = load_state(o.paths.state)
    state["last_paper_runs"] = 25
    state["last_paper_ts"] = now_iso()
    save_state(o.paths.state, state)

    calls = []
    monkeypatch.setattr(
        orch.writer, "write_phase_a_paper",
        lambda *a, **k: calls.append(1),
    )
    o._maybe_write()
    assert calls == []


def test_skips_campaign_with_existing_paper(tmp_path, monkeypatch):
    o = _make_orch(tmp_path)
    _seed_campaign(o)
    _seed_runs(o.paths.runs_db, 25)
    # Pre-create the paper file for c1 under lab/paper/.
    paper_dir = o.paths.runs_db.parent / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "c1.md").write_text("already written")

    calls = []
    monkeypatch.setattr(
        orch.writer, "write_phase_a_paper",
        lambda paths, campaign, **kw: calls.append(campaign["id"]),
    )
    o._maybe_write()
    assert calls == []


def test_budget_pause_short_circuits(tmp_path, monkeypatch):
    o = _make_orch(tmp_path)
    _seed_campaign(o)
    _seed_runs(o.paths.runs_db, 25)
    monkeypatch.setattr(o.budget, "should_pause", lambda: True)

    calls = []
    monkeypatch.setattr(
        orch.writer, "write_phase_a_paper",
        lambda *a, **k: calls.append(1),
    )
    o._maybe_write()
    assert calls == []
    # Cursor not bumped, so it retries when budget frees.
    state = load_state(o.paths.state)
    assert "last_paper_runs" not in state or state.get("last_paper_runs") == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator_writer_cadence.py -v`
Expected: FAIL — `module 'efferents.agents.orchestrator' has no attribute 'writer'` (and `_maybe_write` undefined).

- [ ] **Step 3: Add imports**

In `efferents/agents/orchestrator.py`, change the agents import line:

```python
from efferents.agents import analyst, coder, executor, researcher, writer
```

and add `campaign_open_list` to the `from efferents.agents.state import (...)` block (alongside `campaign_close`):

```python
    campaign_close,
    campaign_open_list,
    campaign_stale_open,
```

- [ ] **Step 4: Add constructor params**

In `Orchestrator.__init__`, add two keyword params after `hours_per_coder: float = 6.0,`:

```python
        runs_per_paper: int = 20,
        hours_per_paper: float = 6.0,
```

and assign them in the body after `self.hours_per_coder = hours_per_coder`:

```python
        self.runs_per_paper = runs_per_paper
        self.hours_per_paper = hours_per_paper
```

- [ ] **Step 5: Add the `_maybe_write` method**

Add this method to the `Orchestrator` class, right after `_maybe_code` (~line 338):

```python
    def _maybe_write(self) -> None:
        if self.dry_run or self.client is None:
            return
        state = load_state(self.paths.state)
        n_runs = runs_count(self.paths.runs_db)
        last_runs = int(state.get("last_paper_runs", 0))
        last_ts = state.get("last_paper_ts")
        if (n_runs - last_runs) < self.runs_per_paper and _hours_since(last_ts) < self.hours_per_paper:
            return
        if self.budget.should_pause():
            return  # do NOT bump the cursor; retry when budget frees

        lab_root = self.paths.runs_db.parent
        wpaths = writer.writer_paths(
            lab=lab_root,
            paper=lab_root / "paper",
            reports=lab_root / "reports",
            context=self.context_dir,
        )
        for campaign in campaign_open_list(self.paths.runs_db, _lab.LAB_ID):
            cid = campaign["id"]
            if (wpaths.paper / f"{cid}.md").exists():
                continue  # one paper per campaign; no re-write / re-review
            try:
                artifact = writer.write_phase_a_paper(
                    wpaths, campaign, client=self.client, budget=self.budget,
                )
                if artifact is not None:
                    notify_all(
                        title=f"{_lab_label()}: paper composed",
                        message=f"campaign {cid}",
                    )
                    notebook_append(
                        self.paths.notebook,
                        f"## {now_iso()} — Writer composed a paper for {cid}\n",
                    )
            except Exception as e:
                notebook_append(
                    self.paths.notebook,
                    f"## {now_iso()} — Writer step FAILED for {cid}: {type(e).__name__}: {e}\n",
                )

        state["last_paper_runs"] = n_runs
        state["last_paper_ts"] = now_iso()
        save_state(self.paths.state, state)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_writer_cadence.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add efferents/agents/orchestrator.py tests/test_orchestrator_writer_cadence.py
git commit -m "feat(orchestrator): add _maybe_write Writer cadence (throttled, skip-existing, budget-guarded)"
```

---

### Task 2: Wire `_maybe_write` into `step()`

**Files:**
- Modify: `efferents/agents/orchestrator.py` (`step()` ~line 340-368)
- Test: `tests/test_orchestrator_writer_cadence.py` (append)

- [ ] **Step 1: Write the failing wiring test**

Append to `tests/test_orchestrator_writer_cadence.py`:

```python
def test_step_calls_maybe_write_before_close_stale(tmp_path, monkeypatch):
    o = _make_orch(tmp_path)
    _seed_campaign(o)

    order = []
    monkeypatch.setattr(o, "_refill_queue", lambda: 0)
    monkeypatch.setattr(orch, "queue_pop", lambda q: None)  # force no-proposal branch
    monkeypatch.setattr(o, "_maybe_digest", lambda: order.append("digest"))
    monkeypatch.setattr(o, "_maybe_code", lambda: order.append("code"))
    monkeypatch.setattr(o, "_maybe_write", lambda: order.append("write"))
    monkeypatch.setattr(orch, "close_stale_campaigns", lambda *a, **k: order.append("close") or [])
    monkeypatch.setattr(orch.time, "sleep", lambda s: None)

    result = o.step()
    assert result["event"] == "no_proposal"
    assert "write" in order
    assert order.index("write") < order.index("close")


def test_step_ran_branch_calls_maybe_write(tmp_path, monkeypatch):
    o = _make_orch(tmp_path)
    _seed_campaign(o)

    called = []
    monkeypatch.setattr(o, "_refill_queue", lambda: 0)
    monkeypatch.setattr(orch, "queue_pop", lambda q: {"name": "p"})  # force ran branch
    monkeypatch.setattr(orch.executor, "execute", lambda **k: {"ok": True, "name": "p"})
    monkeypatch.setattr(o, "_maybe_digest", lambda: None)
    monkeypatch.setattr(o, "_maybe_code", lambda: None)
    monkeypatch.setattr(o, "_maybe_write", lambda: called.append("write"))

    result = o.step()
    assert result["event"] == "ran"
    assert called == ["write"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator_writer_cadence.py -k step -v`
Expected: FAIL — `_maybe_write` is never called by `step()` yet (`order`/`called` lacks "write").

- [ ] **Step 3: Wire into both branches**

In `step()`, the no-proposal branch currently reads:

```python
            self._maybe_digest()
            self._maybe_code()
            closed = close_stale_campaigns(self.paths.runs_db, lab_id=_lab.LAB_ID)
```

Insert `self._maybe_write()` between `_maybe_code()` and `close_stale_campaigns`:

```python
            self._maybe_digest()
            self._maybe_code()
            self._maybe_write()
            closed = close_stale_campaigns(self.paths.runs_db, lab_id=_lab.LAB_ID)
```

In the ran branch, currently:

```python
        outcome = executor.execute(paths=self.paths, proposal=proposal)
        self._maybe_digest()
        self._maybe_code()
        return {"event": "ran", "added": n_added, "outcome_ok": outcome.get("ok"), "name": outcome.get("name")}
```

Insert `self._maybe_write()` after `_maybe_code()`:

```python
        outcome = executor.execute(paths=self.paths, proposal=proposal)
        self._maybe_digest()
        self._maybe_code()
        self._maybe_write()
        return {"event": "ran", "added": n_added, "outcome_ok": outcome.get("ok"), "name": outcome.get("name")}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_writer_cadence.py -v`
Expected: PASS (all 6 tests).

- [ ] **Step 5: Commit**

```bash
git add efferents/agents/orchestrator.py tests/test_orchestrator_writer_cadence.py
git commit -m "feat(orchestrator): call _maybe_write in step() (before close_stale; both branches)"
```

---

### Task 3: Version bump + verification note

**Files:**
- Modify: `pyproject.toml` (version → `0.1.4`)
- Create: `docs/superpowers/specs/2026-06-03-writer-cadence-verification.md`

- [ ] **Step 1: Bump the version**

In `pyproject.toml`, set `version = "0.1.4"`.

- [ ] **Step 2: Run the full non-integration suite**

Run: `uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration -q`
Expected: PASS. Capture the count for the note.

- [ ] **Step 3: Write the verification note**

Create `docs/superpowers/specs/2026-06-03-writer-cadence-verification.md` documenting: the test count from Step 2; that `_maybe_write` is unit-tested for the four behaviors (writes-when-due, below-threshold skip, skip-existing, budget-pause) and wired into both `step()` branches (before `close_stale_campaigns`); and the remaining manual check NOT run here — a live smoke-lab daemon run (`efferents start --submission examples/smoke-lab/`, needs `ANTHROPIC_API_KEY`) confirming a `lab/paper/<campaign_id>.md` file appears once a campaign clears the gate. Note explicitly that this slice is compose-only: publishing to a hosted journal remains the hosted-surface slice.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml docs/superpowers/specs/2026-06-03-writer-cadence-verification.md
git commit -m "chore: bump to 0.1.4 — daemon composes papers via the orchestrator Writer cadence"
```

---

## Notes for the implementer

- **No API key needed for tests.** Build the Orchestrator with `dry_run=True` (so `anthropic.Anthropic()` is never called), then set `o.dry_run = False` and `o.client = object()`; the `writer.write_phase_a_paper` call is always monkeypatched in unit tests, so the fake client object is never dereferenced.
- **Seed `lab_id` from the active config.** Use `_lab.LAB_ID` (resolves via the conftest's `LabConfig`) when inserting the campaign, or `campaign_open_list` won't find it.
- **Cursor semantics:** bump `last_paper_runs`/`last_paper_ts` only after a completed scan; never on the `should_pause` early return.
- **Skip-existing path:** `lab/paper/<cid>.md` (singular `paper`), matching `writer_paths(paper=lab_root / "paper")`.
