---
memo: 001_hypothesis
agent: researcher
generated_at: 2026-07-21T22:02:04.905191+00:00
---

# Objective

maximize the mean detection lead time of an early-warning alarm for a tipping transition, at a fixed ~5% series-level false-alarm rate, by tuning the rolling-window length of the lag-1 autocorrelation indicator


**Metric:** `mean_lead_time` (maximize).

**Search space:** `window` ∈ {10, 25, 50, 100, 200, 300, 380}

## Why this is testable

Each experiment runs the repo's own train + eval commands and reports a single
scalar (`mean_lead_time`). The configurations are ordered, so the loop either
finds a setting that moves the metric or shows the metric is flat across the
search space.
