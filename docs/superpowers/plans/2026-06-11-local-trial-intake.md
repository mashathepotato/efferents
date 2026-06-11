# Local Cold-Start Trial via `intake.md` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single committed `intake.md` at the repo root that lets a fresh Claude Code agent (in an empty project dir, nothing installed) install efferents from git, run popper-probe in the terminal, scaffold a disposable trial kit, run one bounded trial, and watch it on the read-only dashboard.

**Architecture:** One committed markdown contract (`intake.md`) that embeds a disposable trial kit (a stub executor, a config template, a `lab.yaml`, and a bounded `run_trial.py` runner) as fenced code blocks the agent writes into the user's throwaway project dir. The framework package (`efferents/`) is never modified — `intake.md` only *uses* `efferents serve`, `LabConfig`, `cli._init_lab_root`, and `Orchestrator(max_iterations=…)`.

**Tech Stack:** Python ≥3.10, the installed `efferents` package (flit-built, pip-installable from git), popper-probe (`popper-probe:intake` Claude Code plugin), stdlib.

**Reference spec:** `docs/superpowers/specs/2026-06-11-local-trial-intake-design.md`

**Branch:** `feat/local-trial-intake` (already created; spec committed there).

**Note on "tests":** the deliverable is a markdown file and the trial kit is disposable (not committed), so there are no committed unit tests. Each task's verification is a real command with expected output (packaging gate, kit-loads gate, raw-URL gate). The final acceptance is the user's live trial.

---

## File Structure

| File | Responsibility | Committed? |
|------|----------------|-----------|
| `intake.md` (repo root) | The cold-start contract; embeds the disposable trial kit | **Yes** (the only repo addition) |
| `efferents/**` | Unchanged | n/a |
| trial kit (`executor/stub_run.py`, `configs/default.yaml`, `submission/lab.yaml`, `run_trial.py`) | Scaffolded by the agent into the user's disposable project dir from `intake.md` | No (embedded as text only) |

---

## Task 1: Packaging gate — confirm a pip-installed wheel ships the dashboard

This must pass before `intake.md` is viable: `pip install git+…` only works if the flit wheel includes the dashboard static files and the `serve` command.

**Files:**
- None modified (verification only). If it FAILS, add a `[tool.flit.sdist]`/`[tool.flit.external-data]` include to `pyproject.toml` — see Step 4.

- [ ] **Step 1: Build and install the current tree into a throwaway venv**

Run:
```bash
cd /Users/masha/Documents/efferents
rm -rf /tmp/efferents-pkgcheck && python3 -m venv /tmp/efferents-pkgcheck
/tmp/efferents-pkgcheck/bin/pip install --quiet . 2>&1 | tail -5
```
Expected: installs without error (ends with `Successfully installed efferents-0.1.4 …`).

- [ ] **Step 2: Confirm the `serve` subcommand is present**

Run:
```bash
/tmp/efferents-pkgcheck/bin/efferents --help 2>&1 | grep -A20 "positional"
```
Expected: the subcommand list includes `serve`.

- [ ] **Step 3: Confirm the dashboard static files shipped inside the installed package**

Run:
```bash
/tmp/efferents-pkgcheck/bin/python -c "
from pathlib import Path
import efferents.dashboard.server as s
static = s.STATIC_DIR
files = sorted(p.name for p in static.glob('*'))
print('STATIC_DIR:', static)
print('files:', files)
assert static.is_dir(), 'static dir missing from installed package'
for f in ('dashboard.html','dashboard.css','dashboard.js'):
    assert (static / f).is_file(), f'missing {f} in installed package'
print('OK: dashboard static files shipped')
"
```
Expected: prints `OK: dashboard static files shipped`.

- [ ] **Step 4: If Step 3 FAILED, make flit include the static files, then re-run Steps 1–3**

Only if the static files did not ship, add this to `pyproject.toml` (under the existing `[tool.flit.module]` block) and reinstall:
```toml
[tool.flit.external-data]
directory = "efferents/dashboard/static"
```
If flit's default already shipped the files (Step 3 printed OK), make NO change and skip to Step 5.

- [ ] **Step 5: Clean up the throwaway venv**

