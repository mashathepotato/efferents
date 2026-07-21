# Challenge: tipping-point early warning

> **"Climate systems cannot be monitored early enough to anticipate tipping
> transitions"** — [Encode Challengescape](https://encode-challengescape.pillar.vc/),
> Climate domain.

- **Source**: Encode: AI for Science Challengescape (Pillar VC / ARIA). Title
  quoted verbatim from the public challenge map.
- **Point of contact**: listed on the challenge card at the Challengescape
  site. <!-- TODO: capture name/affiliation manually from the site before outreach -->
- **Domain**: climate dynamics / early-warning signals.

## The bottleneck, as this lab frames it

Tipping elements (AMOC, ice sheets, ecosystems) show *critical slowing down*
before transition: rising lag-1 autocorrelation and variance. The open problem
is not whether these indicators exist but whether they fire **early enough,
at a false-alarm rate an operator can live with**. Every estimation window
trades statistical power against lag — and nobody publishes that tradeoff
curve for their detector.

## What this autonomous lab does first

Sweeps the rolling-window length of a lag-1 autocorrelation alarm on a
deterministic synthetic ensemble with known transition time, holding the
control-series false-alarm rate at ~5%, and measures **mean detection lead
time**. Baseline: classic Dakos-style rolling indicators. This is deliberately
the simplest credible baseline — the point is the runnable, provenance-tracked
loop around it.

- **Dataset**: seeded synthetic AR(1) ensemble with critical slowing down
  (`datagen.py`). Public follow-up: RAPID-array AMOC transports, paleoclimate
  proxy records.
- **Metric**: `mean_lead_time` (timesteps before known transition; missed
  transition = 0), with `control_false_alarm_rate` reported alongside.

## What it learned from / contributes to the shared journal

- **From Lab 2**: an attribution/indicator *stability* lens — is the window
  choice itself stable under ensemble resampling?
- **From Lab 3**: what lead time is *actionable* — a warning nobody can act on
  is a metric, not a tool.
- **Contributes**: the lead-time-vs-window tradeoff curve, and the structural
  ceiling result (a window of length w cannot alarm before t=w), which
  transfers to any windowed early-warning indicator — including Lab 3's
  planned storm-trend feature.
