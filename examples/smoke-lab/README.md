# smoke-lab

A trivial example lab that exercises the efferents framework end-to-end
without GPU, real data, or real research.

## What it proves

- LabConfig loads from a non-QML `lab.yaml`
- Coder modifies code under a non-`auto_qml` source dir
- Run command emits stdout JSON; daemon ingests the row
- Progress dashboard renders against a custom headline metric (`synthetic_loss`)
- A full Researcher → Coder → smoke → run → analyst cycle completes in seconds

## Running locally

```bash
efferents validate --submission examples/smoke-lab/
efferents start    --submission examples/smoke-lab/
```

(Foreground; press Ctrl-C to stop.)

For the end-to-end test variant, run: `pytest -m integration tests/integration/`.

## Caveat

The agent prompts (researcher.md, coder.md, etc) are still calibrated for the
QML reference lab. The Researcher's suggestions may read oddly. This is a
known limitation — see [`docs/superpowers/specs/2026-05-26-efferents-deployment-design.md`](../../docs/superpowers/specs/2026-05-26-efferents-deployment-design.md)
Section 5 "Out of scope".
