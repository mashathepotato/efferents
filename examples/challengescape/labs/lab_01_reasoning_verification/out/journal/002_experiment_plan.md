---
memo: 002_experiment_plan
agent: researcher
generated_at: 2026-07-24T17:25:30.032585+00:00
approval_mode: plan_then_execute
execution_authorized: true
---

# Experiment plan

**Objective:** minimize the false-assurance rate of the independent reasoning board on seeded safety violations in N-agent codebases by tuning the verification configuration (board size), holding detection >= 90% — kill-conditions K1-K3 in the hypothesis stand as fixed pass/fail lines


Each experiment runs:

```
train: python3 train.py --config {config_path}
eval:  python3 eval.py --checkpoint {checkpoint}
```

| # | experiment |
|---|------------|
| 1 | board_size=1 |
| 2 | board_size=2 |
| 3 | board_size=3 |
| 4 | board_size=5 |

**Budget ceiling:** 0.5 GPU-hours, $0.0 LLM spend.
**Approval mode:** `plan_then_execute`.
**Execution authorized:** `true`.
This plan is recorded before any experiment runs.
