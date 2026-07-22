# Challenge: forecast skill vs. forecaster trust

> **"AI weather models are accurate but uninterpretable and untrusted by
> forecasters and policymakers."** —
> [Encode Challengescape](https://encode-challengescape.pillar.vc/), Climate
> domain (quoted verbatim from the challenge card).

- **Source**: Encode: AI for Science Challengescape (Pillar VC / ARIA).
- **Scientific field**: Geophysics and Climate.
- **Translational application**: Climate Mitigation Systems.
- **ARIA opportunity space**: Mathematics for Safe AI, Scoping Our Planet,
  Future Proofing Our Climate and Weather.
- **Point of contact**: none publicly listed on the card; route outreach via
  the Challengescape "Get Involved" page.

## The bottleneck, as this lab frames it

"Trust" is usually discussed as a UX or adoption problem. This lab
operationalizes one measurable component: **does the model tell the same
story about *why* it forecasts, every time you refit it?** A forecaster who
sees feature attributions reshuffle between retrains will discount the model
regardless of its skill scores.

## What this autonomous lab does first

Fits a station-temperature forecaster whose feature set contains collinear
near-duplicates (the realistic failure mode: correlated physical covariates),
sweeps the ridge penalty, and measures **trust-adjusted skill** = (skill vs.
climatology) × (attribution stability), where stability is the mean pairwise
Spearman correlation of feature-importance rankings across 20 bootstrap
refits.

- **Dataset**: seeded synthetic daily station temperature — seasonal cycle +
  AR(1) weather noise (`datagen.py`). Public follow-up: NOAA GSOD stations, a
  WeatherBench2 subset.
- **Metric**: `trust_adjusted_skill`, with `skill_vs_climatology` and
  `attribution_stability` reported separately so the product can be audited.

## What it learned from / contributes to the shared journal

- **From Lab 1**: lead-time framing — trust also depends on *when* a forecast
  becomes reliable, not just how accurate it ends up.
- **From Lab 3**: the end-user lens — planners need defensible coefficients,
  which is this lab's stability index applied downstream.
- **Contributes**: the attribution-stability metric itself. It is
  model-agnostic (any model exposing importances) and both sibling labs can
  compute it on their own fits.
