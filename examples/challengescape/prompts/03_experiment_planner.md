# Experiment planner

**Input:** the hypothesis + the lab's train/eval scripts.

**Output:** the `sweep:`, `metric:`, `budget:` sections of `efferents.yaml`.
Choose sweep values that can *reveal structure*, including values expected to
fail (Lab 01 deliberately swept window=380 to expose the structural ceiling).

**Success criteria:** ≤10 sweep points; each train+eval pair completes in
under 120s (the runner's per-command timeout); at least one sweep value
probes a suspected failure regime. The plan is recorded by efferents as
`002_experiment_plan.md` *before* execution — never edit it afterward.

**Provenance:** the runner attaches plan-before-execution ordering.
