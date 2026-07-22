---
submission: sub-001-01
round: 1
reviewer: critical
score: 6
recommendation: minor_revision
agent: llm-review-pass (claude-fable-5), critical persona
grounded_in: [manuscript_v1.md, labs/lab_01_tipping_early_warning/out/runs.jsonl]
---

# Critical review (r1): conflated curve, thin calibration

The sweep is internally sound and every number checks against `runs.jsonl`,
but the headline curve conflates two effects the paper itself identifies and
then declines to separate.

1. **The reported tradeoff mixes estimator quality with the mechanical
   ceiling.** The paper proves max lead = T_C − w − 2 (`run_06` observes 18.5
   against a ~18 ceiling), yet the Results table reports raw lead only. At
   w=300 the ceiling is 98 and observed lead is 77.7 — is that estimator lag
   or ceiling pressure? The reader cannot tell.
2. **Threshold calibration rests on 10 control series**; the 95th percentile
   interpolates between the top two maxima. `run_00`'s nonzero false-alarm
   rate (0.1) shows the calibration is fragile exactly where the paper claims
   noise dominates.
3. **Misses are folded into the mean as zero lead** (`run_01`: 30% misses
   inside the 66.4 figure). Detection rate and earliness are different
   quantities.

Single seed is acknowledged; acceptable for a deterministic venue submission
with a mechanical recipe, but the limitation belongs in Results, not only in
Next questions.

## Requested revisions

- Add a lead-as-fraction-of-achievable-ceiling column to the Results table.
- Report detected_frac and mean-lead-over-detections separately from the
  miss-as-zero mean.
- State the 10-series calibration sample and the `run_00` fragility in
  Results, not implicitly.
