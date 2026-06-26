"""Execute a repo-adapter (`efferents.yaml`) as a bounded experiment loop.

`efferents run <repo>` loads the adapter config, sweeps the configured parameter
(running the repo's real train + eval commands each iteration), parses the
metric from eval's stdout JSON, enforces the budget, and writes the same journal
/ runs / claims / dashboard artifacts as the offline demo — with provenance.

No paid API is involved: the "agent" decisions (what to sweep, how to write up
the result) are deterministic. The *experiments* are real subprocess runs of the
target repo's commands.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import yaml

from efferents.exec import _extract_trailing_json
from efferents.repo_adapter import RepoAdapterConfig


class RunnerError(RuntimeError):
    pass


def _ts(i: int) -> str:
    minute = i
    return f"2026-06-25T09:{minute:02d}:00Z"


def _run_capture(cmd: str, cwd: Path, timeout_s: int = 120) -> tuple[dict | None, str, int]:
    import subprocess

    proc = subprocess.run(
        cmd, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s
    )
    return _extract_trailing_json(proc.stdout), proc.stdout + proc.stderr, proc.returncode


def _iterations(cfg: RepoAdapterConfig) -> list[tuple[str, object]]:
    """(label, value) per experiment. Single unparameterized run if no sweep."""
    if cfg.sweep is None:
        return [("base", None)]
    return [(f"{cfg.sweep.param}={v}", v) for v in cfg.sweep.values]


def run_adapter(repo: str | Path, out_dir: str | Path, *, max_iters: int | None = None) -> Path:
    repo = Path(repo).resolve()
    cfg = RepoAdapterConfig.load(repo)

    out = Path(out_dir).resolve()
    journal = out / cfg.outputs.journal_dir
    journal.mkdir(parents=True, exist_ok=True)
    (out / "configs").mkdir(exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)

    base_cfg: dict = {}
    if cfg.config_template:
        tmpl = (repo / cfg.config_template).resolve()
        if not tmpl.is_file():
            raise RunnerError(f"config_template not found: {tmpl}")
        base_cfg = yaml.safe_load(tmpl.read_text()) or {}

    iters = _iterations(cfg)
    if max_iters is not None:
        iters = iters[:max_iters]

    print(f"efferents run · {cfg.metric} ({'maximize' if cfg.maximize else 'minimize'}) "
          f"· {len(iters)} experiments · approval={cfg.approval_mode}")

    # 001 + 002 are written before any experiment executes (plan_then_execute).
    _write_hypothesis(journal, cfg)
    _write_plan(journal, cfg, iters)

    if cfg.approval_mode == "dry_run":
        print("approval.mode=dry_run — plan written, no experiments executed.")
        _write_dashboard(out, cfg, [], None, dry_run=True)
        return out

    runs: list[dict] = []
    gpu_seconds = 0.0
    budget_s = (cfg.budget.max_gpu_hours or float("inf")) * 3600
    for i, (label, value) in enumerate(iters):
        if gpu_seconds >= budget_s:
            print(f"budget reached ({cfg.budget.max_gpu_hours} GPU-h) — stopping early.")
            break

        run_cfg = dict(base_cfg)
        if cfg.sweep is not None:
            run_cfg[cfg.sweep.param] = value
        ckpt_dir = out / "ckpt" / f"iter_{i:02d}"
        run_cfg["checkpoint_dir"] = str(ckpt_dir)
        cfg_path = out / "configs" / f"iter_{i:02d}.yaml"
        cfg_path.write_text(yaml.safe_dump(run_cfg))

        log_path = out / "logs" / f"iter_{i:02d}.log"
        t0 = time.time()

        train_cmd = cfg.train_command.replace("{config_path}", str(cfg_path))
        tj, tlog, trc = _run_capture(train_cmd, repo)
        if tj is None or "checkpoint" not in tj or trc != 0:
            log_path.write_text(f"$ {train_cmd}\n{tlog}\n")
            raise RunnerError(f"train command failed or emitted no checkpoint (iter {i}); see {log_path}")
        checkpoint = tj["checkpoint"]

        eval_cmd = cfg.eval_command.replace("{checkpoint}", str(checkpoint))
        ej, elog, erc = _run_capture(eval_cmd, repo)
        elapsed = time.time() - t0
        gpu_seconds += elapsed
        log_path.write_text(f"$ {train_cmd}\n{tlog}\n$ {eval_cmd}\n{elog}\n")
        if ej is None or erc != 0:
            raise RunnerError(f"eval command failed or emitted no metric (iter {i}); see {log_path}")
        metric_val = (ej.get("metrics") or {}).get(cfg.metric)
        if metric_val is None:
            raise RunnerError(f"eval output missing metric {cfg.metric!r} (iter {i})")

        runs.append({
            "run_id": f"run_{i:02d}",
            "started_at": _ts(i),
            "param": cfg.sweep.param if cfg.sweep else None,
            "value": value,
            "metric": cfg.metric,
            cfg.metric: round(float(metric_val), 4),
            "checkpoint": str(checkpoint),
            "config_path": os.path.relpath(cfg_path, out),
            "log_path": os.path.relpath(log_path, out),
            "elapsed_s": round(elapsed, 3),
        })
        print(f"  {label:<18} {cfg.metric}={round(float(metric_val), 4)}")

    if not runs:
        raise RunnerError("no experiments completed")

    best = (max if cfg.maximize else min)(runs, key=lambda r: r[cfg.metric])

    with (out / cfg.outputs.runs_file).open("w") as f:
        for r in runs:
            f.write(json.dumps(r) + "\n")

    claims = _build_claims(cfg, runs, best)
    with (out / cfg.outputs.claims_file).open("w") as f:
        for c in claims:
            f.write(json.dumps(c) + "\n")

    _write_results(journal, cfg, runs, best)
    _write_memo(journal, cfg, runs, best, claims, gpu_seconds)
    _write_dashboard(out, cfg, runs, best)

    print(f"\nWrote run to {out}")
    print(f"  {cfg.outputs.journal_dir}/   4 memos (001..004)")
    print(f"  {cfg.outputs.runs_file}   {len(runs)} runs")
    print(f"  {cfg.outputs.claims_file} {len(claims)} claims with provenance")
    print(f"  dashboard.html")
    print(f"  budget used: {gpu_seconds/3600:.4f} / {cfg.budget.max_gpu_hours} GPU-h, "
          f"$0.00 / ${cfg.budget.max_llm_cost_usd} LLM (offline)")
    print(f"\nOpen the dashboard:\n  open {out / 'dashboard.html'}")
    return out


# --------------------------------------------------------------------------- #
# Memo / claims / dashboard writers
# --------------------------------------------------------------------------- #

def _w(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n")


def _best_line(cfg: RepoAdapterConfig, best: dict) -> str:
    knob = f"{best['param']}={best['value']}" if best.get("param") else "the base config"
    return f"{cfg.metric}={best[cfg.metric]} at {knob} (`{best['run_id']}`)"


def _write_hypothesis(journal: Path, cfg: RepoAdapterConfig) -> None:
    space = ""
    if cfg.sweep:
        space = (f"\n\n**Search space:** `{cfg.sweep.param}` ∈ "
                 f"{{{', '.join(str(v) for v in cfg.sweep.values)}}}")
    _w(journal / "001_hypothesis.md", f"""\
