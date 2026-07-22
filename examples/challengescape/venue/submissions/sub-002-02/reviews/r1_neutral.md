---
submission: sub-002-02
round: 1
reviewer: neutral
score: 6
recommendation: major_revision
agent: llm-review-pass (claude-fable-5), neutral persona
grounded_in: [manuscript_v1.md, labs/lab_02_forecast_trust/out/runs.jsonl]
---

# Neutral review (r1): strong mechanism, wrong optimization target

Reproducibility is exemplary: Methods are self-sufficient (exact normal
equations, standardization, B=20 bootstrap Spearman — all reimplementable
from prose), and the recipe pins all five runs. The stability-is-nearly-free
mechanism is the publishable core and is cleanly evidenced.

However, the optimized quantity and the claimed quantity diverge. The
frontmatter's primary metric_provenance entry is the composite (0.2386,
+13.5%), while the Conclusion argues the composite is misleading at the
boundary. A venue paper should optimize what it defends. The fix is
structural (choose the headline, restate the delta against it), hence major
rather than minor.

## Requested revisions

- Make the defended quantity the primary metric_provenance entry and restate
  delta_vs_baseline against it.
- Main results table with skill, stability, and composite as columns per λ.
