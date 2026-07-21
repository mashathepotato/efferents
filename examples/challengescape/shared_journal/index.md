# Shared journal — three interconnected Challengescape labs

> **What is real here:** every experiment, metric, and run record in these journals was produced by `efferents run` executing each lab's own train/eval commands, offline and deterministically — rerun `launch_overnight.sh` to reproduce them. Hypothesis framing, reviewer notes, and cross-lab reviews were written by an LLM agent pass grounded in those recorded runs; every quantitative claim cites a run_id. Nothing here is a scientific result — it is a demonstration of autonomous research memory, review, and inter-lab transfer on real challenge framings from Encode's public [Challengescape](https://encode-challengescape.pillar.vc/).

## Labs at a glance

| lab | headline metric | best result | runs | review verdict |
|-----|-----------------|-------------|------|----------------|
| [lab_01_tipping_early_warning](../labs/lab_01_tipping_early_warning/challenge.md) | `mean_lead_time` (max) | **97.5** at `window=200` (`run_04`) | 7 | accept with mandatory caveats |
| [lab_02_forecast_trust](../labs/lab_02_forecast_trust/challenge.md) | `trust_adjusted_skill` (max) | **0.2386** at `ridge_lambda=100` (`run_03`) | 5 | accept the tradeoff finding; reject the metric as a headline without its components |
| [lab_03_local_risk](../labs/lab_03_local_risk/challenge.md) | `f1_high_risk` (max) | **0.7692** at `pos_weight=2` (`run_02`) | 5 | revise — the sweep winner is not statistically separable from its neighbor |

## Cross-lab reviews

- [`lab_01_on_lab_03.md`](reviews/lab_01_on_lab_03.md) — **lab_01_tipping_early_warning** reviews **lab_03_local_risk** — *adopted — see labs/lab_03_local_risk/out/journal/006_next_experiment_v2.md*
- [`lab_02_on_lab_01.md`](reviews/lab_02_on_lab_01.md) — **lab_02_forecast_trust** reviews **lab_01_tipping_early_warning**
- [`lab_03_on_lab_02.md`](reviews/lab_03_on_lab_02.md) — **lab_03_local_risk** reviews **lab_02_forecast_trust**

**The transfer that closed the loop:** Lab 01's window-ceiling and temporal-signature findings ([review](reviews/lab_01_on_lab_03.md)) caused Lab 03 to withdraw its planned next experiment and adopt a storm-trend feature with ceiling-aware window bounds — see [006_next_experiment_v2.md](../labs/lab_03_local_risk/out/journal/006_next_experiment_v2.md).

## lab_01_tipping_early_warning

**Goal:** maximize the mean detection lead time of an early-warning alarm for a tipping transition, at a fixed ~5% series-level false-alarm rate, by tuning the rolling-window length of the lag-1 autocorrelation indicator

**Best run:** `run_04` — mean_lead_time=97.5 at `window=200` ([log](../labs/lab_01_tipping_early_warning/out/logs/iter_04.log))

| run_id | window | mean_lead_time |
|--------|------|------|
| run_00 | 10 | 32.6 |
| run_01 | 25 | 66.4 |
| run_02 | 50 | 74.8 |
| run_03 | 100 | 78.5 |
| run_04 | 200 | 97.5 ◀ best |
| run_05 | 300 | 77.7 |
| run_06 | 380 | 18.5 |

**Review verdict:** accept with mandatory caveats ([full review](../labs/lab_01_tipping_early_warning/out/journal/005_review.md))

**Artifacts:** [001_hypothesis.md](../labs/lab_01_tipping_early_warning/out/journal/001_hypothesis.md) · [002_experiment_plan.md](../labs/lab_01_tipping_early_warning/out/journal/002_experiment_plan.md) · [003_results.md](../labs/lab_01_tipping_early_warning/out/journal/003_results.md) · [004_research_memo.md](../labs/lab_01_tipping_early_warning/out/journal/004_research_memo.md) · [005_review.md](../labs/lab_01_tipping_early_warning/out/journal/005_review.md) · [runs.jsonl](../labs/lab_01_tipping_early_warning/out/runs.jsonl) · [claims.jsonl](../labs/lab_01_tipping_early_warning/out/claims.jsonl) · [dashboard](../labs/lab_01_tipping_early_warning/out/dashboard.html) · [questions for the challenge POC](../labs/lab_01_tipping_early_warning/questions_for_poc.md)

## lab_02_forecast_trust

**Goal:** maximize trust-adjusted forecast skill — skill vs. climatology multiplied by the stability of the model's feature-importance ranking under bootstrap refits — by tuning the ridge penalty of a station-temperature forecaster

**Best run:** `run_03` — trust_adjusted_skill=0.2386 at `ridge_lambda=100` ([log](../labs/lab_02_forecast_trust/out/logs/iter_03.log))

| run_id | ridge_lambda | trust_adjusted_skill |
|--------|------|------|
| run_00 | 0.01 | 0.2041 |
| run_01 | 1 | 0.2108 |
| run_02 | 10 | 0.2103 |
| run_03 | 100 | 0.2386 ◀ best |
| run_04 | 1000 | -0.0 |

**Review verdict:** accept the tradeoff finding; reject the metric as a headline without its components ([full review](../labs/lab_02_forecast_trust/out/journal/005_review.md))

**Artifacts:** [001_hypothesis.md](../labs/lab_02_forecast_trust/out/journal/001_hypothesis.md) · [002_experiment_plan.md](../labs/lab_02_forecast_trust/out/journal/002_experiment_plan.md) · [003_results.md](../labs/lab_02_forecast_trust/out/journal/003_results.md) · [004_research_memo.md](../labs/lab_02_forecast_trust/out/journal/004_research_memo.md) · [005_review.md](../labs/lab_02_forecast_trust/out/journal/005_review.md) · [runs.jsonl](../labs/lab_02_forecast_trust/out/runs.jsonl) · [claims.jsonl](../labs/lab_02_forecast_trust/out/claims.jsonl) · [dashboard](../labs/lab_02_forecast_trust/out/dashboard.html) · [questions for the challenge POC](../labs/lab_02_forecast_trust/questions_for_poc.md)

## lab_03_local_risk

**Goal:** maximize F1 on the rare high-risk class of a county-level climate-risk classifier by tuning the positive-class weight, so adaptation planners neither miss at-risk communities nor drown in false alarms

**Best run:** `run_02` — f1_high_risk=0.7692 at `pos_weight=2` ([log](../labs/lab_03_local_risk/out/logs/iter_02.log))

| run_id | pos_weight | f1_high_risk |
|--------|------|------|
| run_00 | 0.5 | 0.7179 |
| run_01 | 1 | 0.7556 |
| run_02 | 2 | 0.7692 ◀ best |
| run_03 | 4 | 0.7333 |
| run_04 | 8 | 0.6875 |

**Review verdict:** revise — the sweep winner is not statistically separable from its neighbor ([full review](../labs/lab_03_local_risk/out/journal/005_review.md))

**Artifacts:** [001_hypothesis.md](../labs/lab_03_local_risk/out/journal/001_hypothesis.md) · [002_experiment_plan.md](../labs/lab_03_local_risk/out/journal/002_experiment_plan.md) · [003_results.md](../labs/lab_03_local_risk/out/journal/003_results.md) · [004_research_memo.md](../labs/lab_03_local_risk/out/journal/004_research_memo.md) · [005_review.md](../labs/lab_03_local_risk/out/journal/005_review.md) · [006_next_experiment_v2.md](../labs/lab_03_local_risk/out/journal/006_next_experiment_v2.md) · [runs.jsonl](../labs/lab_03_local_risk/out/runs.jsonl) · [claims.jsonl](../labs/lab_03_local_risk/out/claims.jsonl) · [dashboard](../labs/lab_03_local_risk/out/dashboard.html) · [questions for the challenge POC](../labs/lab_03_local_risk/questions_for_poc.md)

