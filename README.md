# efferents

**Turn your ML repo into a local autonomous research lab.**

efferents runs bounded experiments on *your* compute and writes reviewed
internal research memos — with provenance — into a local lab journal. It frames
a falsifiable hypothesis, plans an experiment, runs it against your own
train/eval commands, and records every result claim back to a run, a metric, or
a code diff.

> Not a chatbot and not a public paper generator. The point is **private,
> reproducible, budgeted experiment loops** and a **research memory** your team
> actually trusts.

## Who it's for

ML / R&D teams who run a lot of internal experiments and want an agent that
explores the parameter/idea space overnight — **without** shipping code, data,
or results to a third party, and **without** producing unverifiable prose. Every
nontrivial claim in a memo points at evidence.

## Why local-first

- **Your compute, your data.** Experiments run via commands you define
  (`train.py`, `eval.py`). Nothing leaves the machine except the LLM calls you
  opt into — and the offline demo makes none.
- **Reproducible memos.** Outputs are plain Markdown + JSONL (`runs.jsonl`,
  `claims.jsonl`) you can diff, grep, and check into a repo.
- **Provenance by construction.** Each result claim resolves to a `run_id`, a
  metric file, a log, or a code diff — not a vibe.
- **Budgeted.** Hard ceilings on GPU hours and LLM spend; an approval mode that
  plans before it executes.

## 60-second quickstart (no API key needed)

```bash
git clone https://github.com/mashathepotato/efferents && cd efferents
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e .
.venv/bin/efferents demo smoke-lab        # or: python -m efferents demo smoke-lab
open efferents-demo/dashboard.html
```

This runs a bounded, **fully offline, deterministic** experiment loop on a toy
synthetic task and writes a complete lab journal:

```
efferents-demo/
├── journal/
│   ├── 001_hypothesis.md        # framed, falsifiability-gated claim
│   ├── 002_experiment_plan.md   # plan recorded before any run executes
│   ├── 003_results.md           # run table, best run, reading
│   └── 004_reviewed_memo.md     # reviewed memo + evidence table
├── runs.jsonl                   # one line per experiment run
├── claims.jsonl                 # each claim → run_id / metric / source
└── dashboard.html               # static dashboard of the above
```

The agent reasoning in the demo is deterministic and offline; the *experiment*
is real (it executes the lab's run command and records the actual metric).

### Example output — the reviewed memo

Every memo carries: **Summary · Hypothesis · Experiment plan · Results ·
Reviewer notes · Limitations · Next experiment · Evidence table.** The evidence
table is the contract:

| claim | evidence_type | source_path | run_id | metric |
|-------|---------------|-------------|--------|--------|
| synthetic_loss is minimized near coefficient 0.81 | run_metric | `logs/run_004_081.log` | `run_004_081` | synthetic_loss |
| Best run beats the 0.05 falsifier threshold | run_metric | `runs.jsonl` | `run_004_081` | synthetic_loss |
| Runs inside (0.75, 0.85) all stay below threshold | metric_aggregate | `runs.jsonl` | — | synthetic_loss |

## Point it at your own repo

Drop an `efferents.yaml` at your ML repo root
([full example](examples/repo-adapter/efferents.yaml)):

```yaml
goal: "improve validation F1 under 2 GPU hours"
train_command: "python train.py --config configs/base.yaml"
eval_command: "python eval.py --checkpoint {checkpoint}"
metric: "val_f1"
maximize: true
budget:
  max_gpu_hours: 2
  max_llm_cost_usd: 20
approval:
  mode: "plan_then_execute"
```

## Safety, budget & approval

- **Approval modes:** `plan_then_execute` (default — the plan is written to the
  journal before anything runs), `dry_run` (plan only), `autonomous` (sandbox
  use only).
- **Budget ceilings:** the lab halts before exceeding `max_gpu_hours` or
  `max_llm_cost_usd`. The live agent loop routes every model call through a
  budget accountant (Sonnet by default; Opus only where it earns it).
- **Read-only dashboard:** `efferents serve --lab-root <lab>` visualizes a lab
  without ever mutating its state.
- **Falsifiability gate:** a hypothesis must pass an adversarial
  [popper-probe](https://github.com/mashathepotato/popper-probe) dialogue before
  the lab will spend compute on it.

## Running a live lab (needs an API key)

```bash
cp .env.example .env        # add ANTHROPIC_API_KEY
efferents validate --submission examples/smoke-lab/
efferents start    --submission examples/smoke-lab/
efferents serve    --lab-root  examples/smoke-lab/lab   # read-only dashboard
```

See [`intake.md`](./intake.md) for the guided "point it at a fresh idea" flow.

## Status & design partners

efferents is **early and honest about it**: the offline demo and the
local CLI (`validate / start / status / serve`) work today; the live multi-agent
loop runs but its prompts are still maturing. The lab-agnostic config layer
(`LabConfig`, the repo adapter) is in place; broader domain coverage is in
progress.

**Looking for design partners.** If you run internal ML experiments and want an
autonomous lab on your own hardware, we'd like to build with you.
📧 alina.nesen@gmail.com · or open an issue.

## More

- [`DEVELOPMENT.md`](./DEVELOPMENT.md) — architecture, package layout, the
  multi-lab vision, and the QML reference-lab history.
- [`examples/smoke-lab/`](./examples/smoke-lab/) — a complete non-toy-domain lab.
- [`context/journal_vision.md`](./context/journal_vision.md) — the long-term
  multi-lab journal design.

## License

[Apache-2.0](./LICENSE). © 2026 Masha Baidachna. You can clone, modify, and use
efferents — including internally and commercially — under the terms of the
license.
