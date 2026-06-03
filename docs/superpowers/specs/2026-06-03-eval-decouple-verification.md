# Agent-proposed evals (v0.1.3) verification

**Date:** 2026-06-03
**Branch:** `feat/agent-proposed-evals`
**Plan:** [`docs/superpowers/plans/2026-06-03-agent-proposed-evals.md`](../plans/2026-06-03-agent-proposed-evals.md)
**Spec:** [`docs/superpowers/specs/2026-06-03-agent-proposed-evals-design.md`](./2026-06-03-agent-proposed-evals-design.md)

## What shipped

The Writer, bundle exporter, dashboard, and saturation report are no longer
hardwired to the QML metric `e_w1`. A campaign carries an agent-proposed
`headline_metric` + `headline_direction`; every consumer resolves the metric
from the campaign row and falls back to `LabConfig.metrics.headline` (then to
`("e_w1","min")` when no config is loaded, for unit tests).

| Task | Commit | What |
|---|---|---|
| 1 | `e7f02c0` | `campaigns.headline_metric` + `headline_direction` columns (idempotent migration) |
| 2 | `5945d09` | `campaign_insert` persists the metric (dynamic-column INSERT) |
| 3 | `ebf3dd6` + `4e18093` | `_best_metric`/`_resolve_campaign_metric`; Writer gates + provenance on the campaign metric; **direction-aware `should_publish`** (review fix) |
| 4 | `6b9533e` | `export_paper_bundle` provenance reads the campaign metric; `_campaign_runs` generalized to `SELECT *` |
| 5 | `74dd069` + `2362e79` | Researcher proposes + validates the metric; **prompt example lists the fields** (review fix); non-string hardening; invalid-proposal logging |
| 6 | `562ce9f` | Dashboard auto-discovers observed metric columns |
| 7 | `5021f16` | Saturation report operates over observed metric columns |
| 8 | `336df73` | e2e asserts the daemon persists the proposed metric (see deviations) |
| 9 | (this commit) | version → 0.1.3 + this note |

## Verified here (automated)

```
$ uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration -q
189 passed, 3 skipped
```

- New unit tests cover: the migration (idempotent); `campaign_insert` with/without
  the metric; `_best_metric` (min/max/absent); `_resolve_campaign_metric`
  (prefer/fallback/invalid-direction); direction-aware `should_publish`
  (max accepts an improvement); the exporter provenance for a custom metric;
  the proposal validator (valid/invalid-name/bad-direction/missing/non-string);
  the prompt example lists the metric fields; dashboard auto-discovery; and
  saturation observed-column discovery.
- The domain-agnostic prompt coupling guard (`tests/test_prompts_domain_agnostic.py`)
  passes — no QML tokens regressed into the prompts.
- Every task passed a spec-compliance review; the integration-heavy tasks (3, 5)
  passed a code-quality review that caught and fixed two real bugs: a
  direction-blind publish gate (max metrics would have been silently rejected)
  and a prompt example that omitted the new fields (the feature would have been a
  silent no-op).

## Plan deviations (intentional, with rationale)

1. **No test relocation (Task 8).** The plan assumed `e_w1`-asserting Writer/
   exporter tests would fail and move to `tests/lab_reference/`. They did not
   fail: the conftest's default `LabConfig` headline is `synthetic_loss`, and
   those tests use `e_w1` as *sample data* (manually-built provenance dicts,
   sample schema columns), not as a framework expectation. The full suite is
   green. Relocating passing tests would have deleted real coverage, so the
   relocation was skipped.

2. **Acceptance assertion changed (Task 8).** The plan's "the daemon composes a
   paper" assertion is **unreachable through `efferents start`** — see the
   blocking finding below. It was replaced with a robust check that any
   Researcher-proposed campaign metric persisted to the DB equals
   `synthetic_loss`.

## NOT verified here (requires a live key — run before announcing)

The live smoke-lab daemon run (`efferents start --submission examples/smoke-lab/`,
~2 min, needs `ANTHROPIC_API_KEY`, costs ~$0.10) was **not executed in this
session.** Before claiming v0.1.3 is deployable, run it and confirm:
- a `campaigns` row has `headline_metric=synthetic_loss`
  (`sqlite3 examples/smoke-lab/lab/runs.sqlite "SELECT id, headline_metric, headline_direction FROM campaigns"`);
- the dashboard renders a `synthetic_loss` panel.
The opt-in integration test `tests/integration/test_smoke_lab_e2e.py -m integration`
encodes the daemon-reachable portion of this.

## Blocking finding for the next slice (the hosted submission surface)

**The daemon does not run the Writer.** `efferents start` runs the orchestrator
loop (researcher → coder → executor → analyst digest); paper composition
(`writer.write_phase_a_paper` / `write_once`) is only invoked by the separate
`python -m efferents.agents write-once` command, never by the orchestrator's
`step()`. Consequences:

- A deployed lab started via `efferents start` **never emits a paper on its own**,
  regardless of this slice's metric decoupling.
- The hosted submission surface (the next slice) assumed the daemon publishes
  papers — but there is nothing to publish until the Writer is wired into the
  daemon cadence.

**Recommended next slice (before the hosted surface):** add a Writer cadence to
the orchestrator (a `_maybe_write` step, alongside `_maybe_digest` / `_maybe_code`,
that attempts `write_phase_a_paper` for campaigns with enough runs to gate). This
is a small, well-bounded addition but it has its own design questions (when to
attempt, how often, interaction with campaign close) and is out of scope for the
eval-decouple slice.
