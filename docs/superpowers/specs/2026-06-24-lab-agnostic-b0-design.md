# B0 — Finish lab-agnosticism (analyst, progress, writer)

**Date:** 2026-06-24
**Status:** approved design, pre-implementation

## Summary

Make the efferents framework genuinely domain-agnostic so diverse users can run
their own (non-QML) labs cleanly. This is the **precondition** (CLAUDE.md hard
constraint) for any Phase-B multi-lab/shared-journal work. The *paper bundle*
(`PaperFrontmatter` + `compose_paper`/`write_phase_a_paper`), the Coder, the
prompts, `recent_runs` (`SELECT *`), and `LabConfig` are already agnostic. Three
things are not:

1. **`analyst.py` (digests) — LIVE.** Hardcodes QML metric/param columns
   (`e_w1`, `val_x0_mse`, `radial_l2_log`, `active_frac_w1`, `raw_q`, `epochs`,
   `aug_depth`, `aug_shared_unitary`, `cond_drop_p`) in `_format_campaign_blocks`
   / `_format_recent_runs`, and the flat-digest counter is W1-min-only.
2. **`progress.py` (static `lab/progress.html`) — LIVE** (refreshed by
   `analyst.write_digest` → `write_progress`). Hardcodes QML columns in
   `_snapshot`, `_scored_sample_runs` (filters `e_w1`/`eval_kind=="sample"`),
   `_best_run_in` (sorts `e_w1`), and ~20 HTML render sites.
3. **`writer.py` legacy LaTeX/figure path — DEAD for the platform.**
   `write_once` + `regenerate_data_efficiency_figure` +
   `regenerate_aug_depth_figure` + `regenerate_recent_runs_table` +
   `regenerate_best_per_config_table` + `ALL_RUNS_SQL` + `_format_all_runs` are
   auto_qml-specific and only reachable via `write_once` (and the legacy
   `python -m efferents.agents write-once` / `start-writer` commands), NOT via
   the live `write_phase_a_paper`.

**B0 = centralize column/metric logic in one helper, generalize the two live
paths onto it, and delete the dead auto_qml path.** Approach 1 (shared helper)
with the display principle: headline + configured panels are the named/featured
metrics (headline+direction drives "best run" and the flat-digest counter); all
other non-meta columns are auto-discovered and shown generically.

## Goals

- A non-QML lab (e.g. the smoke lab, headline `synthetic_loss`/min) produces
  correct digests and a correct `progress.html` with no QML column references.
- A `direction: max` lab (e.g. accuracy) gets correct "best run" and
  improvement/plateau detection.
- No `auto_qml`/QML column names remain in `analyst.py`, `progress.py`, or
  `writer.py`.
- Full test suite green, with QML-encoding tests rewritten to the generic /
  config-driven behavior.

## Non-goals

