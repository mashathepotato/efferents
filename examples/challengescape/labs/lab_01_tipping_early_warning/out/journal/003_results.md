---
memo: 003_results
agent: analyst
generated_at: 2026-07-21T22:02:07.389869+00:00
runs: 7
---

# Results

7 experiments completed locally. Objective: maximize `mean_lead_time`.

| run_id | window | mean_lead_time | |
|--------|------|------|---|
| `run_00` | 10 | 32.6 |
| `run_01` | 25 | 66.4 |
| `run_02` | 50 | 74.8 |
| `run_03` | 100 | 78.5 |
| `run_04` | 200 | 97.5 | ⬅ best
| `run_05` | 300 | 77.7 |
| `run_06` | 380 | 18.5 |

**Best:** mean_lead_time=97.5 at window=200 (`run_04`).

> Provenance: every row is one line in [`../runs.jsonl`](../runs.jsonl);
> each run's train+eval stdout is under `logs/`.
