# repo-adapter example

A runnable, **fully offline** example of pointing efferents at an existing ML
repo via a single `efferents.yaml`.

```bash
efferents run examples/repo-adapter      # writes ./efferents-run/
open efferents-run/dashboard.html
```

## What's here

- `train.py` — a toy 1-D logistic-regression classifier on a fixed synthetic
  dataset (plain Python, no numpy/GPU, no pip deps). Prints
  `{"checkpoint": "<path>"}` on stdout.
- `eval.py` — computes `val_f1` on a held-out imbalanced set using the
  checkpoint's decision threshold. Prints `{"metrics": {"val_f1": <v>}}`.
- `configs/base.yaml` — base hyperparameters; the runner overlays the swept value.
- `efferents.yaml` — the adapter config: goal, train/eval commands, sweep,
  metric, budget, approval.

## What it proves

efferents reads `efferents.yaml`, sweeps the decision `threshold`, runs the
repo's **real** train + eval each iteration, parses `val_f1`, finds the interior
optimum (threshold 0.65 → val_f1 0.8889), and writes a reviewed memo with an
evidence table linking every claim to a run id and a train/eval log — all on
local compute, no API key.

To adapt for your own repo: replace `train.py` / `eval.py` with your commands
and update `efferents.yaml`. The only contract is the two stdout JSON lines
above.
