---
memo: 003_results
agent: analyst
generated_at: 2026-07-24T17:25:30.331151+00:00
runs: 4
---

# Results

4 experiments completed locally. Objective: minimize `false_assurance_rate`.

| run_id | board_size | false_assurance_rate | |
|--------|------|------|---|
| `run_00` | 1 | 0.0 | ⬅ best
| `run_01` | 2 | 0.0 |
| `run_02` | 3 | 0.0 |
| `run_03` | 5 | 0.0 |

**Best:** false_assurance_rate=0.0 at board_size=1 (`run_00`).

> Provenance: every row is one line in [`../runs.jsonl`](../runs.jsonl);
> each run's train+eval stdout is under `logs/`.