Run:
```bash
rm -rf /tmp/efferents-pkgcheck
```

- [ ] **Step 6: Commit (only if pyproject.toml changed in Step 4)**

If Step 4 modified `pyproject.toml`:
```bash
git add pyproject.toml
git commit -m "build: ensure dashboard static files ship in the wheel"
```
If no change was needed, skip this commit.

---

## Task 2: Write `intake.md`

**Files:**
- Create: `intake.md` (repo root)

- [ ] **Step 1: Create `intake.md` with exactly this content**

Write `/Users/masha/Documents/efferents/intake.md`:

````markdown
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
````

- [ ] **Step 2: Verify the file was written and contains the key anchors**

Run:
```bash
cd /Users/masha/Documents/efferents
grep -c "popper-probe:intake" intake.md          # expect >= 2
grep -q "pip install \"git+https://github.com/mashathepotato/efferents.git\"" intake.md && echo "install line OK"
grep -q "efferents serve --lab-root submission/lab" intake.md && echo "serve line OK"
grep -q "TRIAL_MAX_ITERS" intake.md && echo "bounded-run OK"
```
Expected: a count ≥ 2 and the three `OK` lines.

- [ ] **Step 3: Commit**

```bash
git add intake.md
git commit -m "feat: add intake.md cold-start contract (local trial via pip+popper-probe)"
```

---

## Task 3: Kit-loads gate — verify the embedded kit scaffolds and loads

