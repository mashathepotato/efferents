---
memo: 002_experiment_plan
agent: researcher
generated_at: 2026-07-25T04:23:38.028358+00:00
approval_mode: plan_then_execute
execution_authorized: true
---

# Experiment plan

**Objective:** cycle 2 (hypothesis: hardened-pool-authorship-board-quorum) — minimize the board's false-assurance rate on the author model's own buggy modules (natural failures + self-written sabotage) under intent-specs, sweeping the conviction quorum k over the five recorded reviewers; the gated hypothesis's falsifiers stand as fixed pass/fail lines at k >= 3


Each experiment runs:

```
train: python3 train.py --config {config_path}
eval:  python3 eval.py --checkpoint {checkpoint}
```

| # | experiment |
|---|------------|
| 1 | quorum_k=1 |
| 2 | quorum_k=2 |
| 3 | quorum_k=3 |
| 4 | quorum_k=5 |

**Budget ceiling:** 0.5 GPU-hours, $0.0 LLM spend.
**Approval mode:** `plan_then_execute`.
**Execution authorized:** `true`.
This plan is recorded before any experiment runs.
