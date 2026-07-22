---
submission: sub-003-03
round: 1
reviewer: critical
score: 3
recommendation: reject
agent: llm-review-pass (claude-fable-5), critical persona
grounded_in: [manuscript_v1.md, labs/lab_03_local_risk/out/runs.jsonl]
---

# Critical review (r1): the headline claim is unresolvable by design

The paper is honest — unusually so — about its own weakness, but honesty does
not convert an unresolvable result into a publishable one.

1. **The primary gain fails the venue gate and the paper knows it.** +1.8%
   over baseline (0.7692 vs 0.7556, `run_02` vs `run_01`) against a 5% gate,
   and the Conclusion concedes the margin is "one flipped prediction at 23
   held-out positives." A sweep whose winner is statistically inseparable
   from its neighbor cannot anchor a paper whose title is about the optimum.
2. **The synthetic label is linear in the features**, so logistic regression
   is well-specified by construction. Even the tradeoff surface's *shape*
   carries a favorable bias a real risk index will not extend.
3. The genuinely useful piece — flag-count as a first-class planner-facing
   quantity — is a reporting convention, not yet a result.

The lab's own revised plan (enlarge the eval ensemble; add the storm-trend
feature adopted from lab_01) is the paper this should have been. Reject and
resubmit after that cycle runs.

## Requested revisions

- Resubmit after the enlarged-ensemble + storm-trend experiment; the current
  data cannot support an optimum claim at any revision depth.
