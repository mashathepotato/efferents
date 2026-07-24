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
