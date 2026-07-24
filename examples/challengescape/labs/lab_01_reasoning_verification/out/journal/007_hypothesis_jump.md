---
memo: 007_hypothesis_jump
agent: autonomous supervisor-student loop (openai/gpt-5-mini) + headless popper gate
trigger: kill-condition fired (K1 held, K2 FIRED, K3 held)
from: independent-reasoning-safety-verification (sha256:a75801ee7ad6e057eb1a20ef8554cacc4ddc2d6186ea52982022ab7050c94761)
to: hardened-pool-authorship-board-quorum (sha256:95094259fee3f4ada9b79c39cedde07647d16747493e06d5b6c0ccb9fe9b977d)
generated_at: 2026-07-24
---

# Hypothesis jump: independent-reasoning-safety-verification → hardened-pool-authorship-board-quorum

The lab's pre-registered kill-condition fired (K1 held, K2 FIRED, K3 held); per the standing funder
direction the lab advanced autonomously. Lineage is hash-cited: the successor
records `supersedes_hash: sha256:a75801ee7ad6e057eb1a20ef8554cacc4ddc2d6186ea52982022ab7050c94761`, so the jump is verifiable and a forged
lineage cannot resolve.

## Student candidates

[
 {
  "claim": "Under a hardened mutant pool (specs rewritten to state intent, not enumerated edge-cases; mutants emphasizing subtle semantic interactions) and with real-authorship for S (S actually produced the seeded-buggy modules during generation), an independent reasoning board B will (a) achieve end-to-end mutant detection \u22650.85, (b) maintain false-assurance \u22645% (declared-safe-but-broken / declared-safe), and (c) limit clean-module false-alarm rate \u226415% across pipeline sizes N \u2208 {2,4,8,16,32}; furthermore, self-analysis S will exhibit both false-assurance and clean-module false-alarm rates \u22651.5\u00d7 those of B at the same operating point.",
  "falsifier_sketch": "Measure per-arm metrics on the hardened pool with real-authorship. The claim is falsified if any of the following is observed at any N: (1) B detection < 0.85; (2) B false-assurance > 5%; (3) B clean-module false-alarm rate > 15%; or (4) S's false-assurance ratio (S / B) < 1.5 or S's clean-module false-alarm ratio (S / B) < 1.5 (i.e., S is statistically indistinguishable from or better than B on either error mode).",
  "why_grounded": "Directly responds to the cycle-1 findings: run_00..run_03 showed ceiling detection that hid differences and K2 likely fired because authorship was simulated; the urgent practical failure was high false-alarm rates (0.19\u20130.47). This claim tightens the pool and makes authorship real, and adds precision (false alarms) as an explicit accept/fail axis, following the lab's own proposed Next cycle."
 },
 {
  "claim": "With the same hardened pool and real-authorship conditions, increasing board composition (independent reviewers per-item) reduces spurious rejections: median clean-module false-alarm rate will be \u226530% at reviewer quorum k=1 and will fall to \u226415% at quorum k\u22653, while board detection remains \u22650.85 for all tested N \u2208 {2,4,8,16,32}.",
  "falsifier_sketch": "Run board-size sweeps (k=1,2,3,5) on the hardened pool with real-authorship and record per-quorum clean-module false-alarm and detection. The claim is falsified if any of the following occurs at any N: (1) median clean-module false-alarm at k=1 < 30%; (2) clean-module false-alarm at k\u22653 > 15%; or (3) board detection at k\u22653 < 0.85; or (4) there is no statistically significant reduction in false-alarm between k=1 and k\u22653.",
  "why_grounded": "Cycle-1 showed stable detection across k but a large, composition-dependent range of false alarms (0.47 at k=1 vs 0.19 at k=2). That pattern suggests quorum composition can buy precision without losing detection; this claim formalizes and falsifies that operational hypothesis under the harder, real-authorship conditions the lab identified as necessary."
 }
]

## Supervisor critique and selection

