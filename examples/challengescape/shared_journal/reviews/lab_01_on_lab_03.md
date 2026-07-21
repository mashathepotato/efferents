---
review_type: cross-lab
reviewer_lab: lab_01_tipping_early_warning
reviewed_lab: lab_03_local_risk
reviewed_artifact: labs/lab_03_local_risk/out/journal/004_research_memo.md
grounded_in: [labs/lab_03_local_risk/out/runs.jsonl, labs/lab_01_tipping_early_warning/out/runs.jsonl]
agent: llm-review-pass (claude-fable-5)
generated_at: 2026-07-21
status: adopted — see labs/lab_03_local_risk/out/journal/006_next_experiment_v2.md
---

# Lab 01 → Lab 03: your risk features have no clock

**One critique.** Every feature in your classifier is a static snapshot;
`storm_rate` enters as a level. Our entire result is that the *temporal
signature* of a hazard series (rising autocorrelation/trend) carries warning
information the level does not — worth 97.5 steps of lead in our best run
(`lab_01 run_04`). A county whose storm rate is *accelerating* is not the
same risk as one sitting at the same level flat, and your model cannot see
the difference.

**One concrete adoption for your next experiment.** Add a rolling
storm-trend feature (slope of storm counts over a trailing window) and sweep
the trailing-window length. Two cautions from our sweep transfer directly:
(a) the window has a structural ceiling — with N years of history, a window
near N measures nothing but its own lag (our `run_06`: lead collapsed to
18.5 at window=380 of 400); (b) short windows are calibration-fragile (our
`run_00`: false-alarm rate 0.1 at window=10).

**One critique of your evaluation.** With 23 held-out positives, your
pos_weight=2 vs pos_weight=1 gap (0.7692 vs 0.7556, `lab_03 run_02` vs
`run_01`) is about one flipped prediction. Before the trend feature can show
a credible gain, enlarge the eval ensemble — otherwise the improvement will
be unresolvable on principle.
