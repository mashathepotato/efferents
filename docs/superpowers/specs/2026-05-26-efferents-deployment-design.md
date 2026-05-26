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

---

## 5. The four decouple touchpoints

Where the LabConfig flows into Phase A code. Each touchpoint is a small, targeted edit — no architectural rewrites.

### 5.1 — `efferents/lab.py`: static module → loader (CLAUDE.md items 2 + 3)

**Today:** module-level constants (`LAB_ID`, `DOMAIN`, `STUDENTS`, `PEER_REVIEW_*`, `DEFAULT_STUDENT_ID`, ...). Every consumer does `from efferents import lab` then reads `lab.LAB_ID`, etc.

**Change:** replace contents of `efferents/lab.py` with:

```python
# efferents/lab.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class Headline:
    column: str
    direction: str  # "max" | "min"

@dataclass(frozen=True)
class Panel:
    column: str
    label: str
    target: float | None = None

@dataclass(frozen=True)
class Source:
    dir: Path
    allowed_patterns: tuple[str, ...] = ("**/*.py",)

@dataclass(frozen=True)
class Executor:
    run_command: str        # must contain "{config_path}"
    smoke_command: str | None
    config_template: Path

@dataclass(frozen=True)
class Metrics:
    headline: Headline
    panels: tuple[Panel, ...]
    flat_digest_epsilon: float = 0.005

@dataclass(frozen=True)
class Budget:
    daily_cap_usd: float = 10.0
    sonnet_default: bool = True

@dataclass(frozen=True)
class LabConfig:
    lab_id: str
    domain: str
    pi_handle: str | None
    source: Source
    executor: Executor
    metrics: Metrics
    budget: Budget
    # Phase-A multi-student stays here, defaulted:
    default_student_id: str = "primary"
    max_open_campaigns_per_student: int = 2
    students: tuple[dict, ...] = field(default_factory=lambda: (
        {"id": "primary", "handle": None, "focus": "", "prompt_overrides": {}},
    ))
    peer_review_enabled: bool = False
    peer_review_accept_mean_threshold: float = 6.0
    peer_review_accept_min_threshold: int = 4

    @classmethod
    def from_submission(cls, submission_dir: Path) -> "LabConfig":
        """Load and validate hypothesis.md + lab.yaml. Raises SubmissionError."""
        ...

class SubmissionError(ValueError): ...

_active: LabConfig | None = None

def set_config(cfg: LabConfig) -> None:
    global _active
    _active = cfg

def get_config() -> LabConfig:
    if _active is None:
        raise RuntimeError("LabConfig not loaded; call set_config() before agent code runs")
    return _active

# Backward-compat shims so auto-qml's existing imports keep working until it migrates:
def __getattr__(name: str):  # PEP 562
    cfg = get_config()
    mapping = {
        "LAB_ID": cfg.lab_id,
        "DOMAIN": cfg.domain,
        "PI_HANDLE": cfg.pi_handle,
        "DEFAULT_STUDENT_ID": cfg.default_student_id,
        "MAX_OPEN_CAMPAIGNS_PER_STUDENT": cfg.max_open_campaigns_per_student,
        "STUDENTS": list(cfg.students),
        "PEER_REVIEW_ENABLED": cfg.peer_review_enabled,
        "PEER_REVIEW_ACCEPT_MEAN_THRESHOLD": cfg.peer_review_accept_mean_threshold,
        "PEER_REVIEW_ACCEPT_MIN_THRESHOLD": cfg.peer_review_accept_min_threshold,
    }
    if name in mapping:
        return mapping[name]
    raise AttributeError(name)

def get_student(student_id: str) -> dict: ...
def student_ids() -> list[str]: ...
```

**Loader:** `LabConfig.from_submission(dir)` reads `hypothesis.md` (checks `falsifiability_gate: passed`), reads `lab.yaml`, validates per Section 2's rules, returns a fully-resolved frozen `LabConfig`.

**Callsite impact:** zero immediate churn — `__getattr__` shim covers the old API. New code (registry, daemon, CLI) uses `lab.get_config()` directly. We migrate callsites away from the shim opportunistically; auto-qml keeps importing the old names until *its* next session.

### 5.2 — Coder path scope (CLAUDE.md item 5)

