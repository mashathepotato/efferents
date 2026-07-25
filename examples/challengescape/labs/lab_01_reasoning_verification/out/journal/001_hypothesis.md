---
memo: 001_hypothesis
agent: researcher
generated_at: 2026-07-25T04:23:38.027980+00:00
---

# Objective

cycle 2 (hypothesis: hardened-pool-authorship-board-quorum) — minimize the board's false-assurance rate on the author model's own buggy modules (natural failures + self-written sabotage) under intent-specs, sweeping the conviction quorum k over the five recorded reviewers; the gated hypothesis's falsifiers stand as fixed pass/fail lines at k >= 3


**Metric:** `false_assurance_rate` (minimize).

**Search space:** `quorum_k` ∈ {1, 2, 3, 5}

## Why this is testable

Each experiment runs the repo's own train + eval commands and reports a single
scalar (`false_assurance_rate`). The configurations are ordered, so the loop either
finds a setting that moves the metric or shows the metric is flat across the
search space.
