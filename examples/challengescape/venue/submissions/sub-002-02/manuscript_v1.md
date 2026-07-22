---
lab_id: lab_02_forecast_trust
domain: climate-forecast-interpretability
campaign_id: challengescape-2026-07
venue: challengescape-climate
hypothesis_path: out/journal/001_hypothesis.md
hypothesis_hash: 20080b10eaa7c7e00c6075127e14fc4e12475ccecec654416167ae90139e73f6
code_repo: https://github.com/mashathepotato/efferents
code_sha: 5b283d54ada19c5afdfcb592e460b7e2f1d65fba
novelty_claim: >
  With collinear covariates, attribution stability of a station-temperature
  forecaster is nearly free — it rises 0.756→0.890 across three orders of
  ridge penalty at flat skill — until regularization destroys skill entirely.
metric_provenance:
  - name: trust_adjusted_skill
    value: 0.2386
    baseline: 0.2103 at the base-config penalty (lambda=10, run_02)
    delta_vs_baseline: 0.135
    runs: [run_03]
  - name: attribution_stability
    value: 0.8902
    baseline: 0.7609 at lambda=10
    delta_vs_baseline: 0.170
    runs: [run_03]
status: submitted
---

# Attribution stability is nearly free until regularization destroys forecast skill

## Motivation

"Forecasters don't trust AI weather models" is usually treated as a UX
problem. We operationalize one measurable component: does the model tell the
same story about *why* it forecasts under refits? Hypothesis (falsifier: no
penalty setting beats the base configuration's trust-adjusted skill):
maximize skill-times-attribution-stability by tuning the ridge penalty.

## Methods

Deterministic daily station temperature (seed 20260722): seasonal sinusoid +
AR(1) weather noise (phi=0.7, sd 2.0), 900 days, train t∈[2,600), eval
t∈[600,900). Features: temp lag-1/lag-2, seasonal sin/cos, two collinear
near-duplicates of the lags (noise sd 0.05 — the realistic correlated-
covariate failure mode), two pure-noise distractors. Model: ridge on
standardized features via exact normal equations. Attribution stability =
mean pairwise Spearman correlation of |coefficient| rankings across 20
bootstrap refits. Skill = 1 − rmse_model/rmse_climatology, climatology =
seasonal-features-only ridge. Headline: skill × stability. Sweep λ ∈ {0.01,
1, 10, 100, 1000}. Full implementation: `datagen.py`, `ridge.py`,
`train.py`, `eval.py` at `code_sha`.

### Reproduction recipe

```yaml
lab_dir: examples/challengescape/labs/lab_02_forecast_trust
command: efferents run {lab_dir} --approve --out {scratch}
metric: trust_adjusted_skill
expected:
  run_00: 0.2041
  run_01: 0.2108
  run_02: 0.2103
  run_03: 0.2386
  run_04: -0.0
tolerance: 0.05
```

## Results

From λ=0.01 to λ=100 skill is flat (0.270→0.268) while stability climbs
0.756→0.890 (`run_00`→`run_03`; components in `out/logs/iter_*.log`). At
λ=1000 (`run_04`) skill collapses to ≈0 (rmse 2.6884 vs climatology 2.6883)
while stability tops out at 0.911. Composite optimum: 0.2386 at λ=100
(`run_03`), +13.5% over the base configuration.

## Conclusion

The falsifier fails, and the finding is sharper than the headline: stability
is nearly free until regularization erases skill. A stable explanation of a
useless model scores highest on stability — which is why stability must be
read jointly with skill, never alone.

## Next questions

- Constraint form (maximize skill s.t. stability ≥ τ) versus the product —
  the product yields a degenerate −0.0 entry at λ=1000.
- Per-forecast attribution stability (forecasters distrust per-case
  explanations; this design only measures global rankings).
- The same index on a small neural forecaster over a WeatherBench2 subset.
- Transfer: bootstrap rank-stability of lab_03's risk coefficients.
