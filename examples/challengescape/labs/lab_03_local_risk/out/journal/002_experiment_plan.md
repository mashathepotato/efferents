---
memo: 002_experiment_plan
agent: researcher
generated_at: 2026-07-21T22:02:08.752078+00:00
approval_mode: plan_then_execute
execution_authorized: true
---

# Experiment plan

**Objective:** maximize F1 on the rare high-risk class of a county-level climate-risk classifier by tuning the positive-class weight, so adaptation planners neither miss at-risk communities nor drown in false alarms


Each experiment runs:

```
train: python3 train.py --config {config_path}
eval:  python3 eval.py --checkpoint {checkpoint}
```

| # | experiment |
|---|------------|
| 1 | pos_weight=0.5 |
| 2 | pos_weight=1 |
| 3 | pos_weight=2 |
| 4 | pos_weight=4 |
| 5 | pos_weight=8 |

**Budget ceiling:** 0.2 GPU-hours, $0.0 LLM spend.
**Approval mode:** `plan_then_execute`.
**Execution authorized:** `true`.
This plan is recorded before any experiment runs.
