# Research-loop e2e (v0.1.1) design

**Status:** design, ready for plan.
**Date:** 2026-05-29
**Closes:** the 3 follow-ups documented in [`2026-05-28-deployment-verification.md`](./2026-05-28-deployment-verification.md) §5.
**Builds on:** [`2026-05-26-efferents-deployment-design.md`](./2026-05-26-efferents-deployment-design.md).

## Motivation

v0.1 shipped the entry-flow plugin: a user agent can read `skills/intake.md`, install efferents, validate a submission, and start a daemon. The daemon currently starts cleanly but crashes inside the orchestrator loop because three legacy assumptions about Phase A (the auto-qml-coupled scaffold) were not unwound:

1. **Phase A's `Orchestrator` expects a `context/` directory** (with optional `research_log.md`) next to the lab dir. The smoke lab doesn't ship one.
2. **The `runs` table schema is implicit** — Phase A's `migrations.runner` only ADDs columns; the table itself was created by `auto_qml.run.py`. Without that, `runs` doesn't exist, and Task 17's `_persist_run_result` writes silently fail (caught by `except OperationalError` and dropped).
3. **`orchestrator.step()` still dispatches via `executor.execute(...)`** which calls `auto_qml.run_from_config` — now lazy-erroring (per Task-0 prep), so the first real run raises.

v0.1.1 closes all three so the smoke lab actually runs a research cycle end-to-end. The fix is domain-agnostic: no new code paths reference QML.

## Scope

Three connected changes, one cohesive ship:

- Move `_execute_run` and `_persist_run_result` from `orchestrator.py` to `efferents/exec.py` (their natural home alongside `_run_and_capture`). Add lazy ALTER-on-`OperationalError` to `_persist_run_result`.
- Add `ensure_runs_table(db_path, cfg)` to `efferents/migrations/runner.py`. Wire it into `_init_lab_root`. Also create an empty `context/research_log.md` stub if absent.
- Rewrite `efferents/agents/executor.py` so `execute(*, paths, proposal, base_config=None)` preserves its signature but routes through `_execute_run` + `_persist_run_result` instead of `auto_qml.run_from_config`. Notebook formatting becomes generic (columns from `result.metrics.keys()`); the QML-specific column list and amp-ratio heuristics are dropped.

Out of scope:
- Per-column metric typing (everything is REAL in v1; Phase B can extend).
- Cleanup contract for `lab/configs/run_*.yaml` files (cheap, no cleanup).
- Prompt templating — Researcher/Coder prompts remain QML-flavored. Documented limitation already in `intake.md`.
- Auto-qml's `run.py` stdout-JSON migration (lives in auto-qml's repo).

---

## 1. What changes where

