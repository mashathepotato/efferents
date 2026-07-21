---
memo: 006_next_experiment_v2
supersedes: the "Next experiment" section of 004_research_memo.md
triggered_by: shared_journal/reviews/lab_01_on_lab_03.md
agent: llm-planning-pass (claude-fable-5)
status: proposed — not yet executed
generated_at: 2026-07-21
---

# Revised next experiment: add a storm-trend feature (adopted from Lab 01)

The original next step ("refine pos_weight around 2") is **withdrawn**: the
intra-lab review (`005_review.md`) showed the pos_weight=2 vs 1 gap
(`run_02` 0.7692 vs `run_01` 0.7556) is ~one flipped prediction at 23 eval
positives — refining an unresolvable optimum wastes the cycle.

## New plan, in priority order

1. **Enlarge the eval ensemble** to ≥100 held-out positives (raise
   `N_COUNTIES` in `datagen.py`), so F1 differences of ~0.02 become
   resolvable. Precondition for everything below.
2. **Add a temporal `storm_trend` feature** — trailing-window slope of
   yearly storm counts — adopted from Lab 01's finding that the temporal
   signature of a hazard series carries warning information its level does
   not (`lab_01 run_04`: mean lead 97.5 at window=200).
3. **Sweep the trailing-window length**, not pos_weight, with both
   ceiling-aware bounds Lab 01 established: exclude windows near the full
   record length (`lab_01 run_06`: mechanical collapse) and flag
   calibration fragility at very short windows (`lab_01 run_00`: FA 0.1).
4. **Predeclared success criterion:** the trend feature earns its place iff
   F1 at the fixed pos_weight=2 operating point improves by more than the
   sensitivity band measured in step 1. Otherwise record a null result in
   the journal — a null here is itself useful to Lab 01 (it bounds how far
   early-warning structure transfers to planning granularity).

## Provenance

| input | source |
|-------|--------|
| Unresolvable optimum finding | `005_review.md`, `runs.jsonl` (`run_01`,`run_02`) |
| Trend-feature rationale + window bounds | `../../..//shared_journal/reviews/lab_01_on_lab_03.md`, citing `lab_01 run_00`, `run_04`, `run_06` |
