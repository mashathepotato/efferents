---
memo: 005_review
agent: llm-review-pass (claude-fable-5)
reviews: 004_research_memo.md
grounded_in: [runs.jsonl, logs/]
review_type: post-hoc agent review — not human domain review
generated_at: 2026-07-21
---

# Review: forecast-trust memo

**Verdict: accept the tradeoff finding; reject the metric as a headline
without its components.** The interesting result is in the components, and
the composite hides it.

## What checks out

- Best trust_adjusted_skill 0.2386 at ridge_lambda=100 (`run_03`) matches
  `logs/iter_03.log`: skill_vs_climatology=0.268, attribution_stability=0.8902.
- The finding worth quoting: **stability is nearly free until it isn't.**
  From λ=0.01 to λ=100, skill is flat (0.270→0.268, `run_00` vs `run_03`)
  while stability climbs 0.756→0.890; at λ=1000 (`run_04`) skill collapses to
  −0.0 (rmse_model 2.6884 vs climatology 2.6883) while stability tops out at
  0.911. A stable explanation of a useless model.

## Substantive objections

1. **The product form is arbitrary.** skill×stability implies a specific
   exchange rate between the two that nobody defended. A constraint form
   (maximize skill s.t. stability ≥ τ) selects the same run here but
   generalizes better. The composite also produces the absurd `−0.0` entry
   for `run_04`.
2. **The instability is partly engineered.** The collinear twin features are
   injected with 0.05 noise (`datagen.py`); real covariate collinearity may
   be milder or worse. The result demonstrates the *mechanism*, not its
   real-data magnitude.
3. **Stability is measured on training bootstraps of global |coef| rankings
   only.** Forecasters mostly distrust *per-forecast* explanations; that
   requires a per-sample attribution stability measure this design cannot see.
4. **Single station, single seed** (`datagen.py`, seed 20260722); skill 0.27
   over climatology is modest and its variance is unreported.

## Evidence table

| claim | evidence_type | source_path | run_id | metric |
|-------|---------------|-------------|--------|--------|
| Best composite 0.2386 at λ=100 | run_metric | `logs/iter_03.log` | `run_03` | trust_adjusted_skill |
| Skill flat while stability rises (0.270/0.756 → 0.268/0.890) | run_metric | `logs/iter_00.log`, `logs/iter_03.log` | `run_00`,`run_03` | skill_vs_climatology, attribution_stability |
| λ=1000 destroys skill (rmse 2.6884 vs clim 2.6883), stability 0.911 | run_metric | `logs/iter_04.log` | `run_04` | rmse_model |
