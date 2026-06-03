# Agent-proposed domain-specific evals (v0.1.3) design

**Status:** design, ready for plan.
**Date:** 2026-06-03
**Closes:** the Writer/exporter half of CLAUDE.md items 5/6 (metric coupling) for non-QML labs.
**Blocks:** [`2026-06-03-hosted-submission-surface-design.md`](./2026-06-03-hosted-submission-surface-design.md) — the hosted surface's publish path has nothing to publish until a non-QML lab can emit a paper.
**Builds on:** [`2026-06-02-prompt-templating-design.md`](./2026-06-02-prompt-templating-design.md) (v0.1.2, templated prompts).

## Motivation

v0.1.2 templated the agent *prompts*, but the **Writer and the bundle exporter
are still hardwired to the QML headline metric `e_w1`**. For any non-QML lab
(the smoke lab measures `synthetic_loss`):

- `writer.py:write_phase_a_paper` reads `r["e_w1"]` via `_best_e_w1()`, sets
  `primary_metric_name="e_w1"` and `metric_provenance[].name="e_w1"`. With no
  `e_w1` column, `_best_e_w1()` returns `None` → the function returns `None` and
  **never composes a paper**.
- `federation.py:export_paper_bundle` builds `metric_provenance` and
  `primary_metric` from hardcoded `e_w1`/`raw_q`.

So a non-QML lab cannot emit a paper at all — which blocks the hosted submission
surface (nothing to publish) and the smoke-lab E2E acceptance test.

The fix is not "read one fixed metric column from `lab.yaml`." It is that the
**eval should be domain-specific to the hypothesis** — the Researcher *proposes*
the headline metric that would corroborate or refute the hypothesis, the way the
journal vision's `eval-design` PhD-student subagent is meant to. The metric is
stored on the campaign; every downstream consumer reads it (falling back to the
`LabConfig` default for back-compat).

## Key enabling fact: storage is already metric-agnostic

`exec.py:_persist_run_result` inserts each key of the run's stdout `metrics`
dict as a column, and `ALTER TABLE runs ADD COLUMN ...` on `OperationalError`
for any column that doesn't yet exist. So an agent-proposed metric is persisted
automatically on the first run that emits it — **no storage rewrite, no schema
migration for the metric itself.** The gaps are: campaigns don't carry a
proposed metric, and the Researcher/Writer/exporter/dashboard don't read one.

## Coupling inventory (to remove)

| location | coupling |
|---|---|
| `writer.py:write_phase_a_paper` | `_best_e_w1`, `primary_metric_name="e_w1"`, `metric_provenance[].name="e_w1"` |
| `federation.py:export_paper_bundle` | `metric_provenance` + `primary_metric` hardcode `e_w1`/`raw_q` |
| `researcher.py:PRIMARY_METRICS` + `_saturation_report` | QML 3-metric set; already guards/no-ops on non-QML schemas — generalize lightly |

---

## 1. Data model: campaign-level metric

Add two columns to `campaigns` via the existing idempotent ALTER list in
`migrations/runner.py:apply_campaigns_migration` (it already PRAGMAs then ALTERs
only-when-missing):

- `headline_metric TEXT` — the metric name the Researcher proposed for this
  campaign.
- `headline_direction TEXT` — `"min"` | `"max"`.

`state.campaign_insert(...)` gains optional `headline_metric` +
`headline_direction` params and writes them when present.

**Fallback:** when a campaign's `headline_metric` is null (existing QML
campaigns, or a Researcher that didn't propose one), consumers fall back to
`lab.get_config().metrics.headline.column` / `.direction`. This preserves
auto-qml behavior with zero data migration.

**Validation:** the proposed metric name must pass the existing SQL-identifier
sanitizer (the same one `LabConfig` uses for metric columns). An invalid name
rejects the proposal so the Researcher retries.

---

## 2. Researcher proposes the eval

The Researcher's per-campaign output gains `headline_metric` + `direction`
(plus a one-line rationale, logged not stored). The templated Researcher prompt
(`prompts/student.md` / `supervisor.md`, already `load_prompt`-rendered) gains an
instruction:

> Design the eval that would corroborate or refute this hypothesis: name the
> single headline metric and its direction (`min`/`max`), and ensure the run
> command emits it under the stdout `metrics` JSON object.

On campaign open, `campaign_insert` persists the proposed metric. The first run
of that campaign emits the metric in its stdout `metrics` dict; the executor's
existing ALTER-on-demand path creates the column. No new wiring in the executor.

**Back-compat:** if the Researcher omits the metric (older prompts, or an
override lab that keeps the QML prompt), `headline_metric` stays null and the
config default applies.

---

## 3. Writer reads the campaign metric

In `writer.py:write_phase_a_paper`:

- Replace `_best_e_w1(runs)` with `_best_metric(runs, metric, direction)` —
  `min(vals)` when direction is `min`, `max(vals)` when `max`; `None` when no
  run carries the column.
- Resolve `metric, direction` from `campaign["headline_metric"]` /
  `["headline_direction"]`, falling back to `lab.get_config().metrics.headline`.
