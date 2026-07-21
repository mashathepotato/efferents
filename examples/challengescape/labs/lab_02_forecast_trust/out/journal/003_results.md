---
memo: 003_results
agent: analyst
generated_at: 2026-07-21T22:02:08.666798+00:00
runs: 5
---

# Results

5 experiments completed locally. Objective: maximize `trust_adjusted_skill`.

| run_id | ridge_lambda | trust_adjusted_skill | |
|--------|------|------|---|
| `run_00` | 0.01 | 0.2041 |
| `run_01` | 1 | 0.2108 |
| `run_02` | 10 | 0.2103 |
| `run_03` | 100 | 0.2386 | ⬅ best
| `run_04` | 1000 | -0.0 |

**Best:** trust_adjusted_skill=0.2386 at ridge_lambda=100 (`run_03`).

> Provenance: every row is one line in [`../runs.jsonl`](../runs.jsonl);
> each run's train+eval stdout is under `logs/`.
