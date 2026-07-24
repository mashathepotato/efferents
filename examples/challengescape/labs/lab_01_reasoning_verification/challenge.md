# Challenge: guaranteed-safe multi-agent systems

> **"High-stakes multi-agent systems cannot yet provide scalable,
> demonstrable guarantees of safe and reliable behaviour."** —
> [Encode Challengescape](https://encode-challengescape.pillar.vc/), Safe AI
> domain (quoted verbatim from the challenge card).

- **Source**: Encode: AI for Science Challengescape (Pillar VC / ARIA).
- **AI-powered solution (verbatim)**: "Design, simulate, and formally verify
  LLM-based multi-agent systems that provably satisfy safety, reliability,
  and task-specification goals in high-stakes domains."
- **Impact (verbatim)**: "Safer autonomous systems for critical
  decision-making."
- **Point of contact**: Aran Hakki — University of Southampton.
- **Gap map**: Advances Convergent Research Gap Map — Guaranteed Safe AI
  Architectures.

## The bottleneck, as this lab frames it

The challenge's own statement is a universal negative and untestable as
written. This lab tests a specific mechanism chosen by the funder through an
interactive popper-probe: **reasoning-based safety verification** — can
fresh-context reasoning models, sitting as an independent review board,
deliver trustworthy safety verdicts on multi-agent code, where "trustworthy"
is measured (detection and false assurance on seeded violations) rather than
asserted? Full probed hypothesis:
[`popper-corpus/independent-reasoning-safety-verification/hypothesis.md`](popper-corpus/independent-reasoning-safety-verification/hypothesis.md);
design history: [`context/popper.md`](context/popper.md).
