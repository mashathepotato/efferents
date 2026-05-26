---
slug: aug-depth-three
created: 2026-05-17
status: active
falsifiability_gate: passed
literature_pass: none
---

# Increasing aug_depth from 1 to 3 reduces W1 by ≥10% on QG1_64x64_1k within 500 epochs

## Original framing

> What if we just deepen the augmentation?

## Operational restatement

With config `default.yaml` and `aug_depth=3` (vs baseline `aug_depth=1`), trained for 500 epochs on QG1_64x64_1k, the energy-distance W1 metric on the val split will be at least 10% lower than the baseline, averaged across 3 seeds.

## Falsifier(s)

- If mean W1 across seeds is within 5% of baseline, claim fails.
- If W1 is worse than baseline at any seed, claim fails.

## Test design

Run baseline + treatment for 3 seeds each at 500 epochs. Use the existing `run.py` CLI. Compare mean W1.

## Auxiliary assumptions

- The W1 implementation in metrics.py is correct.
- 500 epochs is past the convergence elbow.

## Distinctiveness

Competing account (parameter-only fine-tune) predicts no effect; this one predicts ≥10% gain.

## References

## Intake log

- 2026-05-17: drafted from Researcher proposal; passed all probes.
