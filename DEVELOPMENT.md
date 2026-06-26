# Development & architecture

Internal notes for contributors. Buyer-facing copy lives in [`README.md`](./README.md).

> *Each lab is an efferent channel — emitting its outgoing signals (papers,
> claims, corroborations) into a network of labs.*

## Maturity

What works today:
- **Offline demo** (`efferents demo`) — deterministic, no API calls.
- **CLI** — `validate / start / status / stop / list / serve`.
- **`LabConfig`** — loads a lab from `lab.yaml` + `hypothesis.md`, lab-agnostic.
- **Repo adapter** — `efferents.yaml` loader for pointing at an existing repo.
- **Read-only dashboard** — `efferents serve`.
- **Tests** — see `tests/` (run `uv run pytest tests/`).

In progress: the live multi-agent loop runs but several agent prompts are still
calibrated against the original QML reference lab and read oddly in other
domains; broader domain coverage and prompt templating are ongoing.

## Package layout

```
efferents/
├── efferents/                 # the framework package
│   ├── __main__.py            # `python -m efferents …` → cli.main
│   ├── cli.py                 # validate / start / status / stop / list / serve / demo
│   ├── demo.py                # offline deterministic product demo
│   ├── lab.py                 # LabConfig (lab.yaml + hypothesis.md loader)
│   ├── repo_adapter.py        # efferents.yaml ("bring your own repo") loader
│   ├── daemon.py              # foreground / detached run loop
│   ├── registry.py            # running-lab registry
│   ├── dashboard/             # read-only HTTP dashboard (server + reader)
│   ├── journal/               # paper/memo feed renderer
│   ├── migrations/            # idempotent SQLite schema migration
│   ├── schemas/               # pydantic paper-bundle schema
│   └── agents/                # the multi-role agent loop
│       ├── orchestrator.py    # the 24/7 loop
│       ├── budget.py          # cost discipline + cache-hit tracking
│       ├── state.py           # file-based state (SQLite + JSONL + md)
│       ├── researcher.py      # student↔supervisor dialogue, modes, campaigns
│       ├── coder.py           # autonomous source modification (scoped to source.dir)
│       ├── analyst.py         # periodic digest + flat-improvement counter
│       ├── writer.py          # memo composition, novelty/gain gate, peer review
│       ├── reviewer.py        # reviewer board
│       ├── librarian.py       # lit-review subagent
│       ├── popper_gate.py     # headless popper-probe intake
│       └── progress.py        # self-contained HTML dashboard
├── examples/
│   ├── smoke-lab/             # a complete non-QML example lab (stub executor)
│   └── repo-adapter/          # efferents.yaml example for an existing ML repo
├── web/landing/               # static marketing/landing site
├── tests/
└── docs/
    ├── superpowers/specs/     # design specs
    ├── superpowers/plans/     # implementation plans
    └── templates/             # qml-lab.py.example (historical reference)
```

## Two config layers

1. **`efferents.yaml` (repo adapter)** — the buyer front door. A flat config at
   an ML repo root: goal, train/eval commands, metric, budget, approval. Loaded
   by `efferents.repo_adapter.RepoAdapterConfig`.
2. **`lab.yaml` + `hypothesis.md` (submission)** — the lower-level lab schema the
   daemon consumes directly. Loaded by `efferents.lab.LabConfig.from_submission`.
   The smoke lab and the `intake.md` trial use this layer.

## How a lab runs

One YAML config = one run. The framework hands the lab's executor a config path;
the executor produces a SQLite/JSONL row with metrics. State is file-based (no DB
server): lab state under `lab/`, popper hypotheses under `popper-corpus/`. Every
Anthropic call goes through `efferents.agents.budget` (Sonnet default; Opus on
the Analyst and on Researcher escalation).

## The offline demo

`efferents/demo.py` fakes the *agent reasoning* with deterministic text but runs
the lab's *real* run command over a small parameter sweep, recording the actual
metric each run emits (with an analytic fallback so a fresh clone never
hard-fails). It exists for product comprehension and to exercise the
journal/runs/claims/dashboard artifact shape without a paid API.

## The multi-lab vision (forward design)

The long-term destination is a platform where many autonomous labs publish to
shared **venues** and interact (corroborate, challenge, cite) agent-to-agent,
hosted at `efferents.com`. That is **out of scope** for the framework package —
see [`context/journal_vision.md`](./context/journal_vision.md). Build the
single-lab library first.

## History: the QML reference lab

efferents was extracted on 2026-05-26 from
[auto-qml](https://github.com/mashathepotato/auto-qml), a lab running
quantum-conditioned diffusion experiments on HEP jet data. The framework-relevant
subset was copied out and decoupled from QML specifics into `LabConfig`. Some
agent prompts still carry QML phrasing; `docs/templates/qml-lab.py.example` is a
historical reference for how that lab parameterized the framework. Do **not**
re-introduce `auto_qml` imports.

## Related projects

- [popper-probe](https://github.com/mashathepotato/popper-probe) — adversarial
  Popperian hypothesis intake; required as a subprocess by
  `efferents.agents.popper_gate`. Path via `POPPER_PROBE_REPO`
  (default `~/Documents/popper-probe`).
</content>
