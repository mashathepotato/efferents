# Writer cadence in the orchestrator (v0.1.4) design

**Status:** design, ready for plan.
**Date:** 2026-06-03
**Closes:** the blocking finding in [`2026-06-03-eval-decouple-verification.md`](./2026-06-03-eval-decouple-verification.md) — the daemon never runs the Writer, so a deployed lab emits no papers.
**Builds on:** [`2026-06-03-agent-proposed-evals-design.md`](./2026-06-03-agent-proposed-evals-design.md) (v0.1.3 — campaigns carry the headline metric the Writer reads).
**Unblocks:** [`2026-06-03-hosted-submission-surface-design.md`](./2026-06-03-hosted-submission-surface-design.md) — there is nothing to publish until the daemon composes papers.

## Motivation

`efferents start` runs the orchestrator loop (researcher → coder → executor →
analyst digest). Paper composition (`writer.write_phase_a_paper` / `write_once`)
is only invoked by the separate `python -m efferents.agents write-once` command,
never by the orchestrator's `step()`. So a deployed lab **never emits a paper on
its own**, regardless of how good its results are — and the hosted submission
surface assumed the daemon publishes papers.

This slice adds a Writer cadence to the orchestrator: a `_maybe_write` step,
alongside `_maybe_digest` and `_maybe_code`, that periodically attempts to
compose a paper for each open campaign whose results clear the publish gate.

## Approach (chosen during brainstorm)

**Periodic cadence over open campaigns.** `_maybe_write` is throttled by a
run-count / time cursor (like `_maybe_digest`). When due, it scans open
campaigns and calls `write_phase_a_paper` on each that lacks a paper file. The
Writer's `should_publish` gate is the real arbiter — it runs *before* the LLM
compose call and returns `None` when there's no significant gain, so attempting
a not-yet-publishable campaign costs ~nothing. The throttle bounds how often the
scan runs; the gate decides what actually gets written.

Rejected alternatives: *on-campaign-close* (a strong but long-open campaign
waits until it goes stale to publish), and *threshold-triggered with no time
throttle* (re-attempts every step once over the run threshold, wasting cheap-gate
cycles but adding loop churn).

## 1. `_maybe_write` — the cadence step

A new method on `Orchestrator`, modeled on `_maybe_digest`/`_maybe_code`:

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
        return   # do NOT bump the cursor; retry when budget frees

    lab_root = self.paths.runs_db.parent      # the lab dir backing self.paths.*
    wpaths = writer_paths(
        lab=lab_root,                         # → runs_db/notebook/state/budget under lab_root
        paper=lab_root / "paper",             # paper.md lands at lab/paper/<cid>.md
        reports=lab_root / "reports",
        context=self.context_dir,
    )
    for campaign in campaign_open_list(self.paths.runs_db, _lab.LAB_ID):
        cid = campaign["id"]
        if (wpaths.paper / f"{cid}.md").exists():
            continue   # one paper per campaign; no re-write / re-review
        try:
            artifact = write_phase_a_paper(
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

**New constructor params:** `runs_per_paper: int = 20`, `hours_per_paper: float = 6.0`
(papers are rarer than digests/coder runs). Stored as `self.runs_per_paper` /
`self.hours_per_paper`.

**Notes:**
- The campaign dicts from `campaign_open_list` carry `headline_metric` /
  `headline_direction` (v0.1.3), which is exactly how the agent-proposed metric
  reaches the Writer's gate + provenance.
- `write_phase_a_paper` writes `<paper>/<cid>.md` *before* peer review (if
  enabled). A peer-review **reject** still leaves the file on disk → the
  skip-existing guard prevents re-attempting a rejected campaign. A peer-review
  **accept** closes the campaign as `published`. The no-peer-review path writes
  the file and leaves the campaign open (harmlessly skipped on later scans).
- `lab_root = self.paths.runs_db.parent` is used so the derived `WriterPaths`
  (`runs_db`, `notebook`, `state`, `budget`) point at the *same* files the
  orchestrator already uses — no second copy of lab state. The plan confirms
  this against `writer_paths()` + `WriterPaths` (verified: `writer_paths(lab=L)`
  sets `runs_db = L/"runs.sqlite"`, matching `self.paths.runs_db`).

## 2. Wiring into `step()`

Call `self._maybe_write()` in both `step()` branches, immediately after
`self._maybe_code()`:

- **No-proposal branch:** place it **before** `close_stale_campaigns(...)`, so a
  strong-but-aging campaign gets its paper attempt before being force-closed as
  stale.
- **Ran branch:** after `self._maybe_code()` (no `close_stale_campaigns` there).

No other `step()` logic changes.

## 3. Error handling

- Each campaign's `write_phase_a_paper` call is wrapped in try/except; one
  campaign's failure is logged to the notebook and does not abort the scan or
  the orchestrator loop.
- Budget exhaustion: `should_pause()` short-circuits before any compose, and the
  cursor is left un-bumped so the next eligible tick retries once budget frees.
- The cursor is bumped only after a completed scan, so a normal (no-publish)
  scan still advances the throttle and the loop doesn't re-scan every step.

## 4. Testing

Unit tests monkeypatch the imported `write_phase_a_paper` with a fake recorder
and drive `_maybe_write` directly (a non-None fake client, `dry_run=False`,
seeding `runs` + an open campaign + `state.json` cursors):

- **Below threshold:** cursor recent → writer **not** called.
- **Above threshold, fresh campaign:** open campaign, no `<paper>/<cid>.md` →
  writer called once for that campaign; `last_paper_runs`/`last_paper_ts`
  persisted.
- **Skip-existing:** `<paper>/<cid>.md` already on disk → writer **not** called
  for it.
- **Budget pause:** `budget.should_pause()` true → writer not called and the
  cursor is **not** bumped.

No new integration test: the opt-in smoke e2e already drives the daemon, and
this step is fully unit-coverable by faking the Writer call.

## 5. Scope

**In scope:** one paper attempt per open campaign per cadence tick; one paper per
campaign (skip-existing); lab-wide campaign scan; throttle + budget guard;
wiring into `step()`.

**Out of scope:**
- Per-student paper cadence (lab-wide scan is enough for one lab).
- Paper *revision* / re-write when a campaign accrues more runs (the journal's
  revision flow, Phase B).
- **Publishing** the composed paper to a hosted journal — that is the hosted
  submission surface slice; this slice only makes the daemon *compose* papers
  locally under `<paper>/`.

## Decisions locked during the brainstorm (2026-06-03)

1. **Periodic cadence over open campaigns** (Approach A), throttled by
   `runs_per_paper`/`hours_per_paper`, with the existing `should_publish` gate as
   the publish arbiter.
2. **One paper per campaign** — skip campaigns that already have a paper file.
3. **Attempt before `close_stale_campaigns`** so aging campaigns can still
   publish.
4. **Lab-wide scan**, not per-student.
5. Compose-only — publishing to the hosted journal stays in the hosted-surface
   slice.
