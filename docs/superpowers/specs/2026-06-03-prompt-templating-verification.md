# Prompt templating (v0.1.2) verification

**Date:** 2026-06-03
**Branch:** `feat/prompt-templating`
**Spec:** [`2026-06-02-prompt-templating-design.md`](./2026-06-02-prompt-templating-design.md)

## Result: the smoke lab self-drives end-to-end

The acceptance gate from the spec — *"the Researcher proposes a synthetic_loss experiment and a row lands in runs.sqlite, no QML hardcoding"* — is met.

### Unit + guard tests
```
uv run pytest tests/ --ignore=tests/lab_reference --ignore=tests/integration
164 passed, 3 skipped
```
- `tests/test_prompt_loader.py` — loader rendering, override resolution, PromptRenderError, all 11 framework prompts render clean.
- `tests/test_prompts_domain_agnostic.py` — zero QML tokens across all framework prompts (executable coupling guard).

### Live smoke-lab run (ANTHROPIC via `examples/smoke-lab/.env`)
```
efferents validate --submission examples/smoke-lab/   → OK
efferents start    --submission examples/smoke-lab/   → autonomous loop
```
Observed in `examples/smoke-lab/lab/`:
- Researcher opened campaign `c-132d4d4314` with a **domain-agnostic** hypothesis: *"What is the reproducible baseline synthetic_loss under the default config, and is the noise floor small enough for single-seed comparisons to be meaningful?"* — reasons entirely about `synthetic_loss`, zero QML vocabulary.
- Proposed `default_baseline_seed42`; the executor ran `python3 -m stub_run` and persisted a row.
- `runs.sqlite`: 1 run, `synthetic_loss = 0.2986` (= `abs(0.8 - 0.5)`, the deterministic stub value for the default `coefficient: 0.5`).
- Notebook rendered the generic metric table (`| synthetic_loss | / 0.2986`).
- 9 Anthropic calls, ~$0.46. No `PromptRenderError`, no `no such column: seed`, no `auto_qml` import error.

## Fixes made during verification (beyond the 8 planned tasks)

The acceptance run exposed three latent issues that the loop only reaches once the prompts let it run autonomously. All fixed:

1. **`efferents.cli start` didn't load `.env`** — the deployed entry-point lacked the `_load_dotenv()` the legacy `python -m efferents.agents start` had, so a detached daemon couldn't resolve `ANTHROPIC_API_KEY`. Extracted the loader to `efferents/envfile.py` (shared by both entry points); `_cmd_start` now loads `<submission>/.env` before the daemon forks. `.env` gitignored.
2. **Executor passed a relative config path** — `executor.execute` wrote `lab/configs/run_*.yaml` and passed it relative, but the run command executes with `cwd=source.dir` (≠ daemon cwd), so it failed with `FileNotFoundError`. Now resolved to absolute before invocation.
3. **smoke lab `run_command`** used `python3 -m src.stub_run` but the executor's `cwd=source.dir` (`./src`) makes the module `stub_run`, not `src.stub_run`. Fixed in `examples/smoke-lab/lab.yaml`.

Also: notifications now carry the active `lab_id` (`{lab_id} started/paused/stopped/digest/code committed`) instead of hardcoded `auto-qml`, so a user running several labs gets distinct notifications.

## Known limitations (deferred)

- **`_format_recent_runs` / `_saturation_report` in researcher.py still reference QML run-table columns** (`raw_q`, `e_w1`, …). These are deterministic *user-message table builders* and the saturation heuristic — not the system prompts this slice templated. `_saturation_report` is already try/except-guarded (v0.1.1) so it no-ops on a non-QML schema; `_format_recent_runs` renders empty cells for absent columns (degraded, not fatal). Generalizing these to read columns from `LabConfig.metrics` is the natural next slice (CLAUDE.md item 5 + 7, partially done).
- **`{run_command}` / `{smoke_command}` template vars are effectively unusable in prompts** because their values contain a nested `{config_path}` placeholder, which the zero-brace render convention forbids. Prompts describe the run command in prose / use `{config_template}` instead. Acceptable; documented.
- **Auto-qml degradation:** this repo's framework prompts are now generic, so auto-qml runs degraded until it adds its own `<submission>/prompts/` override directory restoring the QFM/HEP prose. Intended direction; auto-qml's next session does this.

## Recommendation

Tag v0.1.2. The framework now runs a fully autonomous, domain-agnostic research cycle on a non-QML lab — the core proof that the abstractions hold beyond the reference lab.