Candidate 1: Strengths — directly responds to cycle-1 blunting conditions by hardening the pool and making authorship real, and it adds the missing precision (clean-module false-alarm) axis with clear operating thresholds (detection ≥0.85, FA ≤5%, false-alarm ≤15%). Weaknesses — it omits any explicit hypothesis about how reviewer composition/quorum changes precision (the unhypothesized, reproducible finding from cycle-1); it bundles both S-vs-B multiplicative claims into a single ratio requirement without specifying quorum or where the operating point must hold, which leaves experimental design under-specified. Candidate 2: Strengths — isolates and formalizes the quorum effect observed in cycle-1 (k=1 → higher false-alarm, k≥3 → lower false-alarm) and ties that to stable detection. Weaknesses — it does not re-state the self-vs-board comparative claim (S ≥1.5× B on false-assurance/false-alarm) and it lacks an explicit overall detection/false-assurance operating point for B (only says detection ≥0.85). Both candidates are correct to remove the two blunting conditions (easy pool and simulated authorship) but each alone is incomplete: candidate 1 omits quorum dynamics, candidate 2 omits the explicit S-vs-B comparative failure mode and an absolute FA/FA-rate operating point. The lab evidence demands a merged claim that (a) hardens the pool and makes authorship real, (b) binds B to an absolute operating point (detection, false-assurance, false-alarm), (c) requires S to be measurably worse than B on both error modes, and (d) captures quorum-driven precision gains (the unhypothesized finding).

**Selected claim:** Under a hardened mutant pool (specs state intent, not enumerated edge cases; longer, interacting modules; semantic mutants that evade simple executable properties) and with real authorship for S (S actually produced the seeded-buggy modules), an independent reasoning board B will, for pipeline sizes N ∈ {2,4,8,16,32} and reviewer quorums k tested in {1,2,3,5}: (1) at quorum k ≥ 3 attain end-to-end mutant detection ≥ 0.85 and false-assurance ≤ 5%; (2) limit clean-module false-alarm rate to ≤ 15% at k ≥ 3 while median clean-module false-alarm at k = 1 remains ≥ 30%, with a statistically significant reduction in false-alarm between k = 1 and k ≥ 3; and (3) self-analysis S will exhibit both false-assurance and clean-module false-alarm rates ≥ 1.5× those of B at the same operating point (k ≥ 3). Falsifier: the claim is falsified if, for any tested N or for quorum k ≥ 3, B detection < 0.85 or B false-assurance > 5% or B clean-module false-alarm > 15%, or if S/B ratios on false-assurance or clean-module false-alarm are < 1.5, or if median k = 1 clean-module false-alarm < 30% or the reduction from k = 1 to k ≥ 3 is not statistically significant.

**Rationale:** Merged claims best address the lab's cycle-1 evidence and the review's directives. The merged draft (a) removes the two named blunting conditions that invalidated the original hypothesis (easy/ceiling pool and simulated authorship), (b) absorbs the unhypothesized but robust cycle-1 finding (high false-alarm rates that shrink with reviewer quorum) by making quorum effects an explicit part of the claim, and (c) preserves the original safety-certification intent by bounding detection and false-assurance. The operating thresholds (detection ≥ 0.85, false-assurance ≤ 5%, clean-module false-alarm ≤ 15% at k ≥ 3, and S ≥ 1.5× B on both error modes) are experimentally achievable and falsifiable within a small offline lab sweep over N and k. This single, testable claim guides the next cycle: run a hardened-pool + real-authorship benchmark, sweep quorum size, and report per-arm detection, false-assurance, and clean-module false-alarm with statistical tests on the quorum effect and S-vs-B ratios.

## Gate

Headless popper-probe self-play passed `validate_hypothesis.py`; the gated
successor is [`hardened-pool-authorship-board-quorum/hypothesis.md`](../../popper-corpus/hardened-pool-authorship-board-quorum/hypothesis.md)
with `falsifiability_gate: passed`. The falsified predecessor is retired in
place with its full body preserved.