**Today** (`efferents/agents/coder.py`):
```python
DEFAULT_TARGET_GLOBS = ["auto_qml/*.py", "config/default.yaml", "config/smoke.yaml"]
SMOKE_CONFIG = "config/smoke.yaml"
_NEW_FILE_PATH_RE = re.compile(r"^auto_qml/[A-Za-z_][A-Za-z0-9_]*\.py$")
```
Plus the smoke invocation: `python -m auto_qml.run --config config/smoke.yaml`.

**Change:** these become functions of `lab.get_config()`:

```python
def _target_globs() -> list[str]:
    cfg = lab.get_config()
    src = str(cfg.source.dir).rstrip("/")
    return [
        *(f"{src}/{pat}" if not pat.startswith(src + "/") else pat
          for pat in cfg.source.allowed_patterns),
        str(cfg.executor.config_template),
    ]

def _new_file_path_re() -> re.Pattern:
    cfg = lab.get_config()
    src = re.escape(str(cfg.source.dir).rstrip("/"))
    return re.compile(rf"^{src}/[A-Za-z_][A-Za-z0-9_]*\.py$")

def _smoke_command(config_path: Path) -> str:
    cfg = lab.get_config()
    template = cfg.executor.smoke_command or cfg.executor.run_command
    return template.format(config_path=str(config_path))
```

Three call-side updates inside coder.py — line 47-49 (`DEFAULT_TARGET_GLOBS`, `SMOKE_CONFIG`), line 83 (`_NEW_FILE_PATH_RE`), and the smoke subprocess invocation. ~15-line diff.

### 5.3 — progress.py panel metrics (CLAUDE.md item 6)

**Today** (`efferents/agents/progress.py:58-63`):
```python
_PANEL_METRICS: list[tuple[str, str, float | None]] = [
    ("e_w1", "energy W1 (lower)", None),
    ...
]
```

**Change:**

```python
def _panel_metrics() -> list[tuple[str, str, float | None]]:
    cfg = lab.get_config()
    return [(p.column, p.label, p.target) for p in cfg.metrics.panels]
```

The headline-metric selection (the "best of each" line) reads `cfg.metrics.headline.column` and `.direction` — `min` ↔ today's lower-is-better, `max` flips it.

Touchpoints across progress.py: ~6 references to `_PANEL_METRICS` get inlined to `_panel_metrics()`. ~20-line diff.

### 5.4 — Daemon wiring (new code)

The Phase-A orchestrator never had a startup-config hook because the static `efferents/lab.py` was always available. The daemon adds one:

```python
# efferents/daemon.py
def run(submission_dir: Path) -> None:
    cfg = lab.LabConfig.from_submission(submission_dir)
    lab.set_config(cfg)
    os.chdir(submission_dir)             # so ./lab/ paths work as before
    migrations.runner.upgrade(Path("./lab/state.db"))
    orchestrator.start()                 # unchanged
```

`efferents/cli.py` calls `daemon.run()` directly in foreground mode, or forks (double-fork + setsid + pidfile) then calls it for `--detach`.

### What does NOT change in Phase A code

- `orchestrator.py` — unchanged. It already operates on whatever `lab.*` exposes.
- `state.py` — unchanged in v1. `recent_runs` SELECT stays QML-coupled; documented limitation. Phase B touches this.
- `analyst.py` — `flat_digest_epsilon` is the only knob, sourced from `cfg.metrics.flat_digest_epsilon`. ~3-line diff.
- `writer.py` — unchanged in v1. Peer-review thresholds keep reading `lab.PEER_REVIEW_*` via shim.
- `prompts/*.md` — unchanged in v1. QML-flavored prompts remain; documented limitation in intake.md.
- `researcher.py`, `librarian.py` — unchanged.

### Total decouple-work footprint

~150 lines of new code (`LabConfig` + loader + shim), ~50 lines of edits across `coder.py` + `progress.py` + `analyst.py`. No new dependencies (pydantic optional; can hand-roll dataclass validation since the schema is small).

---

## 6. State + lab directory layout

Two distinct trees: **(A)** the user's source repo at `source.dir` (where Coder writes + commits) — outside the submission, in the user's project. **(B)** the submission + lab dir — daemon's working state, observability, papers. Both essential; they don't overlap.

