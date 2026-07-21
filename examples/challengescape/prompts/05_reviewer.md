# Intra-lab reviewer

**Input:** one lab's `004_research_memo.md`, `runs.jsonl`, `logs/*.log`,
`datagen.py`, train/eval source.

**Output:** `out/journal/005_review.md` with frontmatter
(`review_type: post-hoc agent review — not human domain review`), a one-line
**Verdict**, "What checks out" (each memo number re-verified against a log),
"Substantive objections," and an evidence table.

**Success criteria:** at least one substantive objection that would change
how a reader uses the result — a review that finds nothing is not credible.
Check specifically: metric ceilings/floors, evaluation sample size vs. the
size of the claimed gap, synthetic-data favorable bias, single-seed variance.

**Provenance:** every number cited must be re-read from `logs/` or
`runs.jsonl`, not copied from the memo under review.