```
efferents/exec.py
  + move _execute_run, _persist_run_result here (currently in orchestrator.py).
  + on sqlite3.OperationalError during INSERT, attempt ALTER TABLE runs ADD
    COLUMN <name> REAL for the missing column, then retry the insert once.
    Belt-and-suspenders for metrics the run command emits that weren't
    declared in lab.yaml.

efferents/migrations/runner.py
  + new function ensure_runs_table(db_path, cfg). Creates the runs table
    with base meta columns (run_id PK, started_at, ended_at, config_path,
    campaign_id, researcher_mode, student_id DEFAULT 'primary', git_commit,
    duration_seconds) plus a REAL column for every LabConfig metric column
    (headline.column + each panel.column). Idempotent — uses PRAGMA
    table_info to skip existing columns. apply_campaigns_migration stays
    as-is (it operates on the campaigns table).

efferents/cli.py (_init_lab_root)
  + call ensure_runs_table(lab_root/state.db, cfg) after apply_campaigns_migration.
  + ensure <submission>/context/ exists; write an empty research_log.md stub
    if neither exists (Researcher reads it for fuzzy steering; empty = pure
    hypothesis-driven).

efferents/agents/executor.py
  REWRITE: same call signature execute(*, paths, proposal, base_config=None),
  same return shape {ok, name, rows, duration_seconds} OR {ok, name, error,
  traceback, duration_seconds}. New internals — see Section 2.
  Drops the QML-specific _format_outcome column list and the amp-ratio
  WALLPAPER/DIM heuristics entirely.

efferents/agents/orchestrator.py
  No change to .step() or .run() — executor.execute() preserves its signature.
  Remove the orphaned _execute_run/_persist_run_result definitions added in
  Task 17 (they moved to efferents/exec.py).

efferents/lab.py
  + validate that every metric column name (headline.column and each
    panel.column) matches ^[A-Za-z_][A-Za-z0-9_]*$ at LabConfig.from_submission
    time. SubmissionError otherwise. Prevents SQL injection via lab.yaml
    when ensure_runs_table ALTERs the schema.

tests/
  + tests/test_ensure_runs_table.py — schema created with expected columns;
    idempotent on second call; adds missing metric columns to an existing
    table; leaves existing columns untouched.
  ~ tests/test_exec_persist.py (renamed from test_orchestrator_run_persistence.py)
    Same assertions, imports moved to efferents.exec.
    + new test: OperationalError on missing column triggers ALTER + retry.
  + tests/test_executor_rewrite.py — execute() against a tmpdir source.dir
    with a stub run_command echoing stdout-JSON; happy path, non-zero exit,
    no-JSON, notebook formatter with missing metrics.
  ~ tests/conftest.py — smoke_lab_config fixture also creates lab/state.db
    and calls ensure_runs_table(db, cfg) so persistence tests have schema.

Files removed: none.
New files: 2 test files.
Heavy rewrites: executor.py.
```

---

## 2. Execution flow + run_id lifecycle

```
executor.execute(*, paths, proposal, base_config=None):

1. cfg       = lab.get_config()
2. name      = proposal["name"]
   overrides = dict(proposal["config_overrides"] or {})
   if proposal["campaign_id"]:  overrides["run.campaign_id"]    = proposal["campaign_id"]
   if proposal["mode"]:         overrides["run.researcher_mode"] = proposal["mode"]
   if proposal["student_id"]:   overrides["run.student_id"]     = proposal["student_id"]

3. base_yaml = yaml.safe_load(cfg.executor.config_template.read_text())
   rendered  = apply_overrides(base_yaml, overrides)
   rendered.setdefault("run", {})["name"] = name

4. run_id      = uuid.uuid4().hex
   config_dir  = paths.root / "configs"
   config_dir.mkdir(exist_ok=True)
   config_path = config_dir / f"run_{run_id}.yaml"
   yaml.safe_dump(rendered, config_path.open("w"))

5. started = now_iso()
   t0      = time.monotonic()
   result  = _execute_run(config_path)             # exec.py — uses cfg.executor.run_command
                                                    # with cwd=cfg.source.dir, env_passthrough
   duration = time.monotonic() - t0

6. _persist_run_result(result, run_id, config_path)  # exec.py — ALTER-on-OperationalError retry

7. notebook_append(paths.notebook, _format_outcome(
       name, hypothesis, expected, overrides, result, duration, started))

8. if result.ok:
       row = {"run_id": run_id, "name": name, **(result.metrics or {})}
       if result.git_commit:  row["git_commit"]   = result.git_commit
       return {"ok": True, "name": name, "rows": [row], "duration_seconds": duration}
   else:
       err_tail = (result.stderr or "")[-200:]
       return {"ok": False, "name": name,
               "error": result.error or err_tail or "run failed",
               "traceback": "", "duration_seconds": duration}
```

### Run-ID authority

