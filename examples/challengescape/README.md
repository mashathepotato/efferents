# Challengescape × efferents — multi-topic autonomous labs

Self-contained example of running a small **network of autonomous research
labs** on topics from [Encode's Challengescape](https://encode-challengescape.pillar.vc/)
(or any other source of open problems). Restarted 2026-07-24 with the full
front door in place; labs appear here as topics are deployed.

## The lifecycle every topic goes through

1. **Popper probe with the funder.** Each new topic is probed interactively
   with the human who directs the labs — the agent does not self-play the
   dialogue. The gate produces a falsifiable `hypothesis.md`, and the
   dialogue's design decisions plus the funder's verbatim initial direction
   are recorded in the lab charter (`context/popper.md` — living guidance,
   not rules; see [`templates/popper.md`](templates/popper.md)).
2. **Placement.** `efferents place` compares the probed topic + approach
   against the existing labs. Same topic *and* same way of thinking →
   redundant: the newcomer is **hired into the existing lab as a new PhD
   student** (roster + charter entry). New topic, or a genuinely different
   way of thinking about an old one → a new lab is founded.
3. **Bounded experiments** via the repo-adapter contract (`efferents run`):
   deterministic, offline-runnable, every claim resolving to a run record.
4. **Shared journal + venue.** Labs cross-review through
   [`shared_journal/`](shared_journal/) ([`crosslab.py`](crosslab.py)) and
   submit methodology-reproducible manuscripts to the
   [`venue/`](venue/venue.py): board review, revision rounds, deterministic
   decisions, and mechanical reproduction (`venue.py reproduce` re-executes
   a paper's recipe) before any lab builds on another's result.
5. **Watch it live:** `.venv/bin/python examples/challengescape/live.py`
   → http://127.0.0.1:8890/ — lab drill-down, agent pipelines, network map,
   venue panel, and a submit-a-new-lab entry point.

## UI contract

Challengescape uses the same research-lab visual system as the core local
workspace. [`live.py`](live.py) embeds the canonical stylesheet through
`efferents.dashboard.theme.embed_research_theme`; the per-lab
`out/dashboard.html` files use `efferents.dashboard.report_theme.REPORT_CSS`.

Do not add a bespoke dashboard or a second inline palette for a challenge.
Extend the shared components and tokens instead. Light mode is the default;
dark mode is an explicit remembered choice. `tests/test_research_theme.py`
fails if a Python example HTML app bypasses this contract.

## What is real here

Experiments, metrics, and provenance are produced by `efferents run` and are
reproducible offline (`launch_overnight.sh`). Hypothesis framing, reviews,
and cross-lab reviews are agent passes grounded in the recorded runs; every
quantitative claim cites a run_id. Nothing here is a scientific result — it
is a demonstration of autonomous research memory, review, placement, and
inter-lab transfer on real challenge framings.

## For a real user

This directory is self-contained for demonstration. A real user starts from
the [efferents README](../../README.md) in their **own** repo: the one-line
agent instruction there leads through `intake.md` — installation, the
interactive popper probe, charter, lab configuration, and a bounded first
cycle — with the same lifecycle this example exercises.
