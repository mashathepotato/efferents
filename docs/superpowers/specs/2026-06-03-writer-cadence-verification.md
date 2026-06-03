# Writer cadence (v0.1.4) verification

**Date:** 2026-06-03
**Branch:** `feat/writer-cadence`
**Spec:** [`2026-06-03-writer-cadence-design.md`](./2026-06-03-writer-cadence-design.md)
**Plan:** [`../plans/2026-06-03-writer-cadence.md`](../plans/2026-06-03-writer-cadence.md)

## What shipped

`Orchestrator._maybe_write()` makes the running daemon compose papers on its
own. It is throttled by a `last_paper_runs`/`last_paper_ts` cursor
(`runs_per_paper=20`, `hours_per_paper=6.0`), scans open campaigns via
`campaign_open_list`, skips any campaign that already has `lab/paper/<id>.md`,
and calls `writer.write_phase_a_paper` — whose `should_publish` gate runs before
any LLM call. It is wired into both `step()` branches after `_maybe_code()`, and
in the no-proposal branch before `close_stale_campaigns` so an aging campaign can
still publish before being force-closed.

| Commit | What |
|---|---|
| (task 1) | `_maybe_write` + `runs_per_paper`/`hours_per_paper` config + imports |
| (task 2) | wired `_maybe_write` into both `step()` branches |
| (this)   | version → 0.1.4 + this note |

## Verified here (automated)

```
$ uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration -q
197 passed, 3 skipped in 2.77s
```

`_maybe_write` is unit-tested for four behaviors: writes-when-due (cursor
advances), below-threshold skip, skip-campaign-with-existing-paper, and
budget-pause short-circuit (cursor not bumped). Two wiring tests confirm `step()`
calls `_maybe_write` in both branches and, in the no-proposal branch, before
`close_stale_campaigns`.

## NOT verified here (run before announcing)

The live smoke-lab daemon run was not executed in this session. Before claiming
v0.1.4 deployable, run `efferents start --submission examples/smoke-lab/`
(needs `ANTHROPIC_API_KEY`) long enough for a campaign to clear the gate, and
confirm a `lab/paper/<campaign_id>.md` file appears.

## Scope note

This slice is **compose-only**: the daemon now writes papers locally under
`lab/paper/`. Publishing them to a hosted journal remains the hosted submission
surface slice (`2026-06-03-hosted-submission-surface-design.md`), which this
unblocks.
