---
memo: 005_review
agent: llm-review-pass (claude-fable-5)
reviews: 004_research_memo.md
grounded_in: [runs.jsonl, logs/]
review_type: post-hoc agent review — not human domain review
generated_at: 2026-07-21
---

# Review: tipping-point early-warning memo

**Verdict: accept with mandatory caveats.** The sweep is internally sound and
every number checks against `runs.jsonl`, but two findings must temper the
headline before anyone quotes it.

## What checks out

- The headline (mean_lead_time=97.5 at window=200, `run_04`) matches
  `logs/iter_04.log`, with `detected_frac=1.0` and
  `control_false_alarm_rate=0.0` — the lead time is not bought with false
  alarms.
- The interior optimum is real within this design: lead rises monotonically
  through `run_00`→`run_04` (32.6→97.5), then falls at `run_05` (77.7) and
  collapses at `run_06` (18.5).

## Substantive objections

1. **The large-window collapse is partly mechanical, not statistical.** A
   window of length w cannot produce an alarm before t≈w+2, so the maximum
   achievable lead at window=380 is ~18 steps — and `run_06` observed 18.5,
   i.e. the detector saturates its ceiling. The memo's tradeoff curve
   conflates estimator quality with this hard ceiling. **Required fix:**
   report lead time as a fraction of the achievable maximum (T_C − w − 2)
   alongside raw lead.
2. **Threshold calibration rests on 10 control series.** The 95th-percentile
   threshold interpolates between the top two control maxima; its sampling
   variance is untested. `run_00`'s nonzero false-alarm rate (0.1,
   `logs/iter_00.log`) hints the calibration is fragile at small windows.
3. **Single ensemble seed.** All results derive from one seeded ensemble
   (`datagen.py`, seed 20260721). The memo's own limitations section says
   this; it bears repeating because lead-time variance across ensembles is
   exactly what an operator would ask for.
4. **Misses scored as zero lead** conflate detection rate with earliness:
   `run_01` (window=25) mixes 30% misses into its 66.4 mean
   (`detected_frac=0.7`, `logs/iter_01.log`). Report the two separately.

## Evidence table

| claim | evidence_type | source_path | run_id | metric |
|-------|---------------|-------------|--------|--------|
| Headline lead 97.5 with zero false alarms | run_metric | `logs/iter_04.log` | `run_04` | mean_lead_time |
| window=380 saturates its structural ceiling (~18 vs 18.5 observed) | run_metric | `logs/iter_06.log` | `run_06` | mean_lead_time |
| Small-window calibration fragility (FA rate 0.1) | run_metric | `logs/iter_00.log` | `run_00` | control_false_alarm_rate |
| 30% misses folded into the window=25 mean | run_metric | `logs/iter_01.log` | `run_01` | detected_frac |
