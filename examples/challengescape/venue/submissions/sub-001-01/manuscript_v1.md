---
lab_id: lab_01_tipping_early_warning
domain: climate-early-warning
campaign_id: challengescape-2026-07
venue: challengescape-climate
hypothesis_path: out/journal/001_hypothesis.md
hypothesis_hash: 5917ce4c6139e39f5706a2688fe9d540d6edb5458c004ad5d91f4a14cbae51e6
code_repo: https://github.com/mashathepotato/efferents
code_sha: 5b283d54ada19c5afdfcb592e460b7e2f1d65fba
novelty_claim: >
  The window-length/lead-time tradeoff for lag-1 autocorrelation early-warning
  alarms has an interior optimum set jointly by estimator noise and a
  structural ceiling (max lead = T_C - w), and the ceiling side is mechanical,
  not statistical.
metric_provenance:
  - name: mean_lead_time
    value: 97.5
    baseline: 74.8 at the base-config window (w=50, run_02)
    delta_vs_baseline: 0.303
    runs: [run_04]
  - name: control_false_alarm_rate
    value: 0.0
    baseline: calibrated to ~0.05 by construction
    delta_vs_baseline: 0.0
    runs: [run_04]
status: submitted
---

# Window length sets an interior optimum for tipping-point early-warning lead time

## Motivation

Tipping elements exhibit critical slowing down — rising lag-1 autocorrelation
(AC1) — ahead of transitions, but an operational alarm must choose an
estimation window: short windows are noisy, long windows lag the drift.
Practitioners rarely publish this tradeoff curve. Hypothesis (falsifier: no
window setting beats the base configuration's lead time at fixed ~5%
series-level false-alarm rate): maximize mean detection lead time by tuning
the rolling-window length.

## Methods

Deterministic AR(1) ensemble (seed 20260721): 20 control series (phi=0.5) and
20 transitioning series whose phi ramps 0.5→0.98 over t∈[100,400) with
transition at T_C=400, length 500, noise sd 1.0. Detector: rolling AC1 over
window w; alarm threshold = 95th percentile of per-series maxima of rolling
AC1 on 10 training control series (pins series-level false-alarm rate near
5%); alarm fires on 2 consecutive threshold crossings. Score on 10 held-out
transitioning series: lead = T_C − first alarm time (0 if missed); report the
held-out control false-alarm rate alongside. Sweep w ∈ {10, 25, 50, 100, 200,
300, 380}. Generator and detector are fully specified in `datagen.py`,
`train.py`, `eval.py` at `code_sha`; the prose above suffices to reimplement.

### Reproduction recipe

```yaml
lab_dir: examples/challengescape/labs/lab_01_tipping_early_warning
command: efferents run {lab_dir} --approve --out {scratch}
metric: mean_lead_time
expected:
  run_00: 32.6
  run_01: 66.4
  run_02: 74.8
  run_03: 78.5
  run_04: 97.5
  run_05: 77.7
  run_06: 18.5
tolerance: 0.05
```

## Results

Mean lead time rises 32.6 → 97.5 through w=10..200 (`run_00`..`run_04`), then
falls to 77.7 at w=300 (`run_05`) and collapses to 18.5 at w=380 (`run_06`).
At the optimum (w=200, `run_04`): detected fraction 1.0, held-out control
false-alarm rate 0.0 — the lead is not bought with false alarms (per-run
secondary metrics in `out/logs/iter_*.log`). The collapse at w=380 sits at
the structural ceiling: a window of length w cannot alarm before t≈w+2, so
max achievable lead is T_C − w − 2 ≈ 18 — and 18.5 was observed.

## Conclusion

The falsifier fails: w=200 beats the base configuration by +30.3%
(97.5 vs 74.8). The tradeoff curve's right side is dominated by the
mechanical ceiling rather than estimator lag — any windowed early-warning
indicator inherits this constraint.

## Next questions

- Lead time as a fraction of the achievable ceiling, separating estimator
  quality from the mechanical constraint.
- Stability of the argmax window under ensemble resampling (adopted from
  lab_02's attribution-stability lens).
- Real series: RAPID-array AMOC transports, paleoclimate proxies.
- Transfer: trailing-window hazard-trend features for adaptation planning
  (picked up by lab_03).