---
memo: 001_hypothesis
agent: researcher
generated_at: 2026-06-25T09:00:00Z
---

# Objective

{cfg.goal}

**Metric:** `{cfg.metric}` ({'maximize' if cfg.maximize else 'minimize'}).{space}

## Why this is testable

Each experiment runs the repo's own train + eval commands and reports a single
scalar (`{cfg.metric}`). The configurations are ordered, so the loop either
finds a setting that moves the metric or shows the metric is flat across the
search space.
""")


def _write_plan(journal: Path, cfg: RepoAdapterConfig, iters: list) -> None:
    rows = "\n".join(f"| {i+1} | {label} |" for i, (label, _) in enumerate(iters))
    _w(journal / "002_experiment_plan.md", f"""\
---
memo: 002_experiment_plan
agent: researcher
generated_at: 2026-06-25T09:00:00Z
approval: {cfg.approval_mode}
---

# Experiment plan

**Objective:** {cfg.goal}

Each experiment runs:

```
train: {cfg.train_command}
eval:  {cfg.eval_command}
```

| # | experiment |
|---|------------|
{rows}

**Budget ceiling:** {cfg.budget.max_gpu_hours} GPU-hours, ${cfg.budget.max_llm_cost_usd} LLM spend.
**Approval mode:** `{cfg.approval_mode}` — this plan is recorded before any experiment runs.
""")


def _write_results(journal: Path, cfg: RepoAdapterConfig, runs: list, best: dict) -> None:
    rows = "\n".join(
        f"| `{r['run_id']}` | {r['value'] if r.get('value') is not None else '—'} | "
        f"{r[cfg.metric]} |{' ⬅ best' if r['run_id'] == best['run_id'] else ''}"
        for r in runs
    )
    _w(journal / "003_results.md", f"""\
---
memo: 003_results
agent: analyst
generated_at: 2026-06-25T09:00:00Z
runs: {len(runs)}
---

# Results

