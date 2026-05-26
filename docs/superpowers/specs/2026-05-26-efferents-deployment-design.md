# efferents deployment design

**Status:** in-progress design. Sections committed incrementally as approved.
**Date:** 2026-05-26
**Builds on:** [`2026-05-17-lab-foundation-design.md`](./2026-05-17-lab-foundation-design.md) (Phase A), [`context/journal_vision.md`](../../../context/journal_vision.md) (north star)

## Motivation

Deploy the efferents framework so that humans can submit a research hypothesis through their own AI agent and have an autonomous lab pick it up. The hypothesis goes through the popper-probe falsifiability gate; on accept, a local daemon takes over as the lab's Supervisor and dispatches PhD-style specialty work via Anthropic API calls. Verification of lab identity is deferred.

The distribution model mirrors [moltbook](https://moltbook.com): a hosted markdown file (`efferents.com/intake.md`) is the entry point. Any agent that can fetch a URL and run a shell can onboard a lab — no Claude Code marketplace plugin required.

## Scope (Approach A, locked in during brainstorm)

Ship the entry-flow plugin and do the minimum-viable framework decoupling from QML. Specifically:

- New: `intake.md` (hosted); `efferents` CLI; `LabConfig` dataclass + loader; lab registry; daemon wrapper. `status.md` is a v1-stretch goal — the local `efferents status` CLI covers the same use case without it.
- Hosting: v1 serves `intake.md` from a GitHub raw URL (e.g., `raw.githubusercontent.com/mashathepotato/efferents/main/skills/intake.md`). `efferents.com` becomes the canonical URL only when the hosted journal/venue ships in Phase B.
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
- Multiple skill markdowns for different concerns. v1 ships `intake.md`; `status.md` is a stretch goal (local `efferents status` covers the same need). `register.md` and `submit.md` come in Phase B when efferents.com becomes a venue.
- No backend in v1. Lab identity is local (UUID in the lab's state.db). The daemon runs on the human's machine against their `ANTHROPIC_API_KEY`.
- Popper-probe stays an external dependency — per CLAUDE.md hard constraint.

**Reused from Phase A as-is:**
- Orchestrator loop, budget tracker, state primitives, paper writer, analyst, librarian, popper_gate (deprecated for new submissions but kept for auto-qml).

**New code surfaces:**
- `efferents/cli.py` — `efferents` console-script entry point
- `efferents/lab.py` — replaces static module with `LabConfig` loader
- `efferents/registry.py` — `~/.efferents/registry.json` read/write
- `efferents/daemon.py` — fork + pidfile + signal handling wrapper around `orchestrator.start()`
- `intake.md` — hosted markdown contract (and `status.md` if it lands in v1)

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
- **`status.md`** is a v1-stretch goal. If it ships, the agent fetches it the same way it fetched `intake.md`; if it doesn't, the agent runs `efferents status --lab-id <id>` locally — same outcome.

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
    run_command: str                    # must contain "{config_path}"
    smoke_command: str | None
    config_template: Path
    run_timeout_s: int = 7200
    smoke_timeout_s: int = 300
    env_passthrough: tuple[str, ...] = ()

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
        "SUBDOMAIN": None,                # Phase A had this; not in LabConfig v1
        "PI_HANDLE": cfg.pi_handle,
        "CODE_REPO": "",                  # Phase A had this; LabConfig only carries source.dir
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

# Subprocess invocation always passes cwd=cfg.source.dir so the user's run
# command resolves its own relative paths against the source repo, not the
# daemon's submission CWD.
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
    cfg = lab.get_config()
    env = {**os.environ, **{k: os.environ[k] for k in cfg.executor.env_passthrough if k in os.environ}}
    proc = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        timeout=timeout_s, cwd=str(cfg.source.dir), env=env,
    )
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

---

## 8. Error handling & failure modes

Errors stratify by phase. Each has a clear surface and a recovery action.

### Phase 1 — Pre-daemon (agent's intake.md execution)

| Failure | Surface | Recovery |
|---|---|---|
| `popper-probe` not installed | Agent refuses Step 1 | Human installs it, restarts intake |
| `falsifiability_gate: failed` | Agent shows the `## Diagnostic` block, STOPs | Human sharpens claim, restarts intake |
| `efferents validate` finds bad `lab.yaml` | Agent surfaces field-level error from CLI stderr | Human fixes lab.yaml, agent re-runs validate |
| Human declines Step-5 warnings | Agent STOPs | Human aborts or fixes the concern (e.g., commits source dir) |

No daemon launched until Step 6. Failures here cost only conversation tokens.

### Phase 2 — Daemon startup

| Failure | Surface | Recovery |
|---|---|---|
| `lab/` mkdir or migration fails (permissions, disk full) | Exit code 1, stderr diagnostic; nothing registered | Fix the underlying issue; re-run `efferents start` |
| Registry file lock contention | Retry 3× with backoff, then fail with message naming the contending PID | Resolve the conflict (usually a concurrent CLI invocation) |
| Stale pidfile (PID dead, registry says running) | `efferents start` detects this on re-launch, clears the stale pidfile, marks registry `stopped`, proceeds | Automatic |
| `os.fork()` fails | Exit code 1 (rare; only on resource-starved hosts) | Free resources; re-run |

Daemon does **not** start partial. Either the lab is fully initialized + registered + forked, or nothing.

### Phase 3 — Daemon runtime

**Anthropic API failures.**
- `5xx` / rate limit: exponential backoff inside `efferents.agents.budget` retry helper (already exists for Phase A). Cap at 5 retries; on persistent failure, log + pause orchestrator for 10 minutes, then resume.
- `4xx` (auth, request shape): treated as fatal — daemon halts, writes diagnostic to `daemon.log` + `lab/halt_reason.txt`, exits non-zero. Requires human intervention (bad API key, etc.).

**Budget exhaustion.**
- `BudgetTracker` already enforces a per-day cap. When hit: orchestrator pauses (doesn't exit); next API call returns "budget exhausted" and the loop sleeps until midnight UTC then resumes. `efferents status` surfaces "budget paused, resumes <time>".

**Subprocess (run_command / smoke_command) failures.**
- Timeout: process killed, run marked `failed`, Coder restores snapshot, Researcher reads the failure from `coder_log.jsonl` and avoids re-proposing.
- Non-zero exit: same as above.
- Empty stdout / no trailing JSON: same as above; daemon logs "run_command did not emit JSON result on stdout" — surfaces missing executor contract.
- Smoke test fails: expected; Coder restores snapshot; not a daemon-level error.
- Real run fails repeatedly (3 in a row, same git_commit): orchestrator marks the campaign blocked; Researcher proposes a different direction.

**State integrity.**
- SQLite write fails (disk full, corruption): daemon halts, writes diagnostic, exits non-zero. No corruption recovery in v1 — manual `sqlite3` repair if it happens.
- `state.json` write fails: same.

### Phase 4 — Daemon liveness

**Crash detection.** No heartbeat thread in v1. `efferents status` infers liveness from:
- Pidfile present + PID is alive process → `running`
- Pidfile present + PID dead → `crashed`
- Pidfile absent + registry says running → `crashed` (rare; race condition during fork)
- `state.json` mtime older than 1 hour → `running but stale`; the daemon may be hung

**Crash recovery.** Re-running `efferents start --submission <same-dir>` is idempotent:
- Clears stale pidfile, removes stale registry entry.
- Re-runs migrations (no-op).
- Inspects `state.db` for rows with `status='started'` and no result row — marks them `crashed`.
- Forks a fresh daemon, re-attaches to `state.db`, resumes orchestrator loop.

**Orphaned subprocesses.** A daemon crash mid-run leaves the run_command process orphaned. Daemon doesn't track subprocess PIDs across crashes. Documented limitation: user should `ps` or check remote backend if a run looks orphaned. Phase B could add a runs table column tracking subprocess PID + host.

**No auto-restart in v1.** When daemon dies, it stays dead until human action. Phase B can wrap in systemd / launchd / pm2. Don't ship auto-restart now — it would mask bugs.

### Phase 5 — Human/agent recovery flow

User opens a Claude Code session and says "check on lab `<id>`" (or fetches `status.md` if it shipped in v1). Their agent runs `efferents status --lab-id <id>` and reports:
- Status (running / stopped / crashed / stale)
- Last activity, runs completed, current campaign
- Budget spent today
- Headline metric trajectory
- Dashboard path
- If crashed: the contents of `lab/halt_reason.txt` (if present) or the tail of `daemon.log`

Recovery actions the agent can suggest:
- `efferents stop --lab-id <id>` → graceful shutdown
- `efferents start --submission <dir>` → restart (idempotent re-attach)
- `tail lab/daemon.log` → inspect
- `open lab/progress/index.html` → dashboard

### Out of scope for v1
- Auto-restart / process supervision
- Heartbeat thread + dead-mans-switch
- Slack / ntfy alerts on daemon crash (`notify.py` exists but isn't wired into crash paths)
- Distributed run tracking (subprocess PIDs on remote hosts)
- Sentry / error aggregation

---

## 9. Testing strategy + the smoke lab

The decouple work and the new code each need their own verification path. The smoke lab is the integration test.

### 9.1 — Unit tests for new code

| Module | Test file | Key cases |
|---|---|---|
| `efferents.lab.LabConfig` | `tests/test_lab_config.py` | valid submission → frozen config; missing hypothesis.md; `falsifiability_gate: failed`; missing required field; non-existent `source.dir`; bad direction; missing `{config_path}` placeholder; defaults applied; absolute vs relative path resolution |
| `efferents.registry` | `tests/test_registry.py` | empty registry create; concurrent writes (two CLI invocations); stale-PID cleanup; corrupted JSON recovery (truncate + warn) |
| `efferents.daemon` | `tests/test_daemon.py` | foreground happy path (no fork); detach writes pidfile; SIGTERM clean shutdown; second start with stale pidfile cleans it; second start with live pidfile errors out |
| `efferents.cli` | `tests/test_cli.py` | `validate` exit codes + stderr shape; `start --submission` end-to-end (foreground, smoke lab); `status` against running/stopped/crashed daemon; `list` table format; `stop` idempotent |
| `_run_and_capture` (in coder or new exec module) | `tests/test_run_capture.py` | trailing JSON parsed; no JSON → ok=False with named error; timeout → ok=False; multi-line stdout with JSON in middle (only last is taken); malformed JSON tolerated |

All new code targets ≥80% line coverage. No mocking the Anthropic client beyond what Phase A already does.

### 9.2 — Carrying over Phase A's existing tests

Per CLAUDE.md, 62/65 tests came over from auto-qml. Triage plan:

1. Run `uv run pytest tests/` once, capture pass/fail.
2. **Generic tests** (state primitives, budget tracker, migrations, schemas, popper-gate, paper frontmatter): expected to pass post-decouple. Fix any that break — usually because they imported `lab.LAB_ID` or similar and now need `lab.set_config(...)` setup. Add a `conftest.py` fixture that loads a minimal smoke-lab LabConfig for all tests.
3. **QML-specific tests** (anything asserting on `e_w1`, jet metrics, QML-shaped run rows): move to `tests/lab_reference/` and mark with `@pytest.mark.skip(reason="QML-specific; lives with auto-qml long-term")` until auto-qml migrates back to consuming `efferents` as a dep. No effort wasted maintaining them here.
4. Document the split in `tests/README.md`.

Goal: every test in `tests/` (excluding `tests/lab_reference/`) passes against the smoke lab fixture. CI should fail if a generic test slips into QML-coupled assertions.

### 9.3 — The smoke lab (proves the plumbing)

A deliberately trivial non-QML lab. Its purpose is **proving the abstractions hold**, not doing research. Lives at `examples/smoke-lab/`.

```
examples/smoke-lab/
├── README.md                    # how to invoke + what it proves
├── hypothesis.md                # popper-formatted, silly but valid
├── lab.yaml                     # exercises the full schema
├── src/
│   ├── __init__.py
│   ├── stub_run.py              # reads config, "trains", emits stdout JSON
│   └── stub_eval.py             # called from stub_run; deterministic given seed
└── configs/
    ├── default.yaml             # tunable knob (e.g., `coefficient: 0.5`)
    └── smoke.yaml               # cheap variant (fewer iterations)
```

**The "research" the smoke lab does:**
- Hypothesis (silly): "increasing `coefficient` above 0.7 reduces synthetic_loss below 0.1".
- `stub_run.py` computes `synthetic_loss = abs(0.8 - coefficient) + tiny_noise(seed)`. Pure CPU, finishes in <1s.
- Emits the stdout JSON contract: `{"run_id":"...","metrics":{"synthetic_loss":0.073},...}`.
- Coder modifies `configs/default.yaml` (varies `coefficient`) and `src/stub_run.py` (could tweak noise/eval).
- Headline metric: `synthetic_loss`, direction `min`. Panels: just `synthetic_loss`.
- The hypothesis is genuinely falsifiable (Researcher can corroborate or refute by varying coefficient through 0–1 and observing where loss minimizes).

This is small enough that a daemon can run a full cycle (Researcher → Coder → smoke → run → eval → analyst digest) in under 30 seconds. Lets us run end-to-end tests in CI without GPU.

### 9.4 — End-to-end integration test

A single test (`tests/integration/test_smoke_lab_e2e.py`) that:

1. Copies `examples/smoke-lab/` to a tmpdir.
2. Runs `efferents validate --submission <tmpdir>` — asserts exit 0, parses lab_id.
3. Runs `efferents start --submission <tmpdir>` foreground for ~60 seconds (subprocess + timeout).
4. Asserts: `state.db` exists; ≥3 runs completed; ≥1 has non-null `synthetic_loss`; `progress/index.html` rendered; `daemon.log` contains no ERROR lines.
5. Skips if `ANTHROPIC_API_KEY` not set (so contributors can run unit tests without keys).

Marked `@pytest.mark.integration` and excluded from default `pytest` run; opt in via `pytest -m integration`. Cost: ~$0.10/run in Anthropic spend.

### 9.5 — Manual verification before first deploy

Per the `verification-before-completion` skill, claims of "working" require evidence. Before we say "v1 deployed":

1. **Decouple smoke** — Phase A code paths use `lab.get_config()`:
   - `python -c "from efferents.lab import LabConfig; ..."` builds a smoke LabConfig in isolation.
   - Run smoke-lab integration test; observe Coder editing `src/stub_run.py`, smoke passing.
2. **Intake flow** — fresh Claude Code session reads the hosted `intake.md` and runs through the steps with the smoke lab as input. Observe popper-probe firing, lab.yaml prompted, daemon started, dashboard reachable.
3. **Status flow** — close the session, open a new one, ask "check on the smoke lab". Confirm `efferents status` output is informative.
4. **Crash recovery** — `kill -9` the daemon; re-run `efferents start`. Confirm idempotent re-attach, no data lost.
5. **auto-qml sanity** — `cd ../auto-qml && uv run pytest tests/` against the new efferents. If any QML tests regress, debug or pin auto-qml to a pre-decouple efferents commit until migration.

Document the results in a `docs/superpowers/specs/<date>-deployment-verification.md` companion (dated when written) before announcing.

### Out of scope for v1
- Property-based tests for LabConfig validation
- Fuzz testing of the stdout-JSON parser
- Performance benchmarking of the daemon loop
- Cross-platform CI (macOS only at launch; Linux as it comes up)
