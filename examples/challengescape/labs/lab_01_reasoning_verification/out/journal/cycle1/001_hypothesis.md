---
memo: 001_hypothesis
agent: researcher
generated_at: 2026-07-24T17:25:30.032349+00:00
---

# Objective

minimize the false-assurance rate of the independent reasoning board on seeded safety violations in N-agent codebases by tuning the verification configuration (board size), holding detection >= 90% — kill-conditions K1-K3 in the hypothesis stand as fixed pass/fail lines


**Metric:** `false_assurance_rate` (minimize).

**Search space:** `board_size` ∈ {1, 2, 3, 5}

## Why this is testable

Each experiment runs the repo's own train + eval commands and reports a single
scalar (`false_assurance_rate`). The configurations are ordered, so the loop either
finds a setting that moves the metric or shows the metric is flat across the
search space.
