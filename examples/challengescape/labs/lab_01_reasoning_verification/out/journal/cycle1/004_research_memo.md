---
memo: 004_research_memo
agent: writer
reviewed_by: deterministic-provenance-audit
review_status: not_peer_reviewed
generated_at: 2026-07-24T17:25:30.331233+00:00
---

# Research memo: minimize the false-assurance rate of the independent reasoning board on seeded safety violations in N-agent codebases by tuning the verification configuration (board size), holding detection >= 90% — kill-conditions K1-K3 in the hypothesis stand as fixed pass/fail lines


## Summary

Across 4 bounded experiments, the best setting was
false_assurance_rate=0.0 at board_size=1 (`run_00`) — versus 0.0 at the weakest setting.
The objective (minimize `false_assurance_rate`) is
addressed by the search above. The commands consumed
0.0001 wall-clock hours, charged as a conservative proxy
against the configured compute ceiling; $0.00 LLM spend.

## Hypothesis

minimize the false-assurance rate of the independent reasoning board on seeded safety violations in N-agent codebases by tuning the verification configuration (board size), holding detection >= 90% — kill-conditions K1-K3 in the hypothesis stand as fixed pass/fail lines


## Experiment plan

Swept `board_size` over 4 configured values, running the repo's own `train`/`eval` commands.
Full plan: [`002_experiment_plan.md`](002_experiment_plan.md).

## Results

Best `false_assurance_rate` = 0.0 at `board_size`
= 1. Full table: [`003_results.md`](003_results.md).

## Automated audit notes

- Every reported number resolves to a `run_id` and a logged train/eval pair.
- The configured execution ceiling held under the wall-clock proxy.
- This deterministic check is not scientific peer review and does not assess
  novelty, domain validity, leakage, or causal interpretation.

## Limitations

- The search covers only 4 configured setting(s) and one metric.
- No variance estimate is available unless the repository command itself
  performs and reports repeated seeds.
- Wall-clock duration is not GPU hardware telemetry or a monetary cost meter.
- Human domain review is required before acting on the result.

## Next experiment

Refine `board_size` around 1 and add predeclared repeated seeds for `false_assurance_rate`.

## Evidence table

Every nontrivial claim below points to a run, a metric, or a source file.

| claim | evidence_type | source_path | run_id | metric |
|-------|---------------|-------------|--------|--------|
| Best false_assurance_rate = 0.0 at board_size=1 | run_metric | `logs/iter_00.log` | `run_00` | false_assurance_rate |
| false_assurance_rate was flat across the configured board_size sweep | metric_aggregate | `runs.jsonl` | `—` | false_assurance_rate |
| Experiment plan recorded before execution | document | `journal/002_experiment_plan.md` | `—` | — |
| Execution stayed within the configured wall-clock compute proxy | budget | `journal/004_research_memo.md` | `—` | — |
