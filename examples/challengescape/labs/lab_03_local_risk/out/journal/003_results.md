---
memo: 003_results
agent: analyst
generated_at: 2026-07-21T22:02:10.288218+00:00
runs: 5
---

# Results

5 experiments completed locally. Objective: maximize `f1_high_risk`.

| run_id | pos_weight | f1_high_risk | |
|--------|------|------|---|
| `run_00` | 0.5 | 0.7179 |
| `run_01` | 1 | 0.7556 |
| `run_02` | 2 | 0.7692 | ⬅ best
| `run_03` | 4 | 0.7333 |
| `run_04` | 8 | 0.6875 |

**Best:** f1_high_risk=0.7692 at pos_weight=2 (`run_02`).

> Provenance: every row is one line in [`../runs.jsonl`](../runs.jsonl);
> each run's train+eval stdout is under `logs/`.
