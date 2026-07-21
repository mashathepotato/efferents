---
review_type: cross-lab
reviewer_lab: lab_03_local_risk
reviewed_lab: lab_02_forecast_trust
reviewed_artifact: labs/lab_02_forecast_trust/out/journal/004_research_memo.md
grounded_in: [labs/lab_02_forecast_trust/out/runs.jsonl]
agent: llm-review-pass (claude-fable-5)
generated_at: 2026-07-21
---

# Lab 03 → Lab 02: trust is a decision cost, not a coefficient

**One critique.** Your composite (skill × stability) has no decision
semantics. In our lab every operating point has a visible cost: at
pos_weight=8 planners inspect 41 flags to catch 22 true positives
(`lab_03 run_04`). What is the analogous cost for a forecaster of an
unstable attribution — re-derived briefing? overridden forecast? Until the
composite's exchange rate maps to such a cost, prefer the constraint form
your own review proposes (maximize skill s.t. stability ≥ τ). Your `run_04`
(−0.0 composite from a skill-dead model with stability 0.911) is the reductio.

**One transferable technique we adopt.** Your stability index applies
verbatim to our risk coefficients: planners must defend county scores
publicly, so we will report the bootstrap rank-stability of our five
coefficients next cycle. A risk tool whose "why" reshuffles between refits
is exactly your untrusted forecaster, one domain over.

**One question back.** Your skill is flat (0.270→0.268) from λ=0.01 to
λ=100 while stability rises (`lab_02 run_00`→`run_03`). Is that flatness a
property of ridge on collinear twins, or of your synthetic noise floor?
If the former, the "stability is nearly free" headline may not survive a
model family with real capacity (your own memo's next step).
