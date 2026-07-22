---
submission: sub-002-02
round: 1
reviewer: critical
score: 5
recommendation: major_revision
agent: llm-review-pass (claude-fable-5), critical persona
grounded_in: [manuscript_v1.md, labs/lab_02_forecast_trust/out/runs.jsonl]
---

# Critical review (r1): the headline metric is indefensible as submitted

The underlying finding is real and well-evidenced — skill flat 0.270→0.268
while stability climbs 0.756→0.890, then collapse at λ=1000 (`run_00`,
`run_03`, `run_04` all re-verified). But the paper's headline metric
undermines its own conclusion:

1. **skill × stability encodes an exchange rate nobody defended.** The paper
   itself concedes the product yields a degenerate −0.0 at λ=1000 and that
   stability "must be read jointly with skill, never alone" — which is an
   argument against publishing the product as the optimized headline. The
   +13.5% delta_vs_baseline in the frontmatter is a delta *in the composite*,
   and inherits its arbitrariness.
2. **The instability is partly engineered** (collinear twins injected at
   noise sd 0.05). The mechanism is demonstrated; its magnitude is a design
   choice. The paper must say which claims survive if real covariates are
   less collinear.
3. **Stability is measured on global |coef| rankings over training
   bootstraps.** The trust problem cited in Motivation is per-forecast. The
   title claim should be scoped accordingly.

## Requested revisions

- Replace the headline with the constraint form (max skill s.t. stability ≥
  τ) or justify the product; report both components in the main table either
  way.
- Add a sensitivity note on the engineered collinearity (vary the twin noise
  or state the scope limitation explicitly in Results).
- Scope the claim to global attribution stability in title or Conclusion.
