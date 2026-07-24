---
memo: 006_next_experiment
supersedes: the "Next experiment" section of 004_research_memo.md
triggered_by: 005_review.md — K2 fired; ceiling effect; precision finding
agent: llm-planning-pass (claude-fable-5)
status: proposed — awaiting funder direction before execution
generated_at: 2026-07-24
---

# Next cycle: hard pool, real authorship, precision in the claim

Cycle 1 killed the claim as stated (K2: independence indistinguishable from
self-analysis) but under two blunting conditions the review names: a pool
easy enough for universal 1.0 detection, and simulated rather than real
authorship. The revised hypothesis must remove both excuses — and absorb the
finding no kill-condition covered.

1. **Harden the pool until reasoning arms come off the ceiling.** Remove
   spec-named edge-case hints (specs state intent, not enumerated edges);
   longer modules with interacting clauses; subtle mutants (state carried
   across branches, ordering assumptions, float accumulation); target
   detection in the 0.5–0.9 band where arms can separate.
2. **Real authorship for S.** The author model writes each module from the
   spec (recorded); mutations seed the model's own accepted code, or use
   its naturally buggy outputs (labeled by test oracles). Self-review then
   inspects genuinely self-produced code — the condition prior work says
   produces the blind spot. This converts the simulated-authorship
   assumption into a measured variable.
3. **Precision enters the claim.** Cycle 1's real differentiator was false
   alarms (0.19–0.47 by composition). The revised claim must commit to a
   joint operating point (e.g. detection ≥ 0.85 AND clean false alarms
   ≤ 0.15) — a verifier that flags half of all safe code is unusable
   regardless of assurance, which is a scalability failure in exactly the
   challenge's sense.
4. **K2′ restated, harder to dodge**: under real authorship on the hard
   pool, self false-assurance and false-alarm rates are each ≥1.5× the
   board's at the committed operating point — or independence is declared
   unnecessary at realistic difficulty too, which would itself be a strong
   publishable result against the field's fresh-reviewer orthodoxy.

Per the charter, this revision changes the tested claim; it goes back
through the popper probe with the funder before any spend.
