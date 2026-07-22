# Challengescape × efferents — three interconnected autonomous labs

[Encode's Challengescape](https://encode-challengescape.pillar.vc/) maps open
scientific problems. This example turns three related climate challenges into
three local autonomous research labs that ran overnight, each producing a
provenance-tracked lab journal — and then **cross-reviewed each other's
results through a shared journal**, with one lab revising its next experiment
because of another lab's finding.

**Start here → [`shared_journal/index.md`](shared_journal/index.md)**

## What is real here

Every experiment, metric, and run record was produced by `efferents run`
executing each lab's own train/eval commands — offline, deterministic, no API
key. Hypothesis framing, reviewer notes, and cross-lab reviews were written
by an LLM agent pass grounded in those recorded runs; every quantitative
claim cites a `run_id`. Nothing here is a scientific result. It is a
demonstration of autonomous research memory, review, and inter-lab transfer
on real challenge framings.

## The three labs

| lab | challenge (verbatim from Challengescape) | headline metric |
|-----|------------------------------------------|-----------------|
| [lab_01](labs/lab_01_tipping_early_warning/challenge.md) | "Climate systems cannot be monitored early enough to anticipate tipping transitions and direct timely adaptation." | detection lead time at fixed false-alarm rate |
| [lab_02](labs/lab_02_forecast_trust/challenge.md) | "AI weather models are accurate but uninterpretable and untrusted by forecasters and policymakers." | forecast skill × attribution stability |
| [lab_03](labs/lab_03_local_risk/challenge.md) | "Communities lack granular climate-risk tools to plan adaptation and resilient infrastructure." | F1 on the rare high-risk class |

They share a data modality (climate time series / tabular records), a
bottleneck (models exist; trust and actionability don't), and an evaluation
pattern (lead time / skill / operating-point tradeoffs) — which is what makes
the cross-review meaningful rather than decorative.

## The inter-lab loop (the actual point)

1. Each lab ran a bounded sweep via `efferents run` → `journal/001–004`,
   `runs.jsonl`, `claims.jsonl`, `dashboard.html`.
2. An agent review pass wrote `005_review.md` per lab — real objections,
   each verified against the run logs.
3. Labs cross-reviewed each other (`shared_journal/reviews/`): one critique
   through the reviewer's lens, one transferable technique, one concrete
   suggestion.
4. **Lab 03 withdrew its planned next experiment and adopted Lab 01's
   storm-trend suggestion with ceiling-aware bounds** —
   [`006_next_experiment_v2.md`](labs/lab_03_local_risk/out/journal/006_next_experiment_v2.md).

## Reproduce it

```bash
# from the efferents repo root, venv built (see repo README)
examples/challengescape/launch_overnight.sh
```

## Watch it live

```bash
.venv/bin/python examples/challengescape/live.py   # http://127.0.0.1:8890/
```

A local page that polls the labs' `out/` directories every 2 seconds: per-lab
status, run tables, and metric-vs-parameter charts update in place while
`launch_overnight.sh` (or a real overnight run) executes. Read-only and fully
local — start it in one terminal, launch the labs in another.

Reruns regenerate every run record and journal entry 001–004 with identical
metrics (fixed seeds; timestamps will differ). The review layer (005/006 and
`shared_journal/reviews/`) is the recorded agent pass — the prompts that
produced it are in [`prompts/`](prompts/), so it can be re-run or extended.

## Adapt it to your challenge

Copy [`templates/`](templates/) into a new `labs/lab_NN_<slug>/`, point the
`efferents.yaml` at your own train/eval commands (the contract:
`train` prints `{"checkpoint": ...}`, `eval` prints `{"metrics": {...}}`),
and add the lab to `launch_overnight.sh`'s loop. Each lab also keeps a
[`questions_for_poc.md`](labs/lab_01_tipping_early_warning/questions_for_poc.md)
— the questions an autonomous baseline *should* raise for the human who owns
the problem.
