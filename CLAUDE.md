# Session guidance for Claude Code — efferents framework

## What this repo is

A framework extracted from the [auto-qml](https://github.com/mashathepotato/auto-qml) reference lab on 2026-05-26. Long-term goal: a generic platform on which **autonomous research labs** are spun up, communicate via published papers, and aggregate into venues. Lifelong destination: hosted at `efferents.com`, others register their own labs and submit to shared venues.

Read these first:
- [`README.md`](./README.md) — what's here, layout
- [`context/journal_vision.md`](./context/journal_vision.md) — the multi-lab vision (forward design, the north star)
- [`docs/superpowers/specs/2026-05-17-lab-foundation-design.md`](./docs/superpowers/specs/2026-05-17-lab-foundation-design.md) — the Phase A spec that produced the agent loop you're inheriting
- [`docs/templates/qml-lab.py.example`](./docs/templates/qml-lab.py.example) — concrete `lab.py` from auto-qml; how a lab parameterizes the framework today

## What was migrated

Everything in `efferents/agents/`, `efferents/schemas/`, `efferents/migrations/`, and the generic tests under `tests/`. Imports were bulk-renamed:
- `from agents.X` → `from efferents.agents.X`
- `from auto_qml.schemas` → `from efferents.schemas`
- `from auto_qml.migrations` → `from efferents.migrations`
- `from auto_qml import lab` → `from efferents import lab`

`efferents/lab.py` is a placeholder with the SAME symbol surface as `auto_qml/lab.py` (LAB_ID, DOMAIN, PEER_REVIEW_*, STUDENTS, get_student, ...) but with abstract default values. Every executable `from auto_qml ...` import was removed; remaining `auto_qml` references are in comments, docstrings, and prompts (semantic, non-blocking at import time).

## What was NOT migrated (and why)

- `auto_qml/` package — entirely QML/physics-specific (data loading, quantum encoding, UNet, diffusion math, sampling, eval metrics). Belongs in the reference lab.
- `auto_qml/run.py` — QML CLI; stays in the reference lab. The framework should know how to *invoke* a lab's run command, not what the command does.
- `config/default.yaml` — QML config schema. The framework should treat the per-lab config as an opaque YAML it hands to the executor.
- `lab/`, `data/`, `paper/`, `reports/` — runtime artifacts; gitignored anyway.
- `context/research_log.md`, `decisions.md`, `plan.md`, `vision.md` — QML-research-specific narrative; only `journal_vision.md` (forward design) carried over.

## What's broken (the work you're inheriting)

1. **Prompts are QML-flavored.** `efferents/agents/prompts/*.md` references `auto_qml/X.py` paths, QFM encoding, jet metrics. Need to be reworked as **templates with placeholders** that a lab's identity / config fills in.

2. **Coder path scope is hard-coded.** `efferents/agents/coder.py` restricts itself to `auto_qml/<name>.py` (see `_NEW_FILE_PATH_RE` around line 83, plus several other path checks). Needs to be configurable per-lab — likely a `lab.CODER_SOURCE_DIR` constant or similar. References to `python -m auto_qml.run --config config/smoke.yaml` in the smoke-test path likewise need to come from lab config.

3. **`efferents/lab.py` is a static module, not a config system.** The proper API is probably a `LabConfig` dataclass loaded from `<lab>/lab.py` or a YAML at orchestrator startup. The current static module is fine for the reference lab's use but doesn't scale to multiple labs in one Python environment.

4. **Progress dashboard's `_PANEL_METRICS` is QML-specific** (`efferents/agents/progress.py` ~line 50): hardcodes `e_w1`, `active_frac_w1`, `radial_l2_log`, `gen_max_to_real_max`. Needs to come from lab config — each lab defines its own panel set and headline metrics.

5. **`agents/state.py`'s `recent_runs` SELECT** lists QML-specific columns (raw_q, aug_depth, etc.). The columns should be lab-defined; the framework should know about `run_id`, `started_at`, `campaign_id`, `researcher_mode`, `eval_kind`, and an opaque per-run metric dict — not specific physics columns.

6. **`analyst.py`'s `update_flat_digest_counter`** hardcodes `epsilon=0.005` (calibrated for W1 ~0.05–0.10). Should be lab-configurable, possibly per-metric.

7. **`writer.py`'s peer review prompts** and `should_publish`'s `gain_threshold=0.05` default — lab-configurable.

8. **Tests imports work but tests likely fail until the above is fixed** — many tests insert rows with QML columns and expect framework code to read them. Run `uv run pytest tests/` and triage.

## Suggested phasing for the next session

1. **Get tests green.** Run pytest, fix the most local import / fixture issues until the tests at least *collect* cleanly. Some tests are QML-specific and should move out to a separate `tests/lab_reference/` dir or be marked `@pytest.mark.skip` with a TODO.

2. **Introduce `LabConfig`.** A pydantic / dataclass model representing everything a lab parameterizes:
   - identity (LAB_ID, DOMAIN, etc.)
   - executor (`run_command`, `smoke_command`, `config_path`)
   - coder scope (`source_dir`, allowed file patterns)
   - metrics (panel metrics + headline + epsilon for flat-digest detection)
   - prompts (overrides per agent)
   - peer review (flags + thresholds)
   - students (multi-student backlog)

3. **Refactor `efferents/lab.py`** from a static module to a loader: at orchestrator startup, read `<cwd>/lab.py` or `<cwd>/efferents-lab.yaml`, populate a `LabConfig`, make it accessible via `efferents.lab.config`.

4. **Templatize the prompts.** Replace literal `auto_qml/X.py` references with `{source_dir}/X.py` placeholders rendered from `LabConfig`. The lab `student.md` prompt becomes a template the framework formats per-call.

5. **Generalize the Coder's path scope.** Read `lab.config.coder.source_dir` and `lab.config.coder.allowed_patterns` instead of the regex hardcoded against `auto_qml/`.

6. **Decouple progress.py metrics.** `_PANEL_METRICS` becomes `lab.config.metrics.panels`. Each panel: `(column_name, label, target_value | None)`.

7. **Decouple `recent_runs` SELECT.** Use `SELECT *` or accept a column-list from lab config. The framework only needs a stable set of *meta* columns (run_id, started_at, campaign_id, researcher_mode, eval_kind); everything else is lab-defined.

8. **Write the `efferents init <lab-name>` scaffold command.** Generates a starter lab directory with a `lab.py`, sample config, and an empty prompt-overrides dir. This is what "lab user upload their own autolab" looks like in practice.

9. **Write a second example lab.** Pick something trivial (MNIST diffusion, a classical ablation, anything that exercises the Lab config without QML's compute) and verify the framework runs it end-to-end without any framework edits. This is the real proof that the abstractions are right.

## Brand & deployment

- The repo will eventually be deployed at `efferents.com` (mirroring [moltbook.com](https://moltbook.com)) — a registration + venue-feed surface that labs hit via a `skill.md` REST contract. The hosted service is OUT OF SCOPE for the framework package; build the library first.

## Hard constraints

- **Do not re-introduce `auto_qml` imports.** They were intentionally stripped. If you need a concrete example to test against, point at the auto-qml repo or vendor a minimal stub.
- **Don't ship without a second lab as a working example.** The whole point of extracting is to prove the abstractions hold for more than one domain.
- **Popper-probe is an external dependency.** Use `POPPER_PROBE_REPO` env var; do not vendor it.
- **The journal vision (`context/journal_vision.md`) is forward design.** Phase A established the lab-level abstractions. Phase B onwards is multi-lab platform work. Do not start on venues / inter-lab reading / peer-review-across-labs until the single-lab framework is genuinely lab-agnostic.

## Working style notes carried over from auto-qml

- One YAML config = one run. The framework expects the lab's executor to be a command that takes a config path and produces a SQLite row.
- File-based state (no DB server). Lab state lives under `lab/`; popper hypotheses under `popper-corpus/`.
- macOS host. macOS launchd has TCC issues reading `~/Documents`; terminal-launched under `caffeinate` is the realistic agent path.
- Budget discipline is real. Every Anthropic call goes through `efferents.agents.budget`. Sonnet default; Opus on Analyst (and Researcher escalation).
- The reference lab uses `uv` for venv. Match that here.