- No sharing / multi-lab / hosted journal (that's B1+). This is the precondition.
- No change to the paper bundle, Coder, prompts, `recent_runs`, or `LabConfig`.
- No new dashboard work; `progress.py` stays a static-HTML renderer (just
  config-driven). The `efferents serve` dashboard is untouched.
- Not dropping the `matplotlib` dependency even if writer figure deletion frees
  it (out of scope; revisit later).

## §1 — Shared helper: `efferents/metrics_view.py` (new)

The single source of truth for "what a run's columns mean," consumed by
`analyst.py` and `progress.py`. Depends only on `LabConfig` (`from efferents import
lab`) and the runs schema.

```python
META_COLUMNS = ("run_id", "started_at", "ended_at", "config_path",
                "campaign_id", "researcher_mode", "student_id",
                "git_commit", "duration_seconds")

def discover_columns(db_path, *, meta=META_COLUMNS) -> list[str]:
    """Non-meta columns present in the runs table (a lab's params + metrics).
    Relocated from progress._discover_metric_columns; same behavior."""

def finite(x) -> float | None:
    """Return x as a float iff it is a finite real number, else None.
    (bool excluded; non-numeric/NaN/inf -> None.)"""

def headline():            # -> Headline(column, direction) from get_config()
def panels():              # -> tuple[Panel(column,label,target), ...] from get_config()

def best_run(rows: list[dict]) -> dict | None:
    """Best row by the headline column + direction (min/max), skipping rows
    whose headline value isn't finite. None if no scored rows."""

def headline_value(row: dict) -> float | None:   # finite(row.get(headline().column))

def improved(prev: float | None, current: float | None, *,
             direction: str, epsilon: float) -> bool:
    """True iff `current` improves on `prev` by more than epsilon in the given
    direction ('min' -> decrease, 'max' -> increase). prev None -> True if
    current is not None (first measurement counts as improvement)."""
```

- `progress._META_COLUMNS` and `progress._discover_metric_columns` are removed;
  `progress.py` and `researcher.py` import from `metrics_view`
  (`from efferents.metrics_view import discover_columns` etc.). A back-compat
  re-export in `progress.py` (`_discover_metric_columns = discover_columns`) is
  optional — prefer updating the one `researcher.py` import directly.
- `finite` matches the dashboard `reader._finite` semantics (the dashboard may
  adopt this helper later; not required here).

## §2 — Per-file changes

### `analyst.py`

- `_format_campaign_blocks(groups, db_path)`: drop hardcoded `metric_keys`/`cols`.
  Featured metric = `metrics_view.headline()`; best per campaign =
  `metrics_view.best_run(rows)`; the per-run detail uses headline + panel
  columns + `discover_columns` generically.
- `_format_recent_runs(rows)`: drop hardcoded lists. Columns = meta subset
  (short `run_id`, `started_at`, `campaign_id`, `researcher_mode`) + headline +
  panel columns + remaining discovered columns, rendered generically (value or
  `—` when absent/non-finite).
- `write_digest`: replace `best_w1 = …` + `update_flat_digest_counter(...,
  current_best_w1=best_w1, epsilon=0.005)` with the headline value of
  `metrics_view.best_run(rows)` and `update_flat_digest_counter(state,
  current_best_headline=<value>)` (epsilon defaults from config — drop the
  literal `0.005`).
- `update_flat_digest_counter(state, *, current_best_headline, epsilon=None)`:
  rename param from `current_best_w1`; make direction-aware via
  `metrics_view.improved(prev, current_best_headline,
  direction=cfg.metrics.headline.direction, epsilon=epsilon)`. State key
  `last_digest_best_w1` → `last_digest_best_headline`, reading the old key as a
  fallback so existing `state.json` files don't reset the counter. Keep
  `digests_without_improvement`.

### `progress.py`

- Remove `_META_COLUMNS`/`_discover_metric_columns` (now in `metrics_view`);
  import from there.
- `_snapshot`: replace the hardcoded `wanted` column list with meta + headline +
  panel columns + `discover_columns(db_path)`.
- `_scored_sample_runs`: a run is "scored" iff
  `metrics_view.headline_value(row) is not None`. Drop the QML
  `eval_kind == "sample"` filter entirely (`eval_kind` is a lab-defined column,
  not a framework concept).
- `_best_run_in`: delegate to `metrics_view.best_run`.
- HTML render functions (`_render_card`, `_render_run_tile`,
  `_render_architectures`, etc.): replace all QML column references with the
  headline metric, the configured panels, and a generic key/value rendering of
  the remaining discovered columns. `_render_architectures` (QML "architecture"
  = `raw_q`/`aug_depth`) becomes a generic "run config" tile built from the
  discovered non-metric columns, or is dropped if it has no generic meaning.
- `_panel_metrics` already reads `LabConfig`; leave it.

### `writer.py` (+ `__main__.py`) — delete the dead auto_qml path

- Delete: `write_once`, `regenerate_data_efficiency_figure`,
  `regenerate_aug_depth_figure`, `regenerate_recent_runs_table`,
  `regenerate_best_per_config_table`, `ALL_RUNS_SQL`, `_format_all_runs`, and any
  helper used only by these (e.g. QML figure utilities). Remove `WriterPaths`
  fields used only by the deleted figure/table path (`paper_figures`,
  `paper_tables`) if nothing else references them; keep fields used by
  `write_phase_a_paper`/`compose_paper`/peer-review.
- `__main__.py`: remove `cmd_write_once` + the `write-once` subparser; remove or
  repoint `cmd_start_writer`/`start-writer` (if it drives `write_once`, delete
  it — the live writer path is `efferents start` → orchestrator →
  `write_phase_a_paper`).
- Remove now-unused imports (e.g. `matplotlib` in `writer.py` if only the deleted
  figures used it).
- Keep intact: `compose_paper`, `write_phase_a_paper`, `should_publish`,
  `writer_paths`, the peer-review board, and the journal append.

## Data flow (unchanged shape, now config-driven)

```
orchestrator → analyst.write_digest(rows)
                 ├─ metrics_view: headline/panels/discovered/best_run/improved
                 ├─ digest markdown (generic columns)
                 ├─ update_flat_digest_counter (direction-aware)
                 └─ write_progress → progress.html (generic columns)
orchestrator → writer.write_phase_a_paper  (already agnostic; unchanged)
```

## Error handling

- Missing headline/panel column in a given run row → rendered as `—`
  (`finite`/`.get` guards), never raised.
- Empty runs set → `best_run` returns None; digest/progress render empty-valid.
- Existing `state.json` with the old `last_digest_best_w1` key → read as fallback
  so the plateau counter is preserved across the rename.

## Testing

Pytest. The risk is the existing QML-encoding tests; they are rewritten to the
generic/config-driven behavior (most under the `smoke_lab_config` fixture with
headline `synthetic_loss`).

- **New `tests/test_metrics_view.py`:** `discover_columns` (non-meta only, missing
  db → []); `finite` (int/float/bool/NaN/inf/str); `best_run` min and max
  directions + non-finite skipped + empty → None; `improved` direction-aware +
  epsilon boundary + None-prev.
- **Update** `test_analyst_grouping.py`, `test_analyst_epsilon.py`,
  `test_flat_digest_counter.py`: use `current_best_headline`; assert direction-
  aware behavior; assert digest output references the configured headline/panels,
  not QML columns. Keep a `direction: max` case.
- **Update** `test_progress.py`, `test_progress_panels.py`,
  `test_progress_autodiscovery.py`: assert `progress.html` renders the configured
  panels + discovered columns and contains no `e_w1`/`raw_q`/etc. for a smoke lab;
  drop `eval_kind` assumptions.
- **Update/trim** `test_writer_output.py`, `test_writer_metric_resolution.py`:
  remove tests of the deleted `write_once`/`regenerate_*`/`ALL_RUNS_SQL`; keep and
  retain green the `write_phase_a_paper`/`should_publish`/`compose_paper` tests.
- **conftest.py:** the pre-migration `fresh_runs_db` (QML columns) stays for
  migration tests; analyst/progress tests run under `smoke_lab_config`
  (`synthetic_loss`). Add a `direction: max` config variant if a test needs it.
- **Acceptance:** full suite green; and a manual check that
  `python -m efferents.agents digest-now` / a smoke-lab digest produces a clean
  `progress.html` with synthetic_loss panels and no QML columns.

## Out of scope / future

- Dropping `matplotlib` from dependencies once no framework code renders charts.
- The dashboard `reader.py` adopting `metrics_view.finite`/`best_run` (DRY win,
  not required for B0).
- B1+ (shared journal) — unblocked by this work.
