---
memo: 004_research_memo
agent: writer
reviewed_by: deterministic-provenance-audit
review_status: not_peer_reviewed
generated_at: 2026-07-21T22:02:07.390092+00:00
---

# Research memo: maximize the mean detection lead time of an early-warning alarm for a tipping transition, at a fixed ~5% series-level false-alarm rate, by tuning the rolling-window length of the lag-1 autocorrelation indicator


## Summary

Across 7 bounded experiments, the best setting was
mean_lead_time=97.5 at window=200 (`run_04`) — versus 18.5 at the weakest setting.
The objective (maximize `mean_lead_time`) is
addressed by the search above. The commands consumed
0.0007 wall-clock hours, charged as a conservative proxy
against the configured compute ceiling; $0.00 LLM spend.

## Hypothesis

maximize the mean detection lead time of an early-warning alarm for a tipping transition, at a fixed ~5% series-level false-alarm rate, by tuning the rolling-window length of the lag-1 autocorrelation indicator


## Experiment plan

Swept `window` over 7 configured values, running the repo's own `train`/`eval` commands.
Full plan: [`002_experiment_plan.md`](002_experiment_plan.md).

## Results

Best `mean_lead_time` = 97.5 at `window`
= 200. Full table: [`003_results.md`](003_results.md).

## Automated audit notes

- Every reported number resolves to a `run_id` and a logged train/eval pair.
- The configured execution ceiling held under the wall-clock proxy.
- This deterministic check is not scientific peer review and does not assess
  novelty, domain validity, leakage, or causal interpretation.

## Limitations

- The search covers only 7 configured setting(s) and one metric.
- No variance estimate is available unless the repository command itself
  performs and reports repeated seeds.
- Wall-clock duration is not GPU hardware telemetry or a monetary cost meter.
- Human domain review is required before acting on the result.

## Next experiment

Refine `window` around 200 and add predeclared repeated seeds for `mean_lead_time`.

## Evidence table

Every nontrivial claim below points to a run, a metric, or a source file.

| claim | evidence_type | source_path | run_id | metric |
|-------|---------------|-------------|--------|--------|
| Best mean_lead_time = 97.5 at window=200 | run_metric | `logs/iter_04.log` | `run_04` | mean_lead_time |
| mean_lead_time varied across the configured window sweep | metric_aggregate | `runs.jsonl` | `—` | mean_lead_time |
| Experiment plan recorded before execution | document | `journal/002_experiment_plan.md` | `—` | — |
| Execution stayed within the configured wall-clock compute proxy | budget | `journal/004_research_memo.md` | `—` | — |