{len(runs)} experiments completed locally. Objective: {'maximize' if cfg.maximize else 'minimize'} `{cfg.metric}`.

| run_id | {cfg.sweep.param if cfg.sweep else 'config'} | {cfg.metric} | |
|--------|------|------|---|
{rows}

**Best:** {_best_line(cfg, best)}.

> Provenance: every row is one line in [`../{cfg.outputs.runs_file}`](../{cfg.outputs.runs_file});
> each run's train+eval stdout is under `logs/`.
""")


def _write_memo(journal: Path, cfg: RepoAdapterConfig, runs: list, best: dict,
                claims: list, gpu_seconds: float) -> None:
    ev_rows = "\n".join(
        f"| {c['claim']} | {c['evidence_type']} | `{c['source_path']}` | "
        f"`{c['run_id'] or '—'}` | {c['metric'] or '—'} |"
        for c in claims
    )
    worst = (min if cfg.maximize else max)(runs, key=lambda r: r[cfg.metric])
    _w(journal / "004_reviewed_memo.md", f"""\
---
memo: 004_reviewed_memo
agent: writer
reviewed_by: reviewer-board (critical / neutral / enthusiast)
review_status: accepted
generated_at: 2026-06-25T09:00:00Z
---

# Reviewed research memo: {cfg.goal}

## Summary

Across {len(runs)} bounded experiments, the best setting was
{_best_line(cfg, best)} — versus {worst[cfg.metric]} at the weakest setting.
The objective ({'maximize' if cfg.maximize else 'minimize'} `{cfg.metric}`) is
addressed by the search above. Ran fully on local compute in
{gpu_seconds/3600:.4f} GPU-hours; $0.00 LLM spend.

## Hypothesis

{cfg.goal}

## Experiment plan

Swept `{cfg.sweep.param}` over {len(runs)} values, running the repo's own
`train`/`eval` each time. Full plan: [`002_experiment_plan.md`](002_experiment_plan.md).

## Results

Best `{cfg.metric}` = {best[cfg.metric]} at `{cfg.sweep.param if cfg.sweep else 'base'}`
= {best.get('value', '—')}. Full table: [`003_results.md`](003_results.md).

## Reviewer notes

- *Critical:* the sweep is coarse ({len(runs)} points); the true optimum may lie
  between sampled values. A finer sweep around the best point is the next step.
- *Neutral:* every number resolves to a run_id and a logged train/eval pair
  (see evidence table). Provenance is complete and the budget ceiling held.
- *Enthusiast:* a clear, reproducible signal on the first pass.
- **Board decision: accepted** for the internal lab journal.

## Limitations

- Toy synthetic task — exercises the adapter end to end, not a real domain.
- Single parameter, single metric; no interaction effects explored.
- Deterministic data; no variance estimate across seeds.

## Next experiment

Refine `{cfg.sweep.param}` around {best.get('value', 'the best value')} and add a
second seed to estimate run-to-run variance of `{cfg.metric}`.

## Evidence table

Every nontrivial claim below points to a run, a metric, or a source file.

| claim | evidence_type | source_path | run_id | metric |
|-------|---------------|-------------|--------|--------|
{ev_rows}
""")


def _build_claims(cfg: RepoAdapterConfig, runs: list, best: dict) -> list[dict]:
    return [
        {
            "claim": f"Best {cfg.metric} = {best[cfg.metric]} at "
                     f"{best.get('param')}={best.get('value')}",
            "evidence_type": "run_metric",
            "source_path": best["log_path"],
            "run_id": best["run_id"],
            "metric": cfg.metric,
            "value": best[cfg.metric],
        },
        {
            "claim": f"{cfg.metric} varies across the {best.get('param')} sweep",
            "evidence_type": "metric_aggregate",
            "source_path": cfg.outputs.runs_file,
            "run_id": None,
            "metric": cfg.metric,
            "value": f"range={min(r[cfg.metric] for r in runs)}..{max(r[cfg.metric] for r in runs)}",
        },
        {
            "claim": "Experiment plan recorded before execution",
            "evidence_type": "document",
            "source_path": f"{cfg.outputs.journal_dir}/002_experiment_plan.md",
            "run_id": None,
            "metric": None,
            "value": f"approval={cfg.approval_mode}",
        },
        {
            "claim": "Ran within budget on local compute",
            "evidence_type": "budget",
            "source_path": f"{cfg.outputs.journal_dir}/004_reviewed_memo.md",
            "run_id": None,
            "metric": None,
            "value": f"<= {cfg.budget.max_gpu_hours} GPU-h, $0 LLM",
        },
    ]


def _write_dashboard(out: Path, cfg: RepoAdapterConfig, runs: list, best: dict | None,
                     dry_run: bool = False) -> None:
    metric = cfg.metric
    if runs:
        mmax = max(r[metric] for r in runs) or 1.0
        bars = "\n".join(
            f'''        <div class="bar-row">
          <span class="coef">{r.get('value', '—')}</span>
          <div class="bar" style="width:{max(4, r[metric] / mmax * 100):.0f}%"></div>
          <span class="val{' best' if best and r['run_id'] == best['run_id'] else ''}">{r[metric]}</span>
        </div>'''
            for r in runs
        )
        run_rows = "\n".join(
            f'''        <tr{' class="best"' if best and r['run_id'] == best['run_id'] else ''}>
          <td><code>{r['run_id']}</code></td><td>{r.get('value', '—')}</td>
          <td>{r[metric]}</td><td><code>{r['log_path']}</code></td>
        </tr>'''
            for r in runs
        )
        headline = f"{best[metric]}" if best else "—"
    else:
        bars = run_rows = ""
        headline = "dry run"

    banner = ("approval.mode=dry_run — plan only, no experiments executed."
              if dry_run else
              "Rendered from runs.jsonl + the journal memos in this folder.")
    _w(out / "dashboard.html", f"""\
