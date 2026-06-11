# Local cold-start trial via `intake.md`

**Date:** 2026-06-11
**Status:** approved design, pre-implementation

## Summary

Enable a real end-to-end trial of efferents that mimics a brand-new user who has
nothing installed but Claude Code. The user opens a fresh terminal in an empty
project directory and pastes a single **instruction pointer**:

```
Read https://raw.githubusercontent.com/mashathepotato/efferents/main/intake.md and follow it
```

Their agent fetches `intake.md` and follows it: install efferents, run
popper-probe in the terminal to produce a falsifiable hypothesis, scaffold a
disposable trial, run one bounded trial, and open the read-only dashboard to
watch it. This is the local, runnable version of the moltbook-shaped intake
contract from `2026-05-26-efferents-deployment-design.md` (which deferred
hosting to Phase B).

This is **model A**, unchanged: popper-probe and launching happen in the
terminal/agent; the UI (`efferents serve`, built in
`2026-06-11-efferents-web-surfaces-design.md`) stays read-only and just displays
the result.

## Goals

- A fresh Claude Code agent, given only the pointer, can go from nothing to a
  running trial visible on the dashboard.
- The trial exercises the real pipeline: popper-probe → hypothesis → bounded
  orchestrator run → dashboard.
- Everything trial-specific is **disposable** and lives in the user's throwaway
  project directory. The only artifact added to the efferents repo is
  `intake.md`. `efferents/` and the landing page are untouched.

## Non-goals

- No changes to the `efferents/` package (no new CLI command, no orchestrator
  changes). The bounded-run logic lives in the disposable `run_trial.py`, not the
  framework.
- No network/graph visualization (deferred; see "Future work").
- No UI controls — the dashboard remains read-only.
- No hosted `efferents.com`. The pointer is a GitHub raw URL.
- The default trial is **synthetic** (stub executor): it demonstrates the
  plumbing, it does not truly test the user's claim. The user may swap in a real
  executor after seeing their hypothesis.

## Verified preconditions (2026-06-11)

- The GitHub repo `mashathepotato/efferents` is public and reachable
  (`raw.githubusercontent.com/.../efferents/dashboard/server.py` → 200).
- `origin/main` already contains the merged web-surfaces work (`193f74b`).
- The dashboard static files (`efferents/dashboard/static/*.{html,css,js}`) are
  git-tracked inside the `efferents` package, so flit ships them in the wheel.
  (The plan verifies this with a clean-venv install.)
- popper-probe is present on this machine: the `popper-probe:intake` skill is
  installed as a Claude Code plugin and the repo is at `~/Documents/popper-probe`
  (so the orchestrator's `popper_gate`, which defaults `POPPER_PROBE_REPO` to
  that path, also works).
- `ANTHROPIC_API_KEY` is set in the environment.
- **Missing:** `intake.md` — created and pushed by this work.

## Architecture

One committed file (`intake.md`) plus a disposable kit it scaffolds into the
user's project dir at follow time.

```
efferents repo (committed):
  intake.md                       # the cold-start contract (the only addition)

user's empty project dir (created by the agent following intake.md; disposable):
  .venv/                          # pip install target
  hypothesis.md                   # popper-probe output (then copied into submission/)
  executor/
    stub_run.py                   # placeholder executor (copy of smoke-lab stub)
  configs/
    default.yaml                  # config template (copy of smoke-lab's)
  submission/
    hypothesis.md                 # copied here
    lab.yaml                      # executor defaults to ./executor stub; user edits
    lab/                          # created at runtime; the dashboard reads this
    context/                      # created by _init_lab_root
  run_trial.py                    # bounded runner (the only logic)
```

### `intake.md` (the contract)

Terse, for-agent, numbered steps. Markdown is the SDK; the trial kit file
contents are embedded as fenced code blocks the agent writes verbatim.

1. **Preflight.** Confirm `ANTHROPIC_API_KEY` is set; confirm the
   `popper-probe:intake` skill is available (it is a globally installed plugin).
   If the key is missing, stop and tell the user.
2. **Install.** Create a venv and
   `pip install git+https://github.com/mashathepotato/efferents.git`.
   Verify `efferents --help` lists `serve`.
3. **Falsifiability intake.** Invoke the `popper-probe:intake` skill on the
   user's claim. It runs the adversarial dialogue and writes a hypothesis with
   `falsifiability_gate: passed`. Save/copy it to `submission/hypothesis.md`.
4. **Scaffold the trial kit.** Write `executor/stub_run.py`,
   `configs/default.yaml`, `submission/lab.yaml`, and `run_trial.py` from the
   embedded code blocks. Note to the user: the executor defaults to the bundled
   stub (synthetic); they may swap in a real executor now that they have seen
   their hypothesis.
5. **Deploy a bounded trial.** `python run_trial.py`
   (env `TRIAL_MAX_ITERS`, default 3).
6. **Watch.** `efferents serve --lab-root submission/lab`; report the
   `http://localhost:8800` link. The dashboard shows the hypothesis, the trial
   run(s), the metric, and agent activity.
7. **Cleanup.** `rm -rf` the project dir when done.

