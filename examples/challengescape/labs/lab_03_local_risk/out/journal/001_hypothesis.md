---
memo: 001_hypothesis
agent: researcher
generated_at: 2026-07-21T22:02:08.751681+00:00
---

# Objective

maximize F1 on the rare high-risk class of a county-level climate-risk classifier by tuning the positive-class weight, so adaptation planners neither miss at-risk communities nor drown in false alarms


**Metric:** `f1_high_risk` (maximize).

**Search space:** `pos_weight` ∈ {0.5, 1, 2, 4, 8}

## Why this is testable

Each experiment runs the repo's own train + eval commands and reports a single
scalar (`f1_high_risk`). The configurations are ordered, so the loop either
finds a setting that moves the metric or shows the metric is flat across the
search space.