Prove the embedded files are correct by reproducing what the agent does: scaffold them into a temp dir (against the *installed* package) and confirm `LabConfig.from_submission` loads and the scripts compile. This does not run the full orchestrator (that needs API budget and is the user's live trial).

**Files:**
- None committed (temp scaffold only).

- [ ] **Step 1: Install efferents into a throwaway venv and scaffold the kit from intake.md's blocks**

Run (this mirrors the agent following Step 2 of intake.md, plus a dummy hypothesis):
```bash
cd /tmp && rm -rf efferents-kitcheck && mkdir efferents-kitcheck && cd efferents-kitcheck
python3 -m venv .venv && . .venv/bin/activate
pip install --quiet "git+https://github.com/mashathepotato/efferents.git" 2>&1 | tail -1 || pip install --quiet /Users/masha/Documents/efferents
mkdir -p executor configs submission
cp /Users/masha/Documents/efferents/examples/smoke-lab/src/stub_run.py executor/stub_run.py
printf 'coefficient: 0.5\nseed: 42\n' > configs/default.yaml
cat > submission/lab.yaml <<'YAML'
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
YAML
printf -- '---\nslug: trial\nfalsifiability_gate: passed\nstatus: active\n---\n\n## Claim\nThe coefficient minimizing synthetic_loss is near 0.8.\n\n## Falsifier\nLoss does not fall below 0.05 for any coefficient.\n' > submission/hypothesis.md
```
Note: the kit's `submission/lab.yaml` points `source.dir` at `./executor/` and `config_template` at `../configs/default.yaml`, so this scaffold must place `executor/` and `configs/` as siblings of `submission/` — which it does.

- [ ] **Step 2: Confirm `LabConfig.from_submission` loads the scaffolded submission**

Run:
```bash
cd /tmp/efferents-kitcheck && . .venv/bin/activate
python -c "
from efferents.lab import LabConfig
cfg = LabConfig.from_submission('submission')
assert cfg.lab_id == 'trial'
assert cfg.metrics.headline.column == 'synthetic_loss'
print('OK: from_submission loaded the trial submission')
"
```
Expected: prints `OK: from_submission loaded the trial submission`.
(The `source.dir`/`config_template` existence checks pass because `executor/` and `configs/default.yaml` exist — no `check_paths=False` needed.)

- [ ] **Step 3: Confirm `run_trial.py` and `stub_run.py` are syntactically valid and import-resolvable**

Write `run_trial.py` (verbatim from intake.md Step 2) into `/tmp/efferents-kitcheck/run_trial.py`, then:
```bash
cd /tmp/efferents-kitcheck && . .venv/bin/activate
python -m py_compile run_trial.py executor/stub_run.py && echo "OK: py_compile passed"
python -c "from efferents.cli import _init_lab_root; from efferents.agents.orchestrator import Orchestrator; from efferents.envfile import load_dotenv; print('OK: run_trial imports resolve')"
```
Expected: `OK: py_compile passed` and `OK: run_trial imports resolve`.

- [ ] **Step 4: Confirm the stub executor emits parseable result JSON**

Run:
```bash
cd /tmp/efferents-kitcheck && . .venv/bin/activate && cd executor
python3 -m stub_run --config ../configs/default.yaml | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'synthetic_loss' in d['metrics']; print('OK: stub emitted synthetic_loss =', d['metrics']['synthetic_loss'])"
```
Expected: prints `OK: stub emitted synthetic_loss = …`.

- [ ] **Step 5: Clean up**

Run:
```bash
rm -rf /tmp/efferents-kitcheck
```

(No commit — this task is verification only. If any check fails, fix the corresponding embedded block in `intake.md` and re-run Task 3.)

---

## Task 4: Publish — push and verify the raw pointer URL

**Files:**
- None modified (publish + verification).

- [ ] **Step 1: Push the branch's commits to origin**

The pointer URL serves `main`, so `intake.md` must reach `main`. Push the feature branch first (final merge to main happens via the finishing-a-development-branch step after this plan):
```bash
cd /Users/masha/Documents/efferents
git push -u origin feat/local-trial-intake
```
Expected: push succeeds.

- [ ] **Step 2: Note the pointer URL the user will paste**

The instruction pointer (after `intake.md` lands on `main`) is:
```
Read https://raw.githubusercontent.com/mashathepotato/efferents/main/intake.md and follow it
```
Until `intake.md` is merged to `main`, the branch-scoped URL for testing is:
```
https://raw.githubusercontent.com/mashathepotato/efferents/feat/local-trial-intake/intake.md
```

- [ ] **Step 3: Verify the branch-scoped raw URL resolves**

Run:
```bash
curl -s -o /dev/null -w "raw intake.md (branch) HTTP %{http_code}\n" \
  https://raw.githubusercontent.com/mashathepotato/efferents/feat/local-trial-intake/intake.md
```
Expected: `HTTP 200` (may lag a few seconds after push; retry if 404).

- [ ] **Step 4: Report readiness**

Report to the user: the branch raw URL is live for testing; after merging to `main` (finishing-a-development-branch), the canonical pointer is the `main` raw URL. The user then runs the live trial as the new-user simulation.

---

## Self-Review Notes

- **Spec coverage:** intake.md contract + 7 steps → Task 2. Embedded kit (stub_run.py, configs/default.yaml, submission/lab.yaml, run_trial.py) → Task 2 Step 1, verified in Task 3. Packaging precondition (wheel ships dashboard) → Task 1. Push + raw-URL pointer → Task 4. Disposable footprint (only intake.md committed; efferents/ untouched) → File Structure table; no task modifies `efferents/` except the conditional flit include in Task 1 Step 4 (build config only, if needed). Error handling (missing key, failed gate, empty run) → encoded in intake.md Steps 0/3/5.
- **Placeholder scan:** all embedded files are verbatim (stub_run.py from the smoke-lab original; run_trial.py and lab.yaml from the spec). No TBD/TODO. The one conditional (Task 1 Step 4) is gated on an explicit check, with exact toml to add.
- **Consistency:** `run_trial.py` uses `lab_dir="lab"`/`context_dir="context"` after `os.chdir(SUB)`, and `_init_lab_root(SUB, SUB/"lab")` — both resolve to the same `submission/lab`. `submission/lab.yaml` `source.dir: ../executor/` (relative to `submission/`, the dir holding `lab.yaml`) resolves to the project-root `executor/`; `config_template: ../configs/default.yaml` (relative to `source.dir`) then resolves to the project-root `configs/default.yaml` — matching the Task 3 scaffold layout (executor/, configs/ as siblings of submission/). The dashboard view path `efferents serve --lab-root submission/lab` matches where `run_trial.py` writes. `Orchestrator(max_iterations=…)` matches the verified keyword signature.
```
