# efferents intake

You are helping a human launch an autonomous research lab. They have nothing
installed but you (Claude Code). Work in the human's **current working
directory** — a fresh, empty project dir. Follow the steps in order and
translate each into plain conversation for the human. Ask for their research
claim when you reach Step 3.

This runs a *bounded trial*: it exercises the full pipeline (hypothesis →
experiment runs → dashboard) and is fully disposable — the whole project dir can
be deleted afterward.

## Step 0 — Preflight

Confirm the API key is set:
```bash
python3 -c "import os,sys; sys.exit(0 if os.environ.get('ANTHROPIC_API_KEY') else 1)" \
  && echo "ANTHROPIC_API_KEY ok" || echo "MISSING ANTHROPIC_API_KEY"
```
If it prints `MISSING`, STOP and ask the human to export `ANTHROPIC_API_KEY`.

Confirm you can use the **popper-probe:intake** skill (needed in Step 3). If the
popper-probe plugin is not installed, STOP and tell the human to install it.

## Step 1 — Install efferents

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install "git+https://github.com/mashathepotato/efferents.git"
efferents --help
```
The help output must list a `serve` subcommand. Keep this venv activated for all
later steps.

## Step 2 — Scaffold the disposable trial kit

Create these four files exactly as given.

`executor/stub_run.py`:
```python
"""Trial stub run: reads config, computes synthetic_loss, emits stdout JSON.

This is a stub for exercising the efferents pipeline end to end — NOT real
research. Replace it (Step 4) if you want the trial to test your real claim.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
import uuid

import yaml


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=2
        ).strip()
    except Exception:
        return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    cfg = yaml.safe_load(open(args.config))
    coefficient = float(cfg.get("coefficient", 0.5))
    seed = int(cfg.get("seed", 42))
    rng = random.Random(seed)

    start = time.time()
    noise = rng.gauss(0, 0.01) if not args.smoke else 0.0
    synthetic_loss = abs(0.8 - coefficient) + noise

    payload = {
        "run_id": str(uuid.uuid4()),
        "metrics": {"synthetic_loss": synthetic_loss},
        "git_commit": _git_commit(),
        "elapsed_s": time.time() - start,
        "artifacts": [],
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
```

`configs/default.yaml`:
```yaml
coefficient: 0.5
seed: 42
```

`submission/lab.yaml`:
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

`run_trial.py`:
```python
"""Disposable bounded trial runner. Not part of the efferents framework.

Mirrors `efferents start` minus the daemon: load config, init the lab dir, then
run a bounded number of orchestrator iterations. Delete with the project dir.
"""
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

## Step 3 — Falsifiability intake (popper-probe, in the terminal)

Ask the human for their research claim. Invoke the **popper-probe:intake** skill
on that claim — it runs the adversarial dialogue and writes a `hypothesis.md`
with `falsifiability_gate: passed`. Copy that file to `submission/hypothesis.md`.

If popper-probe emits `falsifiability_gate: failed`, the claim could not be made
falsifiable — tell the human and re-run intake with a sharper claim.

## Step 4 — (optional) Choose a real executor

By default the trial uses the bundled **stub** executor, which computes a
synthetic `synthetic_loss` unrelated to the human's claim — it proves the
plumbing without real compute. Now that the hypothesis exists, the human may
replace `executor/stub_run.py` and the `executor`/`metrics` blocks of
`submission/lab.yaml` with a real executor for their domain. Otherwise continue
with the stub.

## Step 5 — Run one bounded trial

```bash
python run_trial.py
```
Runs a bounded number of orchestrator iterations (default 3; override with
`TRIAL_MAX_ITERS=N`) against the submission, writing results to `submission/lab/`.

## Step 6 — Watch it on the dashboard

```bash
efferents serve --lab-root submission/lab
```
Open the printed `http://localhost:8800` link and report it to the human. The
read-only dashboard shows the hypothesis, the trial run(s), the headline metric,
and agent activity.

## Step 7 — Cleanup

When the human is done, the entire project dir is disposable: `rm -rf` it.
