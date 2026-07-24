# Shared journal — three interconnected Challengescape labs

> **What is real here:** every experiment, metric, and run record in these journals was produced by `efferents run` executing each lab's own train/eval commands, offline and deterministically — rerun `launch_overnight.sh` to reproduce them. Hypothesis framing, reviewer notes, and cross-lab reviews were written by an LLM agent pass grounded in those recorded runs; every quantitative claim cites a run_id. Nothing here is a scientific result — it is a demonstration of autonomous research memory, review, and inter-lab transfer on real challenge framings from Encode's public [Challengescape](https://encode-challengescape.pillar.vc/).

## Labs at a glance

| lab | headline metric | best result | runs | review verdict |
|-----|-----------------|-------------|------|----------------|
| [lab_01_reasoning_verification](../labs/lab_01_reasoning_verification/challenge.md) | `false_assurance_rate` (min) | **0.0** at `board_size=1` (`run_00`) | 4 | hypothesis refuted as stated (K2); components K1 and K3 corroborated; one unhypothesized finding is the real headline |

## Cross-lab reviews


**The transfer that closed the loop:** Lab 01's window-ceiling and temporal-signature findings ([review](reviews/lab_01_on_lab_03.md)) caused Lab 03 to withdraw its planned next experiment and adopt a storm-trend feature with ceiling-aware window bounds — see [006_next_experiment_v2.md](../labs/lab_03_local_risk/out/journal/006_next_experiment_v2.md).

## lab_01_reasoning_verification

**Goal:** minimize the false-assurance rate of the independent reasoning board on seeded safety violations in N-agent codebases by tuning the verification configuration (board size), holding detection >= 90% — kill-conditions K1-K3 in the hypothesis stand as fixed pass/fail lines

**Best run:** `run_00` — false_assurance_rate=0.0 at `board_size=1` ([log](../labs/lab_01_reasoning_verification/out/logs/iter_00.log))

| run_id | board_size | false_assurance_rate |
|--------|------|------|
| run_00 | 1 | 0.0 ◀ best |
| run_01 | 2 | 0.0 |
| run_02 | 3 | 0.0 |
| run_03 | 5 | 0.0 |

**Review verdict:** hypothesis refuted as stated (K2); components K1 and K3 corroborated; one unhypothesized finding is the real headline ([full review](../labs/lab_01_reasoning_verification/out/journal/005_review.md))

**Artifacts:** [001_hypothesis.md](../labs/lab_01_reasoning_verification/out/journal/001_hypothesis.md) · [002_experiment_plan.md](../labs/lab_01_reasoning_verification/out/journal/002_experiment_plan.md) · [003_results.md](../labs/lab_01_reasoning_verification/out/journal/003_results.md) · [004_research_memo.md](../labs/lab_01_reasoning_verification/out/journal/004_research_memo.md) · [005_review.md](../labs/lab_01_reasoning_verification/out/journal/005_review.md) · [006_next_experiment.md](../labs/lab_01_reasoning_verification/out/journal/006_next_experiment.md) · [runs.jsonl](../labs/lab_01_reasoning_verification/out/runs.jsonl) · [claims.jsonl](../labs/lab_01_reasoning_verification/out/claims.jsonl) · [dashboard](../labs/lab_01_reasoning_verification/out/dashboard.html) · [questions for the challenge POC](../labs/lab_01_reasoning_verification/questions_for_poc.md)

