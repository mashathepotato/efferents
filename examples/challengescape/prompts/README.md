# Agent prompts for the Challengescape multi-lab demo

These prompts define the LLM passes layered on top of the deterministic
`efferents run` artifacts. The runs themselves involve no LLM; these prompts
produced (and reproduce) the review layer: `005_review.md` per lab, the
cross-lab reviews under `shared_journal/reviews/`, and Lab 03's revised plan.

Run them with any capable coding agent pointed at this directory. The
non-negotiable rule appears in every prompt:

> Every quantitative claim must cite a `run_id` and a source path from the
> lab's `runs.jsonl` / `logs/`. If evidence does not exist, write "no
> evidence recorded" — never invent a number.
