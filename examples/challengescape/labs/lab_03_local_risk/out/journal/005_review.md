---
memo: 005_review
agent: llm-review-pass (claude-fable-5)
reviews: 004_research_memo.md
grounded_in: [runs.jsonl, logs/]
review_type: post-hoc agent review — not human domain review
generated_at: 2026-07-21
---

# Review: local climate-risk memo

**Verdict: revise — the sweep winner is not statistically separable from its
neighbor.** The tradeoff structure is real and well-reported; the ranking at
the top is noise.

## What checks out

- Best f1_high_risk 0.7692 at pos_weight=2 (`run_02`) matches
  `logs/iter_02.log` (precision 0.6897, recall 0.8696, 29 flagged).
- The precision/recall tradeoff behaves as designed: recall climbs 0.609→0.957
  from `run_00` to `run_04` while precision falls 0.875→0.537, and
  `n_flagged` nearly triples (16→41) — the "planners drown in flags" failure
  mode made visible.

## Substantive objections

1. **23 positives in the eval set** (`n_high_risk_true=23`, any log). The gap
   between `run_02` (0.7692) and `run_01` (0.7556) is roughly one flipped
   prediction. The memo's "best setting" language overstates what 160
   held-out counties can resolve. **Required fix:** either enlarge the eval
   ensemble or report a sensitivity band before naming a winner.
2. **The synthetic label is linear in the features** (`datagen.py`), so
   logistic regression is well-specified by construction — a favorable bias a
   real risk index will not extend.
3. **All features are static snapshots.** Storm *rate* enters as a level;
   hazard *trend* is absent entirely. See the cross-lab review from the
   early-warning lab (`shared_journal/reviews/lab_01_on_lab_03.md`) — adopted
   in `006_next_experiment_v2.md`.

## Evidence table

| claim | evidence_type | source_path | run_id | metric |
|-------|---------------|-------------|--------|--------|
| Best F1 0.7692 at pos_weight=2 | run_metric | `logs/iter_02.log` | `run_02` | f1_high_risk |
| Winner vs runner-up gap ≈ one prediction (23 eval positives) | run_metric | `logs/iter_02.log`, `logs/iter_01.log` | `run_02`,`run_01` | f1_high_risk |
| Flag flood at high weight (16→41 flagged, precision 0.875→0.537) | run_metric | `logs/iter_00.log`, `logs/iter_04.log` | `run_00`,`run_04` | n_flagged, precision_high_risk |
