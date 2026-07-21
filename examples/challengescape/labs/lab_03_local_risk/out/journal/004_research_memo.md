---
memo: 004_research_memo
agent: writer
reviewed_by: deterministic-provenance-audit
review_status: not_peer_reviewed
generated_at: 2026-07-21T22:02:10.288401+00:00
---

# Research memo: maximize F1 on the rare high-risk class of a county-level climate-risk classifier by tuning the positive-class weight, so adaptation planners neither miss at-risk communities nor drown in false alarms


## Summary

Across 5 bounded experiments, the best setting was
f1_high_risk=0.7692 at pos_weight=2 (`run_02`) — versus 0.6875 at the weakest setting.
The objective (maximize `f1_high_risk`) is
addressed by the search above. The commands consumed
0.0004 wall-clock hours, charged as a conservative proxy
against the configured compute ceiling; $0.00 LLM spend.

## Hypothesis

maximize F1 on the rare high-risk class of a county-level climate-risk classifier by tuning the positive-class weight, so adaptation planners neither miss at-risk communities nor drown in false alarms


## Experiment plan

Swept `pos_weight` over 5 configured values, running the repo's own `train`/`eval` commands.
Full plan: [`002_experiment_plan.md`](002_experiment_plan.md).

## Results

Best `f1_high_risk` = 0.7692 at `pos_weight`
= 2. Full table: [`003_results.md`](003_results.md).

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

Refine `pos_weight` around 2 and add predeclared repeated seeds for `f1_high_risk`.

## Evidence table

Every nontrivial claim below points to a run, a metric, or a source file.

| claim | evidence_type | source_path | run_id | metric |
|-------|---------------|-------------|--------|--------|
| Best f1_high_risk = 0.7692 at pos_weight=2 | run_metric | `logs/iter_02.log` | `run_02` | f1_high_risk |
| f1_high_risk varied across the configured pos_weight sweep | metric_aggregate | `runs.jsonl` | `—` | f1_high_risk |
| Experiment plan recorded before execution | document | `journal/002_experiment_plan.md` | `—` | — |
| Execution stayed within the configured wall-clock compute proxy | budget | `journal/004_research_memo.md` | `—` | — |