### `submission/lab.yaml` (embedded; mirrors the smoke-lab)

```yaml
lab_id: trial
domain: synthetic
source:
  dir: ../executor/
  allowed_patterns: ["**/*.py", "**/*.yaml"]
executor:
  run_command: "python3 -m stub_run --config {config_path}"
  smoke_command: "python3 -m stub_run --config {config_path} --smoke"
  config_template: ../configs/default.yaml
  run_timeout_s: 60
metrics:
  headline: { column: synthetic_loss, direction: min }
  panels:
    - { column: synthetic_loss, label: "Loss" }
  flat_digest_epsilon: 0.005
budget:
  daily_cap_usd: 2.0
```

`source.dir` = `../executor/` — resolved relative to the dir holding `lab.yaml`
(`submission/`), so it points at the project-root `executor/` (sibling of
`submission/`), whose cwd has `stub_run` importable. `config_template` =
`../configs/default.yaml` is then resolved relative to `source.dir`
(`project/executor/`), giving the project-root `configs/default.yaml`.
`LabConfig.from_submission(submission)` thus validates real paths — no
`check_paths=False` needed; the scaffolded files exist.

### `executor/stub_run.py` and `configs/default.yaml` (embedded)

Verbatim copies of `examples/smoke-lab/src/stub_run.py` and
`examples/smoke-lab/configs/default.yaml`. The stub reads the config, computes a
synthetic `synthetic_loss` from a `coefficient`, and prints the result JSON the
framework's executor parses. (Exact contents captured in the implementation plan
from the smoke-lab originals.)

### `run_trial.py` (embedded; the only logic)

Mirrors `cli._cmd_start` minus the daemon, plus a bounded run:

```python
import os
from pathlib import Path

from efferents.lab import LabConfig
from efferents import lab as lab_mod
from efferents.cli import _init_lab_root
from efferents.agents.orchestrator import Orchestrator
from efferents.envfile import load_dotenv

HERE = Path(__file__).resolve().parent
SUB = HERE / "submission"
MAX_ITERS = int(os.environ.get("TRIAL_MAX_ITERS", "3"))

cfg = LabConfig.from_submission(SUB)
load_dotenv(SUB / ".env")  # optional; falls back to inherited env
lab_mod.set_config(cfg)
lab_root = SUB / "lab"
_init_lab_root(SUB, lab_root)
os.chdir(SUB)  # Orchestrator uses lab_dir/context_dir relative to cwd
Orchestrator(
    lab_dir="lab",
    context_dir="context",
    daily_cap_usd=cfg.budget.daily_cap_usd,
    dry_run=False,
    startup_message=f"trial for lab_id={cfg.lab_id}",
).run(max_iterations=MAX_ITERS)
print(f"\nTrial done. View it:\n  efferents serve --lab-root {lab_root}")
```

It only *uses* framework APIs (`LabConfig`, `_init_lab_root`, `Orchestrator`);
the bounded-run logic (`max_iterations`) stays here, not in the framework.

## Data flow

```
pointer (raw URL) → agent WebFetches intake.md
  → pip install git+… (efferents into project .venv)
  → popper-probe:intake skill → hypothesis.md
  → agent writes kit files from intake.md
  → run_trial.py → Orchestrator(max_iterations=N) → submission/lab/{runs.sqlite,state.json,lab_notebook.md,...}
  → efferents serve --lab-root submission/lab → browser @ localhost:8800
```

## Error handling

- Missing `ANTHROPIC_API_KEY` → intake.md step 1 stops with a clear message.
- popper-probe emits `falsifiability_gate: failed` → `from_submission` rejects it;
  intake.md instructs the user to re-run intake and sharpen the claim.
- `pip install` fails → intake.md notes the repo must be public/reachable and
  suggests checking network.
- A bounded run that produces no rows (e.g., researcher proposes nothing in N
  iterations) → the dashboard renders empty-but-valid panels (already handled by
  the reader); intake.md suggests raising `TRIAL_MAX_ITERS`.

## Testing / verification

The kit is disposable and not committed, so there are no committed unit tests for
it. Acceptance is the real end-to-end run. The plan includes these checks:

1. **Packaging check:** in a clean temp venv, `pip install` the local repo and
   confirm `efferents serve --help` works and the static files are present in the
   installed package (`importlib`/path check).
2. **Pointer check:** after pushing, confirm the raw `intake.md` URL returns 200.
3. **Dry kit check:** scaffold the kit in a temp dir and confirm
   `LabConfig.from_submission(submission)` loads (paths resolve), without running
   the full orchestrator.
4. **The live trial** itself (run by the user as the new-user simulation) is the
   final acceptance.

## Future work (out of scope)

- The network/graph visualization of labs with animated paper-flows along
  inter-lab "pipes" — depends on multi-lab + real inter-lab interactions, which
  are Phase B and fenced by the CLAUDE.md hard constraint.
- Hosting `intake.md` at `efferents.com` and pointing the landing page's agent
  block at it (currently the landing page is untouched and the pointer is a raw
  GitHub URL).
- A real (non-stub) bundled trial executor.
```