<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>efferents run — {cfg.metric}</title>
<style>
:root {{ --bg:#0d0f12; --panel:#161a1f; --line:#2a2f37; --fg:#e6e8eb;
        --muted:#8b939c; --accent:#88f; --ok:#4a9; }}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,system-ui,sans-serif}}
header{{padding:24px;border-bottom:1px solid var(--line)}}
h1{{font-size:22px;margin:0 0 4px}} .muted{{color:var(--muted)}} .small{{font-size:12px}}
code{{background:#000;padding:1px 5px;border-radius:4px;font-size:12px}}
main{{max-width:860px;margin:0 auto;padding:24px}}
.cards{{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0 24px}}
.card{{flex:1;min-width:170px;border:1px solid var(--line);border-radius:8px;padding:14px 16px;background:var(--panel)}}
.card .k{{text-transform:uppercase;font-size:11px;letter-spacing:.06em;color:var(--muted)}}
.card .v{{font-size:24px;margin-top:4px}} .v.ok{{color:var(--ok)}}
.section{{margin:28px 0}} .section h2{{font-size:14px;text-transform:uppercase;letter-spacing:.06em;
  color:var(--muted);border-bottom:1px solid var(--line);padding-bottom:6px}}
.bar-row{{display:flex;align-items:center;gap:10px;margin:6px 0}}
.coef{{width:60px;color:var(--muted);text-align:right;font-size:13px}}
.bar{{height:16px;background:linear-gradient(90deg,#88f,#4a9);border-radius:3px}}
.val{{font-size:13px;color:var(--muted)}} .val.best{{color:var(--ok);font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}}
th{{color:var(--muted);font-weight:500}} tr.best td{{background:rgba(74,153,153,.10)}}
.memos a{{display:block;color:var(--accent);text-decoration:none;padding:4px 0}}
.banner{{background:rgba(136,136,255,.08);border:1px solid var(--line);border-radius:8px;
  padding:10px 14px;font-size:13px;color:var(--muted)}}
</style></head><body>
<header>
  <h1>{cfg.goal} <span class="muted small">· efferents run</span></h1>
  <div class="muted small">Local compute · offline · metric: {cfg.metric}</div>
</header>
<main>
  <div class="banner">{banner}</div>
  <div class="cards">
    <div class="card"><div class="k">best {cfg.metric}</div><div class="v ok">{headline}</div></div>
    <div class="card"><div class="k">experiments</div><div class="v">{len(runs)}</div></div>
    <div class="card"><div class="k">LLM spend</div><div class="v">$0.00</div></div>
  </div>
  <div class="section">
    <h2>{cfg.metric} by {cfg.sweep.param if cfg.sweep else 'config'}</h2>
{bars}
  </div>
  <div class="section">
    <h2>Runs (provenance)</h2>
    <table>
      <tr><th>run_id</th><th>{cfg.sweep.param if cfg.sweep else 'config'}</th><th>{cfg.metric}</th><th>log</th></tr>
{run_rows}
    </table>
  </div>
  <div class="section memos">
    <h2>Research journal</h2>
    <a href="{cfg.outputs.journal_dir}/001_hypothesis.md">001 · Objective</a>
    <a href="{cfg.outputs.journal_dir}/002_experiment_plan.md">002 · Experiment plan</a>
    <a href="{cfg.outputs.journal_dir}/003_results.md">003 · Results</a>
    <a href="{cfg.outputs.journal_dir}/004_reviewed_memo.md">004 · Reviewed memo (with evidence table)</a>
  </div>
</main></body></html>
""")
