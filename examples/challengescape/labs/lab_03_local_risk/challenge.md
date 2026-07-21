# Challenge: granular local climate-risk tools

> **"Communities lack granular climate-risk tools to plan adaptation"**
> — [Encode Challengescape](https://encode-challengescape.pillar.vc/),
> Climate domain.

- **Source**: Encode: AI for Science Challengescape (Pillar VC / ARIA). Title
  quoted verbatim from the public challenge map.
- **Point of contact**: listed on the challenge card at the Challengescape
  site. <!-- TODO: capture name/affiliation manually from the site before outreach -->
- **Domain**: climate adaptation, tabular risk modeling.

## The bottleneck, as this lab frames it

Granular risk tools fail in one of two ways: they miss high-risk communities
(rare-class recall) or they flag so many places that planners ignore them
(precision collapse). That is a class-imbalance tuning problem before it is a
data problem — and the operating point deserves an auditable justification.

## What this autonomous lab does first

Fits a weighted logistic-regression classifier over county-level features
(coastal exposure, elevation, storm rate, drainage, population density),
sweeps the positive-class weight, and measures **F1 on the high-risk class**,
with precision/recall and flagged-count reported so the tradeoff is visible.

- **Dataset**: seeded synthetic county records with ~15% high-risk prevalence
  (`datagen.py`). Public follow-up: FEMA National Risk Index, NOAA Storm
  Events (both public CSV).
- **Metric**: `f1_high_risk`, with `precision_high_risk`, `recall_high_risk`,
  and `n_flagged` alongside.

## What it learned from / contributes to the shared journal

- **From Lab 1**: its features are static snapshots; Lab 1's early-warning
  result motivates a *temporal* storm-trend feature — adopted in this lab's
  revised next-experiment plan (`out/journal/006_next_experiment_v2.md`).
- **From Lab 2**: the attribution-stability index as an audit for the risk
  coefficients planners must defend publicly.
- **Contributes**: the actionability lens — flagged-count as a first-class
  reported quantity, which reframes both siblings' alarms and forecasts as
  decisions with a cost.