- `GateInputs.primary_metric_name` and `metric_provenance[].name` use the
  resolved metric. `should_publish` is unchanged — `primary_metric_name` is
  already one of its parameters.
- The baseline-vs-candidate comparison respects `direction` (today's logic
  assumes lower-is-better; `max` flips it).

---

## 4. Exporter reads the campaign metric

In `federation.py:export_paper_bundle`:

- `metric_provenance` entries read `r.get(metric)` for the resolved metric
  (not `r.get("e_w1")` / `r.get("raw_q")`).
- `primary_metric = {"name": metric, "value": runs[0].get(metric),
  "run_id": runs[0]["run_id"]}`.
- `metric, direction` resolved from the campaign row (already loaded via
  `_campaign_row`), falling back to config.

The content-addressed tarball layout, `_sha256_of`, and manifest schema are
unchanged — only which column the provenance reads changes.

---

## 5. Dashboard auto-discovery (full B)

`progress._panel_metrics()` today returns only `LabConfig.metrics.panels`.
Generalize it to the **union of: config panels ∪ metric columns observed in
`runs`** — the latter discovered via `PRAGMA table_info(runs)` minus the known
meta columns (`run_id, started_at, campaign_id, researcher_mode, eval_kind,
seed, config_yaml`, and the other Phase-A meta columns). Headline selection
reads each open campaign's `headline_metric` / `headline_direction`, falling
back to config. A metric the lab never declared but the agent proposed still
appears on the dashboard.

---

## 6. Researcher saturation report (light generalization)

`researcher.py:_saturation_report` hardcodes a QML 3-metric `PRIMARY_METRICS`
set and buckets by `(model, raw_q, eval_kind)`. Generalize:

- Metrics → the metric columns observed in `runs` (same discovery as §5).
- Buckets → whatever low-cardinality config axes exist, rather than the fixed
  QML triple.
- Keep the existing graceful no-op when the schema lacks the needed columns.

This is a generalization, not a rewrite: non-QML labs get real (if simpler)
saturation signal instead of the current silent skip; QML keeps working.

---

## 7. Validation & failure contract

- Proposed metric name must pass the SQL-identifier sanitizer; reject otherwise
  (Researcher retries).
- If a campaign's `headline_metric` never appears in any run (the run command
  didn't emit it), `_best_metric` returns `None` → the existing "no candidate →
  return `None`, leave campaign open" path. **Logged to the notebook** so the
  miss is visible, not silent.
- Direction restricted to `{min, max}`; any other value falls back to config.

---

## 8. Testing & acceptance

**Unit:**
- `apply_campaigns_migration` adds `headline_metric` + `headline_direction`
  idempotently (run twice → no error, columns present once).
- `campaign_insert` with and without the metric params; reading back the row.
- `_best_metric` for `min` and `max` direction; `None` when the column is
  absent.
- Writer gates + builds `metric_provenance` on a non-`e_w1` metric, and via the
  fallback-to-config path.
- Exporter `metric_provenance` + `primary_metric` for a custom metric.
- Dashboard `_panel_metrics()` discovers an undeclared column present in `runs`.

**Acceptance (the gate that `e_w1`-coupling blocked) — extends
`tests/integration/test_smoke_lab_e2e.py`:**
- The Researcher proposes `synthetic_loss` / `min`, the run emits it, and the
  Writer **composes and accepts a paper** for the smoke lab. `@pytest.mark.integration`.

**Existing tests:** QML-coupled Writer/exporter tests that assert on `e_w1`
move to `tests/lab_reference/` (auto-qml's prompt+config override will re-cover
them when it migrates). Expect a handful of touch-ups.

**Manual verification:** run the smoke daemon foreground ~2 min; confirm a
campaign row carries `headline_metric=synthetic_loss`, a paper is composed under
`lab/papers/`, and the dashboard shows `synthetic_loss`. Document in a short
note and bump to v0.1.3.

---

## 9. Scope

**In scope:**
- One agent-proposed headline metric per campaign, with `LabConfig` fallback.
- Writer + exporter + dashboard + saturation report read the campaign metric.
- Dashboard auto-discovery of observed metric columns.

**Deferred:**
- Multi-objective gating (headline + weighted secondaries). Secondary metrics
  are stored (any emitted metric becomes a column) and shown on the dashboard,
  but the publish gate is single-metric. Multi-metric corroboration is a
  hosted-surface / cross-lab concern anyway.
- Auto-qml's own prompt/config override restoring the QML eval set (its repo).

---

## Decisions locked during the brainstorm (2026-06-03)

1. **Reading B — the agent proposes the eval** (not a static `lab.yaml` metric):
   the Researcher designs a domain-fitting headline metric per hypothesis.
2. **No storage rewrite** — `_persist_run_result`'s ALTER-on-demand already
   persists any emitted metric; the metric lives on the campaign row.
3. **Config fallback everywhere** — null campaign metric → `LabConfig.metrics.headline`,
   preserving auto-qml with zero migration.
4. **Full B** — includes dashboard auto-discovery and a light saturation-report
   generalization; multi-objective gating deferred.
5. **Sequencing:** this slice (v0.1.3) lands *before* the hosted submission
   surface, which depends on a non-QML lab being able to emit a paper.
