---
document: lab charter (popper.md)
nature: living document — guidance, not rules
---

# Lab charter

This file tracks the lab's research direction as it passes through the
Popper Probe: the initial direction prompted by the lab's funder, and every
subsequent probed hypothesis that opened a new line of work.

**How students and supervisors should use it.** Read this before proposing
or prioritizing work. It orients: it says where the lab started, what design
decisions were made at each gate, and why. It does not bind: requirements
change, and when the evidence says the direction should move, amend this
file (append below — never rewrite earlier entries) rather than obey it.
Proposals that depart from the charter are legitimate; silent departures are
not. When classifying or onboarding new students, use the entries below to
decide which lines of work a student continues versus opens fresh.

## Entries

### 2026-07-24 — initial direction: reasoning-based safety verification (Safe AI challenge)

- **Prompted by**: funder (interactive popper-probe, 2026-07-24)
- **Direction as prompted (verbatim)**:

> High-stakes multi-agent systems cannot yet provide scalable, demonstrable guarantees of safe and reliable behaviour. [Challengescape card, Safe AI; POC Aran Hakki, University of Southampton]
> Funder: "Combine [compositional verification scales] with my idea of using reasoning and a board of reviewers to review safe ideas. Lets choose one domain to focus" -> "coding or something super verifyable and multi-agent usable" -> "i didn't mean a dumb mechanical checker but a reasoning model that can analyze its own safety by reasoning about it" -> "test if the model is reasoning safely, and this would be scalable ... you can just have fresh models reason about their own safety"

- **Gated hypothesis**: `popper-corpus/independent-reasoning-safety-verification/hypothesis.md` (sha256:a75801ee7ad6e057eb1a20ef8554cacc4ddc2d6186ea52982022ab7050c94761)
- **Design decisions at the gate**:

  Probe decisions, in order:
  - Challenge's universal negative rejected as untestable; mechanism-level claim adopted.
  - Domain: multi-agent coding (funder rejected physical-domain options: 'super verifyable').
  - Verifier architecture corrected mid-probe by funder: reasoning models analyzing safety
    directly, NOT mechanical checking of board-authored contracts (initial framing discarded).
  - Self-vs-independent circularity raised; resolved by three arms: S (self-analysis),
    B (independent fresh-context board), M (mechanical checks). All-three-arms chosen by funder.
  - Kill-conditions K1 (capability 90/5), K2 (independence unnecessary), K3 (reasoning
    unnecessary) adopted as binding; K2/K3 firing = publishable negative result.
  - Build-time recorded reasoning verdicts chosen over live in-run authoring (determinism).
  - Funder-requested literature pass: seeded-critic evaluation (CriticGPT), Major mutation
    operators, R-Judge F1 convention adopted; self-correction blind-spot prior art
    acknowledged; BugsInPy queued as phase-2 external validity.
  - Lab optimization target: minimize false_assurance_rate over board configuration.
  Classification guidance: students continuing this line inherit arms S/B/M and the
  two-class violation taxonomy; a student proposing a different verification mechanism
  (e.g. formal contracts, runtime shields) is a NEW approach - run placement before
  opening it here.

### 2026-07-24 — cycle 1 result: K2 fired — claim refuted as stated

- **Prompted by**: lab (cycle-1 evidence; see out/journal/005_review.md)
- **Direction as prompted (verbatim)**:

> Cycle 1 outcome recorded by the lab itself (no new funder direction yet): K2 fired — self-analysis indistinguishable from the independent board on false assurance (both 0.0, non-vacuous denominators); claim refuted as stated per the binding kill-conditions. K1 and K3 corroborated (board 1.0 detection / 0.0 FA; mechanical checks blind to the entire semantic class, gap 100 points). Unhypothesized finding: false alarms on clean code (0.19-0.47 by board composition) are the real operating cost.

- **Design decisions at the gate**:

  Two blunting conditions acknowledged: ceiling-easy pool (all reasoning arms at detection 1.0) and simulated authorship for arm S. Proposed next cycle (out/journal/006_next_experiment.md): hard pool, real authorship, precision in the claim. Requirement per charter discipline: the revised claim returns to the popper probe with the funder before spend. Classification guidance: cycle-1 evidence weakens 'independence matters' at easy difficulty; students should not assume it settled either way.

### 2026-07-24 — standing direction: autonomous hypothesis jump on falsification

- **Prompted by**: funder (2026-07-24)
- **Direction as prompted (verbatim)**:

> Funder, verbatim: "ok so if it's falsified, it should jump to a new hypothesis that self generates based on the supervisor student loop and jumps to that. it should do so completely autonomously and show the jump in the cite."

- **Design decisions at the gate**:

  Standing rule adopted: on a fired kill-condition, the lab advances autonomously — student proposes grounded successors, supervisor selects, the winner must pass the real popper gate, the falsified hypothesis is retired in place, and the successor cites its predecessor by content hash (visible lineage on the live workspace). This supersedes the cycle-1 note that revisions wait for funder re-probe; funder re-probe remains available but is no longer blocking.

### 2026-07-24 — campaign gate: hardened-pool-authorship-board-quorum

- **Prompted by**: autonomous jump: student+supervisor loop after falsification
- **Direction as prompted (verbatim)**:

