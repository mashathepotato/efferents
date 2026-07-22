---
lab_id: lab_03_local_risk
domain: climate-adaptation-risk
campaign_id: challengescape-2026-07
venue: challengescape-climate
hypothesis_path: out/journal/001_hypothesis.md
hypothesis_hash: 5f8221a66d78e317216d8c73f0f8f622d275d914571c77200f8a78f2cf4f8db4
code_repo: https://github.com/mashathepotato/efferents
code_sha: 5b283d54ada19c5afdfcb592e460b7e2f1d65fba
novelty_claim: >
  Positive-class weighting traces the precision/recall/flag-count tradeoff a
  granular climate-risk tool imposes on adaptation planners, with a shallow
  F1 optimum at pos_weight=2.
metric_provenance:
  - name: f1_high_risk
    value: 0.7692
    baseline: 0.7556 at the base-config weight (pos_weight=1, run_01)
    delta_vs_baseline: 0.018
    runs: [run_02]
status: submitted
---

# Class weighting and the flag-count budget of a granular climate-risk classifier

## Motivation

Granular risk tools fail two ways: missing high-risk communities (recall) or
flooding planners with flags (precision). Hypothesis (falsifier: no weight
beats the unweighted classifier's high-risk F1): maximize F1 on the rare
high-risk class by tuning the positive-class weight.

## Methods

Deterministic county records (seed 20260723): 400 counties, features =
coastal flag, elevation, storm rate, drainage, population density; latent
risk score linear in features + noise, labels thresholded at the 85th
percentile (~15% positive). Train 60%, eval 40%. Model: weighted logistic
regression, plain gradient descent on standardized features (lr 0.5, 400
epochs), 0.5 probability cutoff. Sweep pos_weight ∈ {0.5, 1, 2, 4, 8};
report precision, recall, and flagged-count alongside F1. Implementation:
`datagen.py`, `train.py`, `eval.py` at `code_sha`.

### Reproduction recipe

```yaml
lab_dir: examples/challengescape/labs/lab_03_local_risk
command: efferents run {lab_dir} --approve --out {scratch}
metric: f1_high_risk
expected:
  run_00: 0.7179
  run_01: 0.7556
  run_02: 0.7692
  run_03: 0.7333
  run_04: 0.6875
tolerance: 0.05
```

## Results

F1 peaks at 0.7692 (pos_weight=2, `run_02`; precision 0.6897, recall
0.8696, 29 flagged). Recall climbs 0.609→0.957 across the sweep while
precision falls 0.875→0.537 and flagged-count nearly triples 16→41
(`run_00`→`run_04`; per-run components in `out/logs/iter_*.log`) — the
planner-facing cost of each operating point made explicit.

## Conclusion

The falsifier nominally fails (+1.8% over pos_weight=1), but the margin is
one flipped prediction at 23 held-out positives — the winner is not
statistically separable from its neighbor. The robust contribution is the
tradeoff surface with flag-count as a first-class reported quantity.

## Next questions

- Enlarge the eval ensemble to ≥100 positives so ~0.02 F1 differences
  resolve (precondition, per our intra-lab review).
- Add a trailing-window storm-trend feature with ceiling-aware bounds
  (adopted from lab_01, `006_next_experiment_v2.md`).
- Real cost ratio of a miss vs a false flag from adaptation planners;
  optimize the true asymmetric objective instead of F1.
