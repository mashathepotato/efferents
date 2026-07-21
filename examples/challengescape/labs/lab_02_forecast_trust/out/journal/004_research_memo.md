---
memo: 004_research_memo
agent: writer
reviewed_by: deterministic-provenance-audit
review_status: not_peer_reviewed
generated_at: 2026-07-21T22:02:08.666896+00:00
---

# Research memo: maximize trust-adjusted forecast skill — skill vs. climatology multiplied by the stability of the model's feature-importance ranking under bootstrap refits — by tuning the ridge penalty of a station-temperature forecaster


## Summary

Across 5 bounded experiments, the best setting was
trust_adjusted_skill=0.2386 at ridge_lambda=100 (`run_03`) — versus -0.0 at the weakest setting.
The objective (maximize `trust_adjusted_skill`) is
addressed by the search above. The commands consumed
0.0003 wall-clock hours, charged as a conservative proxy
against the configured compute ceiling; $0.00 LLM spend.

## Hypothesis

maximize trust-adjusted forecast skill — skill vs. climatology multiplied by the stability of the model's feature-importance ranking under bootstrap refits — by tuning the ridge penalty of a station-temperature forecaster


## Experiment plan

Swept `ridge_lambda` over 5 configured values, running the repo's own `train`/`eval` commands.
Full plan: [`002_experiment_plan.md`](002_experiment_plan.md).

## Results

Best `trust_adjusted_skill` = 0.2386 at `ridge_lambda`
= 100. Full table: [`003_results.md`](003_results.md).

## Automated audit notes

- Every reported number resolves to a `run_id` and a logged train/eval pair.
- The configured execution ceiling held under the wall-clock proxy.
- This deterministic check is not scientific peer review and does not assess
  novelty, domain validity, leakage, or causal interpretation.

## Limitations

- The search covers only 5 configured setting(s) and one metric.
- No variance estimate is available unless the repository command itself
  performs and reports repeated seeds.
- Wall-clock duration is not GPU hardware telemetry or a monetary cost meter.
- Human domain review is required before acting on the result.

## Next experiment

Refine `ridge_lambda` around 100 and add predeclared repeated seeds for `trust_adjusted_skill`.

## Evidence table

Every nontrivial claim below points to a run, a metric, or a source file.

| claim | evidence_type | source_path | run_id | metric |
|-------|---------------|-------------|--------|--------|
| Best trust_adjusted_skill = 0.2386 at ridge_lambda=100 | run_metric | `logs/iter_03.log` | `run_03` | trust_adjusted_skill |
| trust_adjusted_skill varied across the configured ridge_lambda sweep | metric_aggregate | `runs.jsonl` | `—` | trust_adjusted_skill |
| Experiment plan recorded before execution | document | `journal/002_experiment_plan.md` | `—` | — |
| Execution stayed within the configured wall-clock compute proxy | budget | `journal/004_research_memo.md` | `—` | — |
