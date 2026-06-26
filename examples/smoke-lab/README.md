# smoke-lab

A trivial example lab that exercises the efferents framework end-to-end
without GPU, real data, or real research.

## What it proves

- LabConfig loads from a non-QML `lab.yaml`
- Coder modifies code under a non-`auto_qml` source dir
- Run command emits stdout JSON; daemon ingests the row
- Progress dashboard renders against a custom headline metric (`synthetic_loss`)
- A full Researcher → Coder → smoke → run → analyst cycle completes in seconds

## Offline demo (no API key)

```bash
efferents demo smoke-lab        # writes ./efferents-demo/
open efferents-demo/dashboard.html
```

Runs a bounded, deterministic experiment loop and writes a full lab journal
(hypothesis → plan → results → reviewed memo), `runs.jsonl`, `claims.jsonl`, and
a static dashboard — with no Anthropic call.

## Running the live lab (needs ANTHROPIC_API_KEY)

```bash
efferents validate --submission examples/smoke-lab/
efferents start    --submission examples/smoke-lab/
```

(Foreground; press Ctrl-C to stop.)

For the end-to-end test variant, run: `pytest -m integration tests/integration/`.

## Known limitation

The live agent prompts (researcher.md, coder.md, …) still carry phrasing from the
original QML reference lab, so the Researcher's suggestions can read oddly in this
synthetic domain. Prompt templating is in progress — see [`DEVELOPMENT.md`](../../DEVELOPMENT.md).
The offline demo above is unaffected.
