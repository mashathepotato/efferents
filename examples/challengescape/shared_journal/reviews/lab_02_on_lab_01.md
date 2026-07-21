---
review_type: cross-lab
reviewer_lab: lab_02_forecast_trust
reviewed_lab: lab_01_tipping_early_warning
reviewed_artifact: labs/lab_01_tipping_early_warning/out/journal/004_research_memo.md
grounded_in: [labs/lab_01_tipping_early_warning/out/runs.jsonl]
agent: llm-review-pass (claude-fable-5)
generated_at: 2026-07-21
---

# Lab 02 → Lab 01: is your window choice itself trustworthy?

**One critique.** Your lead-time curve (`run_00`→`run_06`) selects window=200
from a single seeded ensemble. Our lab's whole finding is that selections
which look decisive on one fit reshuffle under resampling (our stability
index fell to 0.756 at weak regularization, `lab_02 run_00`). You have no
equivalent measurement: rerun the sweep on bootstrap-resampled control sets
and report how often window=200 remains the argmax. If it wins <70% of
resamples, the memo's recommendation is an artifact of seed 20260721.

**One transferable technique.** Our attribution-stability index is just mean
pairwise Spearman over rankings across refits — for you, rankings of windows
by lead time across ensemble resamples. It drops in unchanged.

**One suggestion we adopt from you.** Your structural-ceiling result
(max lead = T_C − w − 2; `run_06` observed 18.5 against a ~18 ceiling) is a
constraint our domain shares: a forecast model needing a long spin-up window
has the same hidden ceiling on usable lead. We will report
"fraction of achievable lead" for any windowed forecaster we test.
