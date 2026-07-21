---
memo: 001_hypothesis
agent: researcher
generated_at: 2026-07-21T22:02:07.486949+00:00
---

# Objective

maximize trust-adjusted forecast skill — skill vs. climatology multiplied by the stability of the model's feature-importance ranking under bootstrap refits — by tuning the ridge penalty of a station-temperature forecaster


**Metric:** `trust_adjusted_skill` (maximize).

**Search space:** `ridge_lambda` ∈ {0.01, 1, 10, 100, 1000}

## Why this is testable

Each experiment runs the repo's own train + eval commands and reports a single
scalar (`trust_adjusted_skill`). The configurations are ordered, so the loop either
finds a setting that moves the metric or shows the metric is flat across the
search space.
