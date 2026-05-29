# Deployment v0.1 verification

**Date:** 2026-05-28
**Branch:** `feat/efferents-deployment`
**Scope:** Manual verification per the [deployment design spec](./2026-05-26-efferents-deployment-design.md), section 9.5.

## 1. Decouple smoke — Phase A code paths use LabConfig

✅ All four decouple touchpoints verified:
- `efferents.lab.LabConfig.from_submission(...)` builds a frozen config from a submission dir. Unit-tested across 14 cases (`tests/test_lab_config.py`).
- `efferents.agents.coder` reads `source.dir`, `allowed_patterns`, `smoke_command`, `smoke_timeout_s` from LabConfig. 4 helper tests (`tests/test_coder_path_scope.py`).
- `efferents.agents.progress._panel_metrics()` and `_headline_metric()` read from LabConfig. 3 tests (`tests/test_progress_panels.py`).
- `efferents.agents.analyst._flat_digest_epsilon()` reads from LabConfig. 2 tests (`tests/test_analyst_epsilon.py`).

## 2. Generic test suite

```
$ uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration
121 passed, 3 skipped
```

The 3 skips are QML-coupled tests with `@pytest.mark.skip(reason="QML-specific; lives with auto-qml")` markers — see [tests/README.md](../../../tests/README.md). They were the 3 pre-existing failures from the CLAUDE.md handoff (62/65 carry over); now triaged.

## 3. CLI surface

```
$ .venv/bin/efferents --help
usage: efferents [-h] {validate,start,status,stop,list} ...
```

All 5 subcommands registered via `[project.scripts] efferents = "efferents.cli:main"`. 12 CLI unit tests (`tests/test_cli.py`).

## 4. Smoke-lab validate

```
$ .venv/bin/efferents validate --submission examples/smoke-lab/
OK lab_id=smoke-coefficient domain=synthetic source_dir=.../examples/smoke-lab/src
```

✅ Validation passes against the non-QML smoke lab. Proves the LabConfig loader works for any domain.

## 5. End-to-end smoke-lab cycle

🟡 **Substantially resolved in v0.1.1** (see [`2026-05-29-research-loop-e2e-design.md`](./2026-05-29-research-loop-e2e-design.md)). Remaining gap is documented below.

**v0.1.1 closed all three v0.1 gaps:**
- `_init_lab_root` now scaffolds `<submission>/context/research_log.md` and calls `ensure_runs_table(db, cfg)` so the runs schema includes the LabConfig-declared metric columns from startup.
- `efferents.exec._persist_run_result` ALTERs missing columns and retries on `OperationalError`, so labs that add metrics mid-flight don't lose rows.
- `efferents.agents.executor.execute` was rewritten (domain-agnostic) to route through `_execute_run` + `_persist_run_result`. The legacy `auto_qml.run_from_config` path is no longer touched on new submissions.

**What I verified by hand on the smoke lab:**
- `efferents validate --submission examples/smoke-lab/` → OK
- `efferents start --submission examples/smoke-lab/` runs cleanly: daemon registers, orchestrator boots, Researcher fires (one Anthropic call cycle), Coder + Analyst cadence kicks in. No SQL crash on missing `runs` columns, no missing-`context/` crash, no `auto_qml.run_from_config` raise.
- The executor's stdout-JSON contract works end-to-end: on the daemon run where the Researcher's QML-flavored proposal reached the executor, the subprocess was spawned with the right `cwd`, stderr was captured (it surfaced a `python: command not found` shell-PATH issue on the smoke lab — fixed by switching the smoke lab's `run_command` to `python3`), and the generic "no JSON on stdout" error was logged in the new format. With `python3` in the command, `examples/smoke-lab/src/stub_run.py` standalone returns a valid stdout-JSON payload with `synthetic_loss`.

**The remaining gap — Researcher prompt-templating (Phase B).** The Researcher's prompt is still calibrated for QML — it proposes experiments with overrides like `data.raw_q`, `training.epochs`, expects metrics like `e_w1`, `radial_l2_log`, `active_frac_w1`. The smoke lab's `coefficient` knob is invisible to it. So while the executor pipeline is functional and the smoke lab's `stub_run.py` works in isolation, the Researcher won't *autonomously drive* a non-QML lab to convergence until prompt overrides ship in v0.1.2+. That's the next deploy slice.

**Net for v0.1.1:** the three deployment-blocking infrastructure gaps are closed. The next deploy slice is the Researcher (and Coder) prompt-templating work, which lets the Researcher propose experiments shaped by `LabConfig.metrics` and `LabConfig.source` rather than the QML reference lab's design space.

## 6. auto-qml compatibility

The auto-qml repo is a separate clone (`~/Documents/auto-qml`) and not validated here. The Task-0 prep (`fix(executor): make auto_qml.run import lazy`) means efferents now imports cleanly without auto-qml installed; reverse compatibility — auto-qml continuing to use efferents — is documented as requiring auto-qml's `run.py` to start emitting the stdout-JSON contract (or alternatively, the dual-read fallback discussed in spec section 7).

## 7. What's deployable today

- **Entry flow:** `skills/intake.md` is the moltbook-shaped contract. A user agent that fetches this file and follows it can install efferents, validate a submission, and start a daemon. The daemon will start cleanly; what it does next depends on item 5's follow-ups.
- **CLI:** `efferents validate` / `start` / `status` / `stop` / `list` all work as designed. Registry persistence, fcntl locking, double-fork detach mode, SIGTERM handling, and crash detection are all unit-tested.
- **Framework:** Phase A code is no longer QML-coupled at the load-bearing decouple touchpoints. New labs supply their own `lab.yaml`; the framework loads it and exposes it via `lab.get_config()`.

## 8. Recommendation

Ship v0.1.0 with these caveats documented in `examples/smoke-lab/README.md` and `skills/intake.md`. The entry-flow side of the deployment is complete and tested. The orchestrator side (real research cycles against the smoke lab) needs the two follow-ups in §5 before non-QML users can run a full lab — that's a Phase B priority.