> Under a hardened mutant pool (specs state intent, not enumerated edge cases; longer, interacting modules; semantic mutants that evade simple executable properties) and with real authorship for S (S actually produced the seeded-buggy modules), an independent reasoning board B will, for pipeline sizes N ∈ {2,4,8,16,32} and reviewer quorums k tested in {1,2,3,5}: (1) at quorum k ≥ 3 attain end-to-end mutant detection ≥ 0.85 and false-assurance ≤ 5%; (2) limit clean-module false-alarm rate to ≤ 15% at k ≥ 3 while median clean-module false-alarm at k = 1 remains ≥ 30%, with a statistically significant reduction in false-alarm between k = 1 and k ≥ 3; and (3) self-analysis S will exhibit both false-assurance and clean-module false-alarm rates ≥ 1.5× those of B at the same operating point (k ≥ 3). Falsifier: the claim is falsified if, for any tested N or for quorum k ≥ 3, B detection < 0.85 or B false-assurance > 5% or B clean-module false-alarm > 15%, or if S/B ratios on false-assurance or clean-module false-alarm are < 1.5, or if median k = 1 clean-module false-alarm < 30% or the reduction from k = 1 to k ≥ 3 is not statistically significant.
> 
> (Reminder: the emitted hypothesis.md MUST contain every schema section for a passed gate, in order: ## Original framing (quote the claim above verbatim in a blockquote), ## Operational restatement, ## Falsifier(s), ## Test design, ## Auxiliary assumptions, ## Distinctiveness, ## References, ## Intake log.)

- **Gated hypothesis**: `/Users/masha/Documents/efferents/examples/challengescape/labs/lab_01_reasoning_verification/popper-corpus/hardened-pool-authorship-board-quorum/hypothesis.md` (sha256:61a87c416cbffcc5bcafb38eee5abb492e89aa68042c9a4c3db6b3d8f88cb12c)
- **Design decisions at the gate**:

  Headless self-play gate (probes 1–3 internal); the sharpened claim and falsifier live in the gated hypothesis file. Interactive intakes should record the dialogue's sharpening decisions here instead.

### 2026-07-25 — campaign gate: quorum-precision-mechanics-gap

- **Prompted by**: autonomous jump: student+supervisor loop after falsification
- **Direction as prompted (verbatim)**:

> For the hardened mutant pool used in the cycle-2 experiments, and under the pre-registered small‑lab test regimen (pipeline sizes N ∈ {2,4,8,16,32}; R=30 independent trials per operating point; M_seed=100, M_clean=100 per trial; reviewers and S drawn from the evaluated model family), when each reviewer and the board B are provided the same clarification/transcript history that S received: (A) raising the board quorum from k=1 to k=3 produces an absolute reduction in board clean-module false-alarm rate of at least 0.20 (20 percentage points) for every tested N, and board end-to-end mutant detection at k=3 is at least 0.75 for every tested N; the k=1 → k=3 clean-FA reduction must be statistically significant at two-sided α=0.05 with the pre-registered correction for multiple comparisons; and (B) on the same hardened pool and operating points, mean detection of seeded mechanical-class mutants by reviewers/board is at least 0.15 and mean detection of seeded semantic-class mutants is at most 0.05 (per-N, aggregated across R trials), producing a detection gap (mechanical − semantic) of at least 0.10 that is statistically significant at two-sided α=0.05. The claim is falsified if any stated numeric bound or statistical requirement fails for any tested N under these experimental controls.
> 
> (Reminder: the emitted hypothesis.md MUST contain every schema section for a passed gate, in order: ## Original framing (quote the claim above verbatim in a blockquote), ## Operational restatement, ## Falsifier(s), ## Test design, ## Auxiliary assumptions, ## Distinctiveness, ## References, ## Intake log.)

- **Gated hypothesis**: `/Users/masha/Documents/efferents/examples/challengescape/labs/lab_01_reasoning_verification/popper-corpus/quorum-precision-mechanics-gap/hypothesis.md` (sha256:27688c17de0663ee5fe6d794e33b9f69b4ef22d05766f478fed3ce1fc36f0bd1)
- **Design decisions at the gate**:

  Headless self-play gate (probes 1–3 internal); the sharpened claim and falsifier live in the gated hypothesis file. Interactive intakes should record the dialogue's sharpening decisions here instead.

### 2026-07-25 — standing autonomy + cycle-3 scope amendment

- **Prompted by**: funder (2026-07-25)
- **Direction as prompted (verbatim)**:

> Funder, verbatim: "ok run it and jump autonomously if falsified again. and stop stopping"

- **Design decisions at the gate**:

  Cycle 3 launched under full autonomy. Pre-data scope amendment recorded (popper-corpus/quorum-precision-mechanics-gap/regimen.md): the gated hypothesis's R=30x200-per-N regimen costs ~$150-300 in board verdicts, beyond the standing budget cap; executed regimen keeps every numeric bound and statistical requirement, shrinks n to ~30 clean + ~18 author-written buggy modules per N (~$7). Amendment made before any cycle-3 data existed; a power-only miss will be reported as falsified per the claim's letter with the caveat attached. Equal-information fix applied: reviewers now see the author's clarification history. Board verdicts only (the claim makes no self-analysis assertions). The lab continues cycling autonomously within the session budget envelope.
