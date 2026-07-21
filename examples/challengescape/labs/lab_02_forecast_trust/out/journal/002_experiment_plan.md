---
memo: 002_experiment_plan
agent: researcher
generated_at: 2026-07-21T22:02:07.487247+00:00
approval_mode: plan_then_execute
execution_authorized: true
---

# Experiment plan

**Objective:** maximize trust-adjusted forecast skill — skill vs. climatology multiplied by the stability of the model's feature-importance ranking under bootstrap refits — by tuning the ridge penalty of a station-temperature forecaster


Each experiment runs:

```
train: python3 train.py --config {config_path}
eval:  python3 eval.py --checkpoint {checkpoint}
```

| # | experiment |
|---|------------|
| 1 | ridge_lambda=0.01 |
| 2 | ridge_lambda=1 |
| 3 | ridge_lambda=10 |
| 4 | ridge_lambda=100 |
| 5 | ridge_lambda=1000 |

**Budget ceiling:** 0.2 GPU-hours, $0.0 LLM spend.
**Approval mode:** `plan_then_execute`.
**Execution authorized:** `true`.
This plan is recorded before any experiment runs.
