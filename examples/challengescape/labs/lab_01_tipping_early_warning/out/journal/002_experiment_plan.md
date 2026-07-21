---
memo: 002_experiment_plan
agent: researcher
generated_at: 2026-07-21T22:02:04.905666+00:00
approval_mode: plan_then_execute
execution_authorized: true
---

# Experiment plan

**Objective:** maximize the mean detection lead time of an early-warning alarm for a tipping transition, at a fixed ~5% series-level false-alarm rate, by tuning the rolling-window length of the lag-1 autocorrelation indicator


Each experiment runs:

```
train: python3 train.py --config {config_path}
eval:  python3 eval.py --checkpoint {checkpoint}
```

| # | experiment |
|---|------------|
| 1 | window=10 |
| 2 | window=25 |
| 3 | window=50 |
| 4 | window=100 |
| 5 | window=200 |
| 6 | window=300 |
| 7 | window=380 |

**Budget ceiling:** 0.2 GPU-hours, $0.0 LLM spend.
**Approval mode:** `plan_then_execute`.
**Execution authorized:** `true`.
This plan is recorded before any experiment runs.