### Per-user

```
~/.efferents/
└── registry.json          # lab_id → submission_dir, lab_root, pid, started_at, status
```

Single JSON file with a file lock (fcntl). CLI reads/writes it; the daemon never touches it after registration. Keeps daemon-state under `lab/` so a corrupted registry never loses lab data.

### Per submission (everything the daemon owns)

```
./efferents-submissions/<slug>/
├── hypothesis.md                # popper-probe output (provenance copy)
├── lab.yaml                     # efferents lab config (provenance copy)
└── lab/                         # daemon's lab_root
    ├── daemon.pid               # PID of detached daemon
    ├── daemon.log               # stdout+stderr of detached daemon (rolling, 10MB cap)
    ├── state.db                 # SQLite: runs, campaigns, papers, peer_reviews, …
    ├── state.json               # cursors, budget tracker counters, supervisor streak
    ├── lab_notebook.md          # supervisor's running notebook
    ├── proposed_changes.md      # Researcher → Coder backlog
    ├── researcher_dialogue.jsonl
    ├── coder_log.jsonl
    ├── progress/
    │   └── index.html           # dashboard (regenerated on every digest)
    └── papers/                  # writer output, content-addressed by paper_id
        └── <paper_id>/
            ├── paper.md
            └── frontmatter.json
```

### The user's source repo (lives wherever they put it)

```
<source.dir>/                    # e.g. ~/Documents/my-research/src/
├── ...                          # user's existing code
├── <coder writes new .py here>
└── ... (must be a git repo; Coder commits each accepted change)
```

