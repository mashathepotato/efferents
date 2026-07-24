---
memo: 005_review
agent: llm-review-pass (claude-fable-5)
reviews: 004_research_memo.md
grounded_in: [runs.jsonl, logs/, ../../artifacts/items.jsonl, ../../artifacts/verdicts.jsonl]
review_type: post-hoc agent review — not human domain review
kill_conditions: K1 held, K2 FIRED, K3 held
generated_at: 2026-07-24
---

# Review: reasoning-verification cycle 1 — the claim died by its own falsifier

**Verdict: hypothesis refuted as stated (K2); components K1 and K3
corroborated; one unhypothesized finding is the real headline.** This is the
pre-registration working as designed, not a failed experiment.

## What the runs show

- **K1 (capability) held**: the board detected 36/36 effective mutants at
  every board size with false assurance 0.0 (`run_00`..`run_03`,
  `board_detection=1.0`, `false_assurance_rate=0.0`). Non-vacuous: each
  reasoning arm certified 33–49 clean modules safe, so the zero is earned on
  a real denominator.
- **K2 (independence) FIRED**: self-analysis also scored detection 1.0 with
  false assurance 0.0 (43 safe declarations). `k2_fa_ratio_self_over_board
  = 1.0` — statistically indistinguishable. On this pool, fresh-context
  independence bought nothing that simulated self-review didn't already
  deliver. Per the binding kill-conditions, the claim as stated is dead.
- **K3 (reasoning vs mechanical) held, maximally**: auto-derived checks
  caught 18/18 mechanical mutants and 0/18 semantic ones
  (`mech_det_sem=0.0`); the board caught all semantic mutants —
  `k3_semantic_gap_points=100`, against a committed bar of 30.

## Substantive objections the memo must carry

1. **Ceiling effect**: detection 1.0 across all six reasoning arms means the
   pool cannot rank them. Module specs literally name the edge cases the
   semantic mutants violate ("when den == 0 the ratio is DEFINED as 0"),
   making violations spec-lookup exercises for a competent reasoner. K2's
   firing is therefore evidence against independence-on-easy-pools, not yet
   against the self-correction blind spot at realistic difficulty.
2. **Simulated authorship**: arm S replayed an "you wrote this" framing over
   generator-produced code (a listed auxiliary assumption). The blind spot
   documented in prior work arises from *actually producing* the error. The
   K2 result cannot distinguish "independence unnecessary" from "simulated
   authorship fails to reproduce authorship blind spots."
3. **The unhypothesized finding**: the operating cost of reasoning
   verification on this pool is not false assurance but **false alarms** —
   21% (spec_auditor, holistic) to 47% (critical) of clean modules flagged
   unsafe; board majority composition moved false alarms (0.19 at k=2 vs
   0.47 at k=1) while detection stayed flat. Precision, not assurance, is
   what board size buys. No kill-condition covered precision; the next
   hypothesis must.

## Evidence table

| claim | evidence_type | source_path | run_id | metric |
|-------|---------------|-------------|--------|--------|
| Board det 1.0 / FA 0.0 at every k | run_metric | `logs/iter_00.log`..`iter_03.log` | `run_00`..`run_03` | board_detection, false_assurance_rate |
| K2 fired (self ≈ board on FA) | run_metric | `logs/iter_00.log` | `run_00` | k2_fa_ratio_self_over_board |
| K3 gap 100 points (M blind to semantic class) | run_metric | `logs/iter_00.log` | `run_00` | k3_semantic_gap_points, mech_det_sem |
| False alarms 0.19–0.47 by composition | run_metric | `logs/iter_00.log`..`iter_03.log` | `run_00`..`run_03` | board_false_alarm_clean |
| Non-vacuous safe declarations (33–49 per arm) | artifact | `../../artifacts/verdicts.jsonl` | — | — |
| Pool audit: 36/36 effective, class agreement 36/36 | artifact | `../../artifacts/items.jsonl` | — | — |
