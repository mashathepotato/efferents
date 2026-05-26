# efferents

> *Each lab is an efferent channel — emitting its outgoing signals (papers, claims, corroborations) into the network of labs.*

**Status: scaffold.** Migrated from the [auto-qml](https://github.com/mashathepotato/auto-qml) reference lab on 2026-05-26. Framework abstractions need decoupling from QML before this is usable as a generic library. See [`CLAUDE.md`](./CLAUDE.md) for the next-session handoff and [`context/journal_vision.md`](./context/journal_vision.md) for the long-term design.

## What this is

A framework for running **autonomous research labs**:

- A *lab* is a continuously-running multi-agent loop that frames falsifiable hypotheses, runs experiments, drafts papers, and publishes them.
- Each lab is owned by a human PI but operates without per-cycle human input.
- Many labs across topics submit to shared **venues** — thematic publication streams that act as the multi-lab equivalent of a workshop or journal.
- Inter-lab dynamics (corroboration, challenge, citation) are pure agent-to-agent.

The framework provides the loop, the budget discipline, the falsifiability gate (via [popper-probe](https://github.com/mashathepotato/popper-probe)), the campaign / paper machinery, and the progress dashboard. The lab user provides the domain — data, model, evals, prompts.

## Repository status

This repo was scaffolded by copying the framework-relevant subset of auto-qml (the *reference lab*), renaming imports, and stubbing out QML-specific identity into an abstract `lab.py`. The code is **not yet runnable as a generic framework** — see CLAUDE.md for the work remaining.

## Layout

```
efferents/
├── efferents/                 # the framework package
│   ├── __init__.py
│   ├── lab.py                 # abstract lab identity (override per-lab)
│   ├── agents/                # the multi-role agent system
│   │   ├── orchestrator.py    # the 24/7 loop
│   │   ├── budget.py          # cost discipline + cache hit tracking
│   │   ├── state.py           # file-based state primitives (SQLite + JSONL + md)
│   │   ├── researcher.py      # student↔supervisor dialogue, modes, campaigns
│   │   ├── coder.py           # autonomous source-code modification
│   │   ├── analyst.py         # periodic digest + flat-improvement counter
│   │   ├── writer.py          # paper composition, novelty/gain gate, peer review
│   │   ├── librarian.py       # lit-review subagent
│   │   ├── popper_gate.py     # headless popper-probe intake
│   │   ├── progress.py        # self-contained HTML dashboard
│   │   ├── notify.py          # macOS notification + ntfy.sh
│   │   ├── __main__.py        # CLI entry: start, propose-once, digest-now, write-once, progress-now, ...
│   │   └── prompts/           # per-agent prompts (currently QML-flavored; templates needed)
│   ├── schemas/
│   │   └── paper_frontmatter.py   # pydantic Paper bundle schema
│   └── migrations/
│       └── runner.py          # idempotent SQLite schema migration
├── tests/                     # generic unit tests (62/65 from auto-qml carry over)
├── docs/
│   ├── superpowers/specs/     # phase A lab-foundation spec
│   ├── superpowers/plans/     # phase A implementation plan (TDD)
│   └── templates/             # qml-lab.py.example — concrete lab config to copy from
├── context/
│   └── journal_vision.md      # the long-term multi-lab journal design
├── pyproject.toml
└── README.md
```

## Reference lab

[auto-qml](https://github.com/mashathepotato/auto-qml) is the first concrete lab built on these abstractions (before they were a framework). It runs quantum-conditioned diffusion experiments on HEP jet data. It currently still imports its framework pieces in-tree; once `efferents` is published, auto-qml will `pip install efferents` and shed those.

## Related projects

- [popper-probe](https://github.com/mashathepotato/popper-probe) — adversarial Popperian hypothesis intake. Required as a subprocess by `efferents.agents.popper_gate`. Repo path resolved via `POPPER_PROBE_REPO` env var (default `~/Documents/popper-probe`).

## Next steps (next Claude session)

See `CLAUDE.md`.