The Coder agent's smoke test runs `lab.config.executor.run_command` *inside the source repo's working dir*. Outputs (logs, generated samples) get written wherever the run command writes — typically into the source repo. The daemon's `lab/state.db` ingests **metric rows only** from the run command's stdout JSON result (see Section 7's contract).

### Path mapping at daemon startup

`daemon.run(submission_dir)` does:
1. Resolves `submission_dir` to absolute.
2. `os.chdir(submission_dir)` — so Phase A's hardcoded `./lab/...` paths resolve under the submission.
3. Resolves `cfg.source.dir` to absolute (it was relative in lab.yaml or absolute) — stored on the LabConfig at load time.
4. Coder agent always uses the absolute `cfg.source.dir`, never CWD-relative — protects against `cd` drift inside the orchestrator loop.

### Backups and re-attach

- `efferents stop` is graceful; `state.db` and `state.json` survive.
- `efferents start --submission <same-dir>` re-attaches to the existing `lab/` automatically. Migration runner is idempotent. Registry entry gets a new PID + `started_at`.
- No automatic backup — user's `lab/` is in their working directory and they can `git`-track it or rsync it if they care.

### Cleanup contract

- `efferents stop` removes nothing.
- `efferents list` shows `status: stopped` for stale entries (PID dead, registry not updated).
- No `efferents prune` command in v1. Manual `rm -rf lab/` if user wants a clean restart.

### Out of scope for v1

- Multi-machine state sync (daemon is single-host).
- Encrypted-at-rest state files.
- A read-only "lab archive" mode that lets you browse a finished lab's `lab/` after the daemon's gone.

---

## 7. Compute & execution model

### The fundamental constraint

Every Phase-A cycle is: Researcher proposes → Coder edits code → smoke test → if smoke passes, real training run → eval → row in `state.db`. The training run is where compute matters. It's domain-specific (GPU minutes for QML/diffusion, CPU for ablations, whatever the lab needs).

Moltbook's design dodges this because its agents don't *do* anything — they post text. Efferents can't dodge it: empirical results are the whole point.

### Where does compute happen — three reasonable models

**Model A — Local daemon, local compute (Phase A today).**
Daemon runs on the user's machine. `run_command` invokes a local Python process. User's hardware does the work. Simplest. Sharply limiting for any lab that needs serious GPU.

**Model B — Local daemon, BYO remote compute (recommended for v1).**
Daemon stays on the user's laptop. `run_command` is a shell template — *anything that returns when training finishes*: `ssh gpu-box "cd /path && python -m foo.run --config {config_path}"`, `modal run my_module.train --config {config_path}`, a sbatch wrapper, whatever. Daemon doesn't care how the work happens; it cares about parsing the result. Requires loosening Phase A's tight coupling between run_command and SQLite (described below).

**Model C — Efferents-provisioned compute (Phase B+).**
efferents.com (or a per-lab cloud account) spins up VMs on submission. User pays via efferents. Substantial infra; substantial trust ask. Not v1.

**Recommendation: Model B for v1.** Keeps the daemon's deployment story unchanged (`pip install efferents`, run locally), unlocks GPU-backed labs via existing tools the user already knows (ssh, modal, slurm), and doesn't commit us to building cloud infrastructure.

### What Model B requires that Phase A doesn't have

**The problem.** Phase A's current contract is: `run_command` opens `lab/state.db` and writes a row directly via the schemas-defined writer. Works when daemon and run share a filesystem. Breaks the moment training happens on a different host.

**The fix — stdout result contract.** The run command's last action is a single JSON line to stdout:

```json
{"run_id":"<uuid>","metrics":{"e_w1":0.043,"active_frac_w1":0.012,...},"git_commit":"abc123","elapsed_s":847.2,"artifacts":[{"path":"./lab/samples/run_abc.png","kind":"sample"}]}
```

Daemon captures stdout (already does, for logging), parses the last `{...}` line, inserts the row. Artifacts are local paths; the daemon expects them readable from the daemon's host. For remote compute, the user is responsible for rsync-back or mounting (e.g., `modal.Mount`, sshfs). Missing artifacts gracefully skipped by the dashboard.

### Daemon-side changes for Model B

Wrap subprocess invocation with:

```python
def _run_and_capture(cmd: str, timeout_s: int) -> RunResult:
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_s)
    last_json = _extract_trailing_json(proc.stdout)  # parses last balanced { ... }
    if last_json is None:
        return RunResult(ok=False, error="run_command did not emit a JSON result on stdout",
                         stdout=proc.stdout, stderr=proc.stderr)
    return RunResult(ok=proc.returncode == 0, metrics=last_json.get("metrics"),
                     artifacts=last_json.get("artifacts", []), git_commit=last_json.get("git_commit"),
                     elapsed_s=last_json.get("elapsed_s"), stdout=proc.stdout, stderr=proc.stderr)
```

Then a small writer that inserts the row into `state.db`.

### Backward compat with auto-qml

auto-qml today writes directly to SQLite. The new stdout contract would skip that row. Two options:
- **(preferred) Migrate auto-qml's `run.py` to emit JSON on stdout.** ~10-line change in auto-qml. Done in auto-qml's next session.
- **(fallback) Dual-read.** Daemon checks: did a row appear in state.db for this run_id during the subprocess? If yes, use it. If no, fall back to stdout parsing. Keeps auto-qml working unchanged. Ugly but safe.

Recommend the preferred path — small, clean, and auto-qml's `run.py` is the natural place to own the contract.

### What lab.yaml gains for Model B (optional, defaulted)

```yaml
executor:
  run_command: "modal run my_module.train --config {config_path}"
  smoke_command: "modal run my_module.train --config {config_path} --smoke"
  config_template: configs/default.yaml
  run_timeout_s: 7200            # optional; default 7200 (2h)
  smoke_timeout_s: 300           # optional; default 300 (5m)
  env_passthrough:               # optional; env vars copied into subprocess
    - MODAL_TOKEN_ID
    - MODAL_TOKEN_SECRET
    - WANDB_API_KEY
```

`env_passthrough` is the clean way to ship secrets to remote backends without putting them in lab.yaml.

### Documentation impact on intake.md

Add a sentence in Step 2 question #2: "Run command template — anything that takes a config path and emits a JSON metrics object on stdout. Common shapes: local Python, ssh to a GPU box, modal/runpod/slurm submission."

### Out of scope for v1

- Built-in adapters for specific backends (modal, slurm, ssh, kubernetes). The shell template covers all of these; we don't pre-package them.
- Daemon-side compute provisioning.
- Cost tracking for compute (we already track Anthropic spend via budget tracker; compute spend is user-tracked).
- Live log streaming from remote runs to the dashboard. Stdout is captured to `daemon.log`; that's it.
