# efferents deployment design

**Status:** in-progress design. Sections committed incrementally as approved.
**Date:** 2026-05-26
**Builds on:** [`2026-05-17-lab-foundation-design.md`](./2026-05-17-lab-foundation-design.md) (Phase A), [`context/journal_vision.md`](../../../context/journal_vision.md) (north star)

## Motivation

Deploy the efferents framework so that humans can submit a research hypothesis through their own AI agent and have an autonomous lab pick it up. The hypothesis goes through the popper-probe falsifiability gate; on accept, a local daemon takes over as the lab's Supervisor and dispatches PhD-style specialty work via Anthropic API calls. Verification of lab identity is deferred.

The distribution model mirrors [moltbook](https://moltbook.com): a hosted markdown file (`efferents.com/intake.md`) is the entry point. Any agent that can fetch a URL and run a shell can onboard a lab — no Claude Code marketplace plugin required.

## Scope (Approach A, locked in during brainstorm)

Ship the entry-flow plugin and do the minimum-viable framework decoupling from QML. Specifically:

- New: `intake.md`, `status.md` (hosted); `efferents` CLI; `LabConfig` dataclass + loader; lab registry; daemon wrapper.
- Targeted decouple work inside Phase A:
  - LabConfig dataclass loaded from submission frontmatter (CLAUDE.md item 2)
  - `efferents/lab.py` becomes a loader, not a static module (item 3)
  - Coder path-scope reads from LabConfig (item 5)
  - progress.py panel metrics read from LabConfig (item 6)
- A tiny non-QML smoke lab to prove the plumbing.

Out of scope:
- Hosted backend / API endpoints / journal venue
- Lab ownership verification (tweet-flow or otherwise)
- Cross-lab heartbeat / corroboration / retraction
- Full prompt templating (CLAUDE.md item 4) — labs inherit QML-flavored prompts in v1
- A full second example lab beyond the smoke lab (CLAUDE.md item 9)
- `recent_runs` SELECT column generalization (CLAUDE.md item 7) — start with `SELECT *`
- `efferents init` scaffold (CLAUDE.md item 8) — the submission frontmatter is the scaffold

---

## 1. Architecture

Three components, glued by a file contract.

```
┌──────────────────────────────────────────────────────────────────┐
│  Human's agent (any agent that can fetch URLs + run shell)       │
│                                                                  │
│  Human: "Read https://efferents.com/intake.md and follow it"     │
│                                                                  │
│  1. Agent fetches intake.md                                      │
│  2. Instructions inside:                                         │
│     a. pip install efferents (or git clone, fallback)            │
│     b. Run popper-probe intake interactively with the human      │
│     c. Prompt human for lab config                               │
│     d. Write submission/ dir with hypothesis.md + lab.yaml       │
│     e. Run `efferents start --submission <dir>` as daemon        │
│     f. Report lab_id, daemon PID, dashboard path                 │
└────────────────────────────────────┬─────────────────────────────┘
                                     │ subprocess
                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│  efferents daemon (Phase A orchestrator + LabConfig load)        │
│  • researcher/coder/analyst/writer loop                          │
│  • lab state under <submission>/lab/state.db                     │
│  • dashboard under <submission>/lab/progress/                    │
│  • lifetime: until budget exhausted, hypothesis resolved, or     │
│    human kills it                                                │
└──────────────────────────────────────────────────────────────────┘
```

**Distribution principles, lifted from moltbook:**
- A single hosted markdown URL is the entry point. The agent reads it and follows numbered steps.
- Multiple skill markdowns for different concerns. v1 ships `intake.md` and (optionally) `status.md`. `register.md` and `submit.md` come in Phase B when efferents.com becomes a venue.
- No backend in v1. Lab identity is local (UUID in the lab's state.db). The daemon runs on the human's machine against their `ANTHROPIC_API_KEY`.
- Popper-probe stays an external dependency — per CLAUDE.md hard constraint.

**Reused from Phase A as-is:**
- Orchestrator loop, budget tracker, state primitives, paper writer, analyst, librarian, popper_gate (deprecated for new submissions but kept for auto-qml).

**New code surfaces:**
- `efferents/cli.py` — `efferents` console-script entry point
- `efferents/lab.py` — replaces static module with `LabConfig` loader
- `efferents/registry.py` — `~/.efferents/registry.json` read/write
- `efferents/daemon.py` — fork + pidfile + signal handling wrapper around `orchestrator.start()`
- `intake.md`, `status.md` — hosted markdown contracts

---

## 2. Submission contract

The agent produces a **submission directory** with two files. Separation of concerns: popper-probe owns its hypothesis format, efferents owns the lab config schema.

```
submission/
├── hypothesis.md     # popper-probe output, unmodified
└── lab.yaml          # efferents lab config (this design owns the schema)
```

### `hypothesis.md`

Whatever popper-probe emits — existing format with `falsifiability_gate: passed`, `status: active`, probe sections, `## Falsifier` clause. Efferents reads:
- The hypothesis slug → default `lab_id`
- The file hash → for paper frontmatter / journal compatibility
- The body text → passed to the Researcher's first call

If `falsifiability_gate: failed`, daemon refuses to start. Hard fail.

### `lab.yaml` schema

```yaml
# --- Identity ---
lab_id: my-conjecture          # optional; defaults to hypothesis slug
domain: quantum-ml             # opaque string; used for future venue routing
pi_handle: "@mashathepotato"   # optional

# --- Source ---
source:
  dir: ./src/                  # REQUIRED. Local path. Coder writes here.
  allowed_patterns:            # optional; default ["**/*.py"]
    - "**/*.py"
    - "configs/*.yaml"

# --- Executor ---
executor:
  run_command: "python -m my_research.run --config {config_path}"   # REQUIRED
  smoke_command: "python -m my_research.run --config {config_path} --smoke"  # optional
  config_template: configs/default.yaml   # REQUIRED. Path relative to source.dir.

# --- Metrics ---
metrics:
  headline:                    # REQUIRED
    column: accuracy
    direction: max             # "max" or "min"
  panels:                      # optional; dashboard panels
    - { column: accuracy, label: "Acc",  target: 0.95 }
    - { column: loss,     label: "Loss", target: null }
  flat_digest_epsilon: 0.005   # optional; analyst's flat-improvement detector

# --- Budget ---
budget:
  daily_cap_usd: 10.0          # optional; default 10.0
  sonnet_default: true         # optional; default true
```

### Validation rules (fail fast before daemon start)

- `hypothesis.md` missing or `falsifiability_gate: failed`
- `lab.yaml` missing or unparseable
- `source.dir` doesn't exist on disk
- `executor.config_template` doesn't exist under `source.dir`
- `executor.run_command` doesn't contain `{config_path}` placeholder
- `metrics.headline.direction` not in {`max`, `min`}
- `metrics.headline.column` is empty

Validation lives in `efferents.lab.LabConfig.from_submission(dir: Path)` — single entry, returns a fully-resolved `LabConfig` or raises `SubmissionError` with the offending field.

### Out of scope for v1
- Remote `source.repo: github.com/...` cloning — local path only.
- Multi-PhD-student concurrent campaigns within one lab — single campaign per submission.
- `claim_url` / verification flow — Phase B (hosted venue).
- Custom prompt overrides — labs inherit current QML-flavored prompts; documented limitation in `intake.md`.

---

## 3. `intake.md` contents

Hosted at `efferents.com/intake.md` (initially: a GitHub raw URL). Written FOR the agent. The agent translates each step into conversational prompts for the human.

```markdown
# efferents intake

You are an agent helping a human submit a research hypothesis to an
autonomous lab. This file is your instruction set. Follow each step in
order. If any prerequisite or validation fails, stop and tell the human.

## Prerequisites

- popper-probe plugin/skill installed: https://github.com/mashathepotato/popper-probe
- Python 3.11+ and pip available in the shell
- A local git repository the human is OK with autonomous edits to

## Step 1 — Falsifiability intake (interactive)

Invoke popper-probe:intake on the human's claim. The human will answer
adversarial probes. The output is a hypothesis.md at
<popper-corpus>/<slug>/hypothesis.md with `falsifiability_gate: passed`.

If `falsifiability_gate: failed`, surface the diagnostic and STOP.
If popper-probe is unavailable, refuse and tell the human to install it.

## Step 2 — Lab configuration (interactive)

Ask the human, one question at a time:
  1. Local path to the source code to be modified
  2. Run command template (must contain `{config_path}`)
  3. Path to the run command's config template (relative to source dir)
  4. Headline metric column name and direction (`max` or `min`)
  5. Domain string (free text, e.g. "quantum-ml", "nlp")

Then offer optional fields: panels, allowed_patterns, flat_digest_epsilon,
daily budget cap. Default daily budget cap is $10.

Schema reference:
https://github.com/mashathepotato/efferents/blob/main/docs/lab-yaml-schema.md

## Step 3 — Stage submission

mkdir -p ./efferents-submissions/<slug>/
cp <popper-corpus>/<slug>/hypothesis.md ./efferents-submissions/<slug>/
Write lab.yaml to ./efferents-submissions/<slug>/lab.yaml

## Step 4 — Install + validate

pip install efferents
efferents validate --submission ./efferents-submissions/<slug>/

If validation fails, surface the field-level error to the human and STOP.

## Step 5 — Surface warnings (mandatory; before step 6)

Tell the human, verbatim:
  - "The daemon will make Anthropic API calls against your ANTHROPIC_API_KEY.
    Budget cap is $<cap>/day; lower it in lab.yaml if you want."
  - "The framework's agent prompts are currently calibrated for QML-domain
    research. Non-QML domains may get odd suggestions until prompt overrides
    ship in Phase B."
  - "The Coder agent will autonomously modify files under source.dir.
    Make sure that directory is in git and clean."

Ask: "OK to start the daemon?" If no, STOP.

## Step 6 — Start the daemon

efferents start --submission ./efferents-submissions/<slug>/ --detach

Report to the human:
  - lab_id (printed by `start`)
  - Daemon PID
  - Path to the progress dashboard
  - That their session can end; daemon keeps running
  - That they can check status by asking you to fetch
    https://efferents.com/status.md

## Step 7 — End

You're done. The daemon owns the lab from here.
```

### Notes
- **Terse, instructional, for-agent.** Mirrors moltbook's SKILL.md style.
- **Step 5 warnings are mandatory.** Deliberate human-confirmation gate before any autonomous code modification.
- **popper-probe stays external.** intake.md only invokes it; doesn't inline its protocol.
- **`status.md`** is a Phase B nice-to-have. The agent can also run `efferents status --lab-id <id>` locally.

---

## 4. CLI surface

`pyproject.toml` adds a `console_scripts` entry: `efferents = efferents.cli:main`. The existing `python -m efferents.agents` keeps working for backward compat with auto-qml.

### Commands

```
efferents validate  --submission <dir>
efferents start     --submission <dir> [--detach] [--lab-root <path>]
efferents status    [--lab-id <id>]
efferents stop      --lab-id <id>
efferents list
```

### `efferents validate --submission <dir>`
- Loads `hypothesis.md` + `lab.yaml` from `<dir>` via `LabConfig.from_submission(dir)`.
- On error: prints field-level diagnostic to stderr, exit code 1.
- On success: prints `OK lab_id=<id> domain=<d> source_dir=<path>`, exit 0.
- Pure validator — no side effects.

### `efferents start --submission <dir> [--detach] [--lab-root <path>]`
- Runs validation first.
- Resolves `<lab_root>`: defaults to `<submission>/lab/` so everything for one submission stays together. `--lab-root` lets users override.
- Initializes lab dir on first run: SQLite via `migrations.runner.upgrade()`, copies `hypothesis.md` + `lab.yaml` for provenance, writes empty `state.json`.
- Registers the lab in `~/.efferents/registry.json`:
  ```json
  { "lab_id": "...", "submission_dir": "...", "lab_root": "...",
    "started_at": "...", "pid": 12345, "status": "running" }
  ```
- If `--detach`: forks a daemon process (double-fork), writes `<lab_root>/daemon.pid`, prints `lab_id=<id> pid=<pid> dashboard=<path>` to stdout, returns immediately.
- If not `--detach`: runs the orchestrator loop in foreground (dev + smoke tests).
- Daemon `cd`s into `<submission>` before running so Phase A's relative `./lab/` paths still work without churn.

### `efferents status [--lab-id <id>]`
- With `--lab-id`: looks up via registry, reads `<lab_root>/daemon.pid` (liveness check), summarizes:
  - Daemon: running / dead / never started
  - Started: ISO timestamp
  - Last activity: `state.json` mtime
  - Runs completed: count from `state.db`
  - Budget spent today: from budget tracker
  - Headline metric: best value + last 5 trajectory
  - Dashboard: `file://<lab_root>/progress/index.html`
- Without `--lab-id`: equivalent to `efferents list`.

### `efferents stop --lab-id <id>`
- Reads pidfile, sends `SIGTERM`, waits up to 10s.
- If still alive: `SIGKILL`, log it.
- Updates registry: `status: stopped`.

### `efferents list`
- Reads registry, runs liveness check on each PID, prints a table:
  ```
  LAB_ID              STATUS    STARTED              SUBMISSION
  my-conjecture       running   2026-05-26 14:02     ./submissions/my-conjecture/
  qml-aug-depth-3     stopped   2026-05-24 09:11     ./submissions/qml-aug-depth-3/
  ```

### Implementation footprint
- `efferents/cli.py` — new file, ~150 lines. `argparse` subcommand dispatch.
- `efferents/lab.py` — replaces static module with the `LabConfig` loader (Section 5).
- `efferents/registry.py` — new tiny module for `~/.efferents/registry.json` read/write with a file lock.
- `efferents/daemon.py` — new tiny module for fork + pidfile + signal handling. Reuses `efferents.agents.orchestrator.start()` as the loop body.
- `efferents/agents/__main__.py` — unchanged.

### Out of scope for v1
- `efferents logs --lab-id`
- `efferents restart --lab-id`
- Remote registry / multi-machine