The orchestrator-side `run_id` is authoritative. If `result.metrics["run_id"]` or top-level `result.metrics.run_id` exists (the run_command's stub might emit one), it is ignored at persistence time — `_persist_run_result(result, run_id, config_path)` uses the passed-in `run_id`. Reason: the orchestrator needs a stable ID for downstream analyst/coder reference *before* the subprocess starts; generating it on our side is the only way.

### Config file path lifecycle

Rendered configs land under `<lab_root>/configs/run_<uuid>.yaml` and are not deleted — they're the auditable trace of what was actually run. Storage is cheap (KB-scale YAML). No cleanup contract in v1.

### Notebook entry format (generic)

```
## <iso-ts> — <name>

**Hypothesis**: <text>
**Expected**: <text>
**Overrides**: `{...}`
**Duration**: <s>

| metric1 | metric2 | ... |
|---|---|---|
| <v1>    | <v2>    | ... |
```

Columns are `result.metrics.keys()` in insertion order. If `metrics is None` (failure case), the table is replaced by:

```
**Error**: <error>

```
<last 1KB of stderr>
```
```

### Compatibility with the orchestrator's downstream

`orchestrator.step()` consumes `outcome.get("rows", [])` as a list of metric dicts (it iterates over them, counts runs, feeds the analyst). The new executor returns a single-element `rows` list — orchestrator's downstream loop is happy with that, no orchestrator change needed.

---

## 3. Migration + tests

### `ensure_runs_table(db_path, cfg)`

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

def ensure_runs_table(db_path, cfg):
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

Column-name sanitization: a small follow-up edit in `LabConfig.from_submission` ensures metric column names match `^[A-Za-z_][A-Za-z0-9_]*$` at load time (SubmissionError if not). Prevents SQL injection via lab.yaml.

REAL is the universal numeric type for v1. Per-column typing (REAL/INTEGER/TEXT) is Phase B.

### Context dir bootstrap (`_init_lab_root`)

```python
context = submission_dir / "context"
context.mkdir(exist_ok=True)
research_log = context / "research_log.md"
if not research_log.exists():
    research_log.write_text(
        f"# {cfg.lab_id} research log\n\n"
        "*(empty — populate to guide the Researcher; "
        "the lab will operate from the hypothesis if left blank)*\n"
    )
```

### Tests

| File | Cases |
|---|---|
| `tests/test_ensure_runs_table.py` (new) | empty DB → table with expected columns; idempotent; new metric column added to existing table; existing columns untouched |
| `tests/test_exec_persist.py` (renamed from `test_orchestrator_run_persistence.py`) | existing 2 cases preserved with imports moved to `efferents.exec`; **new**: OperationalError on missing column triggers ALTER ADD COLUMN + retry, row lands |
| `tests/test_executor_rewrite.py` (new) | happy path against tmpdir source.dir with shell-echo stub emitting stdout-JSON; non-zero exit → ok=False, no row inserted; no-JSON → ok=False; notebook formatter handles None metrics |
| `tests/conftest.py` (updated) | `smoke_lab_config` autouse fixture also creates `lab/state.db` and calls `ensure_runs_table(db, cfg)` so persistence-touching tests have a valid schema |

### Verification (post-impl)

```bash
.venv/bin/efferents start --submission examples/smoke-lab/   # foreground
# Watch lab/daemon.log; expect:
#   - Orchestrator starts cleanly (no context/ crash)
#   - First step() runs executor.execute → run_command spawns stub_run.py
#   - stdout-JSON parsed, runs row written with synthetic_loss value
#   - Analyst digest fires after enough runs; progress.html updated
sqlite3 examples/smoke-lab/lab/state.db "SELECT COUNT(*), MIN(synthetic_loss) FROM runs"
```

`tests/integration/test_smoke_lab_e2e.py` (already exists, currently failing) becomes the green oracle.

### Out of scope for v0.1.1

- Per-column typing in `ensure_runs_table` (everything is REAL).
- Cleanup contract for `lab/configs/run_*.yaml`.
- Prompt templating (Researcher/Coder still QML-flavored — documented limitation).
- Auto-qml's own `run.py` migration to stdout-JSON contract.
- An `efferents prune` CLI.
