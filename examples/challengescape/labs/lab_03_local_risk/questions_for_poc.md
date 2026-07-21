# Questions for the challenge point of contact — Lab 03

1. **What is the decision unit for adaptation planning** — county, census
   tract, watershed? Our synthetic records are county-shaped; FEMA NRI is the
   obvious public substitute, but the right granularity decides everything.
2. **What is the real cost ratio of a miss vs. a false flag?** We tuned the
   positive-class weight for F1; if you can tell us the actual asymmetry, the
   lab optimizes the right objective instead of a symmetric proxy.
3. **How much history should a risk feature carry?** Our revised plan adds a
   rolling storm-trend feature (adopted from the sibling early-warning lab).
   Is trend-in-hazard genuinely predictive at planning granularity, or does
   exposure dominate?
4. **Whose scrutiny must the tool survive?** If planners must defend the
   scores publicly, coefficient stability (the sibling forecast lab's index)
   may matter as much as F1. True in your experience?
5. **Is there a public dataset you consider the credibility bar** for this
   challenge — the one a demo must run on before you'd take it seriously?
